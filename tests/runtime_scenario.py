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
client = Path(os.environ.get('COLOSSEUM_TEST_' + robot.upper() + '_CLIENT',
                             os.environ.get('COLOSSEUM_TEST_CLIENT', str(ROOT.parent / 'client'))))
sys.path.insert(0, str(client / 'src'))
import colosseum_client.evaluation as ev
import colosseum_client.lerobot_export as lx

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
        if scenario == 'error_restart' and len(assignments) == 1:
            raise RuntimeError('Injected controller return-home timeout')
        if scenario == 'manual_finish' or scenario.startswith('early_stop'):
            runtime.c.S.set_run(phase='running')
            stopped = scenario.startswith('early_stop') and len(assignments) == 1 and run['side'] == ('B' if scenario.endswith('_b') else 'A')
            runtime.dispatch('finish', {'reason': 'stopped' if stopped else 'completed', 'expected_eid': assignment['id']})
            assert runtime.c.PROMPTS.finish_now.is_set()
            if stopped:
                assert runtime.round_stop_pending
                assert (path / 'frames.jsonl').exists(), 'Cleanup ran before trial release'
                assert not json.loads((path.parent / 'manifest.json').read_text()).get('discarded')
                await asyncio.sleep(.05)
                if scenario == 'early_stop_cleanup_error':
                    raise RuntimeError('Injected robot release failure')
        for remote_run in assignments[assignment['id']]['runs']:
            if remote_run['id'] == run['id']:
                remote_run['state'] = 'finished'
        run['state'] = 'finished'
    ev.run_trial = trial

    def export(path, *args, **kwargs):
        exports.append((path.name, kwargs['metadata']['outcome']))
        if robot == 'franka':
            assert kwargs['metadata']['task_difficulty'] == 7
            assert kwargs['metadata']['task_difficulty_scale'] == 10
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
    if scenario.startswith('early_stop'):
        runtime.round_stop_thread.join(10)
        assert not runtime.round_stop_thread.is_alive()
        eid = next(iter(assignments))
        folder = runtime.root / eid
        document = json.loads((folder / 'manifest.json').read_text())
        assert trials == (['A', 'B'] if scenario.endswith('_b') else ['A'])
        assert not exports and not any(p.endswith(('/result', '/abort')) for _, p, _ in calls)
        if scenario == 'early_stop_cleanup_error':
            assert runtime.c.S.run['phase'] == 'error' and not document.get('discarded')
            assert (folder / assignments[eid]['runs'][0]['id'] / 'frames.jsonl').exists()
            assert not runtime.round_stop_pending
            runtime.dispatch('shutdown', {})
            print('PASS', robot, scenario, 'real cleanup error remains visible; no false new round')
            sys.exit(0)
        assert document['discarded'] and document['error_recovery']['cleanup_complete']
        assert not any((folder / r['id']).exists() for r in assignments[eid]['runs'])
        assert runtime.c.S.run['phase'] == 'idle' and runtime.c.S.run['eval_id'] is None
        assert runtime.c.S.run['restarted_from'] == eid and runtime.c.S.run['instruction'] == ''
        assert runtime.store.pending() == [] and runtime.store.stats()['rows'] == []
        assert len(assignments) == 1
        runtime.start({**form, 'instruction': 'Different new task'})
        runtime.c.RECORDER['thread'].join(15)
        assert runtime.c.S.run['phase'] == 'done'
        assert len(assignments) == 2 and not runtime.c.S.run.get('restarted_from')
        runtime.dispatch('shutdown', {})
        print('PASS', robot, scenario, 'whole-round stop waits for release, deletes locally, requires explicit new start')
        sys.exit(0)
    if scenario == 'error_restart':
        eid = runtime.c.S.run['eval_id']
        assert runtime.c.S.run['phase'] == 'error' and trials == ['A']
        folder = runtime.root / eid
        captured = folder / assignments[eid]['runs'][0]['id']
        assert (captured / 'frames.jsonl').exists()
        runtime.router = lambda *args: (_ for _ in ()).throw(AssertionError('No abort/confirmation job allowed'))
        previous_calls = copy.deepcopy(calls)
        runtime.act(eid, {'action': 'restart'})
        assert not captured.exists()
        assert json.loads((folder / 'manifest.json').read_text())['error_recovery']['cleanup_complete']
        assert runtime.c.S.run['phase'] == 'idle' and runtime.c.S.run['eval_id'] is None
        assert runtime.c.S.run['instruction'] == '' and not runtime.c.recording()
        assert trials == ['A'] and calls == previous_calls and exports == []
        assert runtime.store.pending() == [] and runtime.store.stats()['rows'] == []
        assert runtime.act(eid, {'action': 'restart'})['cleanup_complete']
        assert len(assignments) == 1 and calls == previous_calls
        runtime.start({**form, 'instruction': 'A completely different task', 'scene': 'new scene'})
        runtime.c.RECORDER['thread'].join(15)
        new_id = runtime.c.S.run['eval_id']
        assert new_id != eid and runtime.c.S.run['phase'] == 'done'
        assert assignments[new_id]['task']['instruction'] == 'A completely different task'
        assert assignments[new_id]['scene'] == 'new scene'
        assert trials == ['A', 'A', 'B']
        runtime.dispatch('shutdown', {})
        print('PASS', robot, scenario, 'local delete -> blank idle; new task only after explicit start')
        sys.exit(0)
    assert runtime.c.S.run['phase'] == 'done', runtime.c.S.run
    eid = runtime.c.S.run['eval_id']
    assert trials == ['A', 'B'] and exports == []
    if scenario == 'manual_finish':
        for run in assignments[eid]['runs']:
            marker = json.loads((runtime.root / eid / run['id'] / 'operator-stop.json').read_text())
            assert marker['reason'] == 'completed'
        assert not json.loads((runtime.root / eid / 'manifest.json').read_text()).get('recording_error')
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
                      'feedback': 'One overall comment.', 'task_difficulty': 7})
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
