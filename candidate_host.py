"""Candidate-only maintenance. Never imports legacy services or robot drivers."""
import json
import os
import subprocess
import sys

UNIT = os.environ.get('COLOSSEUM_POLICY_UNIT', 'franka-candidate-policy.service')
STAGE = os.environ.get('COLOSSEUM_CANDIDATE_ROOT', '/path/to/candidate').rstrip('/')
ACTIONS = {'status', 'gpu', 'logs', 'start_policy', 'stop_policy', 'restart_policy'}
MUTATIONS = {'start_policy': 'start', 'stop_policy': 'stop', 'restart_policy': 'restart'}


def run(argv):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Command failed').strip()[:1000])
    return result.stdout.strip()


def remote_call(action):
    if action not in ACTIONS:
        raise ValueError('Unsupported candidate maintenance action')
    if action == 'gpu':
        data = run(['nvidia-smi', '--query-gpu=name,memory.used,memory.total,utilization.gpu',
                    '--format=csv,noheader,nounits'])
        return {'ok': bool(data), 'detail': data + ' (used MiB / total MiB / utilization %)'}
    if action == 'logs':
        return {'ok': True, 'policy_tail': run(['journalctl', '--user', '-u', UNIT, '-n', '100', '--no-pager', '-o', 'cat'])}
    # Check the exact unit's executable before allowing lifecycle operations.
    info = run(['systemctl', '--user', 'show', UNIT,
                '--property=LoadState,ActiveState,SubState,MainPID,ExecStart,FragmentPath'])
    props = dict(line.split('=', 1) for line in info.splitlines() if '=' in line)
    if props.get('LoadState') != 'loaded' or STAGE + '/envs/policy/bin/python' not in props.get('ExecStart', ''):
        raise RuntimeError('Candidate unit is missing or does not use the reviewed candidate environment')
    if action in MUTATIONS:
        run(['systemctl', '--user', MUTATIONS[action], UNIT])
        state = remote_call('status')
        expected = 'inactive' if action == 'stop_policy' else 'active'
        state['ok'] = state['active_state'] == expected
        return state
    active = props.get('ActiveState', 'unknown')
    return {'ok': active == 'active', 'active_state': active,
            'detail': UNIT + ': ' + active + '/' + props.get('SubState', 'unknown'),
            'pid': int(props.get('MainPID', '0'))}


class CandidateHost:
    def __init__(self, config):
        # An administrator-supplied argv, never constructed from HTTP input.
        self.command = list(config['command'])
        if not self.command or not all(isinstance(arg, str) and arg for arg in self.command):
            raise ValueError('candidate maintenance command must be a nonempty argv')

    def call(self, action):
        if action not in ACTIONS:
            raise ValueError('Unsupported candidate maintenance action')
        # SSH must not consume or change the worker's JSON-lines RPC input pipe.
        result = subprocess.run([*self.command, action], stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=55, check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or 'Candidate maintenance connection failed').strip()[:1000])
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or 'ok' not in value:
            raise RuntimeError('Invalid candidate maintenance response')
        if value.get('error'):
            raise RuntimeError(value['error'])
        return value


if __name__ == '__main__':
    try:
        value = remote_call(sys.argv[1] if len(sys.argv) == 2 else '')
    except Exception as exc:
        value = {'ok': False, 'error': str(exc)}
    print(json.dumps(value))
