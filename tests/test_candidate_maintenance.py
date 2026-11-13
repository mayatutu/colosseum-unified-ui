from types import SimpleNamespace
import threading
import pytest
import candidate_host as host
from runtime import Runtime


def test_restart_targets_only_reviewed_unit(monkeypatch):
    commands = []
    def run(argv):
        commands.append(argv)
        if 'show' in argv:
            return 'LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=7\nExecStart=' + host.STAGE + '/envs/policy/bin/python'
        return ''
    monkeypatch.setattr(host, 'run', run)
    assert host.remote_call('restart_policy')['ok']
    assert commands[1] == ['systemctl', '--user', 'restart', host.UNIT]
    assert len(commands) == 3


def test_foreign_unit_executable_refuses_mutation(monkeypatch):
    commands = []
    monkeypatch.setattr(host, 'run', lambda argv: commands.append(argv) or 'LoadState=loaded\nExecStart=/old/policy/python')
    with pytest.raises(RuntimeError, match='reviewed'):
        host.remote_call('stop_policy')
    assert len(commands) == 1


@pytest.mark.parametrize('action', ['restart_docker', 'restart_can', 'kill', 'restart_policy; killall python'])
def test_no_device_or_arbitrary_command(monkeypatch, action):
    monkeypatch.setattr(host, 'run', lambda argv: pytest.fail('No command allowed'))
    with pytest.raises(ValueError):
        host.remote_call(action)


def test_gpu_query_is_read_only(monkeypatch):
    commands = []
    monkeypatch.setattr(host, 'run', lambda argv: commands.append(argv) or 'GPU, 16, 24576, 0')
    assert host.remote_call('gpu')['ok']
    assert len(commands) == 1 and commands[0][0] == 'nvidia-smi'


@pytest.mark.parametrize('recording,pending', [(True, False), (False, True)])
def test_active_client_never_stopped_for_maintenance(recording, pending):
    runtime = Runtime.__new__(Runtime)
    runtime.candidate = object()
    runtime.maintenance_lock = threading.Lock()
    runtime.lock = threading.RLock()
    runtime.round_stop_pending = pending
    runtime.c = SimpleNamespace(recording=lambda: recording)
    runtime.policy = lambda *a: pytest.fail('No maintenance while evaluating')
    with pytest.raises(RuntimeError, match='End the evaluation'):
        runtime.maintain('restart_policy')


def test_stop_reports_inactive_as_success(monkeypatch):
    responses = iter(['LoadState=loaded\nExecStart=' + host.STAGE + '/envs/policy/bin/python', '',
                      'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nExecStart=' + host.STAGE + '/envs/policy/bin/python'])
    monkeypatch.setattr(host, 'run', lambda argv: next(responses))
    assert host.remote_call('stop_policy')['ok']


def test_transport_fails_without_fallback(monkeypatch):
    monkeypatch.setattr(host.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=255, stderr='Permission denied'))
    with pytest.raises(RuntimeError, match='Permission denied'):
        host.CandidateHost({'command': ['ssh', 'reviewed-host', 'python3', 'helper.py']}).call('status')


def test_candidate_offline_endpoint_not_false_green(monkeypatch):
    from colosseum_client import local_policy
    runtime = Runtime.__new__(Runtime)
    runtime.candidate = SimpleNamespace(call=lambda action: {'ok': True, 'detail': 'active'})
    runtime.c = SimpleNamespace(CONFIG=SimpleNamespace(policy_server_url='ws://127.0.0.1:18001'),
                                S=SimpleNamespace(set_check=lambda *a: None))
    async def capabilities(url):
        raise ConnectionError('Tunnel unavailable')
    monkeypatch.setattr(local_policy, 'capabilities', capabilities)
    assert runtime.policy('status') == {'ok': False, 'detail': 'Tunnel unavailable'}


def test_successful_stop_does_not_display_running():
    runtime = Runtime.__new__(Runtime)
    states = []
    runtime.candidate = SimpleNamespace(call=lambda action: {'ok': True, 'active_state': 'inactive', 'detail': 'stopped'})
    runtime.c = SimpleNamespace(S=SimpleNamespace(set_check=lambda *args: states.append(args)))
    assert runtime.policy('stop_policy')['ok']
    assert states == [('server', 'idle', 'stopped')]


def test_ssh_never_inherits_worker_protocol_stdin(monkeypatch):
    def run(args, **kwargs):
        assert kwargs['stdin'] == host.subprocess.DEVNULL
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr='')
    monkeypatch.setattr(host.subprocess, 'run', run)
    assert host.CandidateHost({'command': ['ssh', 'host', 'python3', 'helper.py']}).call('status')['ok']
    assert host.run(['systemctl', '--user', 'show', host.UNIT]) == '{"ok":true}'
