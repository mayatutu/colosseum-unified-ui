"""Offline contract exercise of actual Client evaluation code; fake Router/trials only in this test."""
import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from station import Station
from store import PendingEvaluation

robot, scenario = sys.argv[1:3]
workspace = ROOT.parents[1]
client = (workspace / 'deployment/client-reset-timing-20261027/candidate' if robot == 'franka'
          else workspace / 'Official/colosseum-client-main')
sys.path.insert(0, str(client / 'src'))
import colosseum_client.evaluation as ev
import colosseum_client.lerobot_export as lx
if robot == 'yam':
    # Use the read-only snapshot of the YAM workstation's actual evaluation loop, not only the newer archive.
    source = ROOT / 'validation/yam-evaluation-source.py'
    spec = importlib.util.spec_from_file_location('colosseum_client.evaluation', source)
    ev = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ev
    spec.loader.exec_module(ev)
    import colosseum_client
    colosseum_client.evaluation = ev

import yaml
from runtime import Runtime
from client_job import run as submit_job

with tempfile.TemporaryDirectory(prefix='unified-ui-contract-') as tmp:
    tmp = Path(tmp)
    config = {'url': 'ws://127.0.0.1:1', 'api_url': 'http://127.0.0.1:1', 'token': 'offline-test',
              'robot_type': robot, 'test': True, 'cameras': {'head_image': 'offline-test'},
              'policy_server_url': 'ws://127.0.0.1:8000', 'recording': True, 'skip_upload': True,
              'evaluation_dir': str(tmp / 'evals'), 'institution': 'offline-test', 'max_trial_steps': 2}
    (tmp / 'robot.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    (tmp / 'station.yaml').write_text(yaml.safe_dump({'robot': robot, 'client_root': str(client),
        'client_python': sys.executable, 'robot_config': str(tmp / 'robot.yaml'), 'database': str(tmp / 'stats.db')}))
    station = Station.load(tmp / 'station.yaml')
    calls, assignments, exports, trials = [], {}, [], []
    lost = [scenario == 'lost_response']

    def request(api, method, route, body=None):
        calls.append((method, route, copy.deepcopy(body)))
        if route == '/reset':
            return {}
        if route == '/next':
            eid = 'ev_contract_' + str(len(assignments) + 1)
            value = {'id': eid, 'robot_id': robot, 'state': 'pending', 'track': 'open', 'test': True,
                     'recording': True, 'inference_mode': 'local', 'institution': 'offline-test',
                     'scene': body['scene'], 'evaluator': body['evaluator'],
                     'task': {'instruction': body['instruction'], 'cameras': ['head_image'], 'max_steps': 2},
                     'runs': [{'id': 'run_' + eid + side, 'side': side, 'state': 'assigned'} for side in ('A', 'B')]}
            assignments[eid] = value
            return copy.deepcopy(value)
        eid = route.split('/')[2]
        if method == 'GET':
            return copy.deepcopy(assignments[eid])
        if route.endswith('/result'):
            assignments[eid]['state'] = 'completed'
            assignments[eid]['result'] = copy.deepcopy(body)
            if lost[0]:
                lost[0] = False
                raise TimeoutError('Injected lost response after Router acceptance')
            return {'ok': True}
        if route.endswith('/abort'):
            assignments[eid]['state'] = 'aborted'
            return {'ok': True}
        raise AssertionError('Unexpected route: ' + route)
    ev.EvalAPI.request = request

    async def trial(config, assignment, run, path, api, **kwargs):
        trials.append(run['side'])
        path.mkdir(parents=True, exist_ok=True)
        (path / 'frames.jsonl').write_text('{"frame":0,"seconds":0}\n')
        (path / 'recording-status.json').write_text('{"complete":true}')
        (path / 'recording-context.json').write_text(json.dumps({'fps': 15, 'robot_type': robot,
            'test': True, 'action_space': 'joint_position', 'execution_enabled': False}))
        for remote_run in assignments[assignment['id']]['runs']:
            if remote_run['id'] == run['id']:
                remote_run['state'] = 'finished'
        run['state'] = 'finished'
    ev.run_trial = trial

    def export(path, *args, **kwargs):
        exports.append((path.name, kwargs['metadata']['outcome']))
        video = path / 'lerobot/videos/observation.images.head_image/chunk-000/file-000.mp4'
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b'offline-video-path-fixture')
        return path / 'lerobot'
    lx.export_trial = export

    runtime = Runtime(station)
    runtime.c.PROMPTS.ask = lambda prompt='': ''
    form = {'instruction': 'offline contract task', 'scene': 'offline', 'evaluator': '甲', 'max_steps': 2}
    runtime.start(form)
    runtime.c.RECORDER['thread'].join(15)
    assert not runtime.c.recording()
    assert runtime.c.S.run['phase'] == 'done', runtime.c.S.run
    eid = runtime.c.S.run['eval_id']
    assert trials == ['A', 'B'] and exports == []
    assert not any(route.endswith('/result') for _, route, _ in calls)
    assert runtime.store.stats()['rows'] == []
    with_exception = False
    try:
        runtime.start({**form, 'evaluator': '乙'})
    except PendingEvaluation:
        with_exception = True
    assert with_exception
    assert runtime.store.get(eid)['person'] == '甲'
    runtime.act(eid, {'action': 'save', 'score_A': 100, 'score_B': 50, 'preference': 'A',
                      'feedback': 'Offline test.', 'notes': {'A': 'first', 'B': 'second'}, 'factors': {'speed': 'A1'}})
    # Simplified UI no longer sends notes/factors. Existing saved metadata must survive.
    runtime.act(eid, {'action': 'save', 'score_A': 100, 'score_B': 50, 'preference': 'A',
                      'feedback': 'One overall comment.'})
    notes = json.loads((runtime.root / eid / 'review-notes.json').read_text())
    assert notes['A'] == 'first' and notes['factors']['speed'] == 'A1'
    if scenario == 'lost_response':
        try:
            submit_job(station, eid, 'submit')
        except TimeoutError:
            pass
        else:
            raise AssertionError('Expected injected lost response')
        assert runtime.store.get(eid)['state'] == 'unknown'
        assert runtime.store.stats()['rows'] == []
    submit_job(station, eid, 'submit')
    assert len(exports) == 2
    assert trials == ['A', 'B']  # review must not run hardware again
    assert runtime.store.stats()['rows'][0]['count'] == 1
    assert len([p for m, p, b in calls if p.endswith('/result')]) == 1
    submit_job(station, eid, 'submit')
    assert len([p for m, p, b in calls if p.endswith('/result')]) == 1
    detail = runtime.detail(eid)
    assert detail['state'] == 'submitted'
    assert all(r['cams'] == ['head_image'] and r['recorded'] for r in detail['runs'])
    assert runtime.video_path(eid, detail['runs'][0]['id'], 'head_image').exists()
    runtime.start(form)
    runtime.c.RECORDER['thread'].join(15)
    eid2 = runtime.c.S.run['eval_id']
    submit_job(station, eid2, 'discard', 'offline discard test')
    assert runtime.store.pending() == []
    assert (runtime.root / eid2 / 'manifest.json').exists()
    assert runtime.store.stats()['rows'][0]['count'] == 1
    runtime.dispatch('shutdown', {})
    print('PASS', robot, scenario, 'actual evaluation loop; fake Router/trials; no hardware/network')
