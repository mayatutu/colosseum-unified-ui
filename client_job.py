"""One real Client submit/discard job, in that station's existing interpreter."""
import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from station import Station
from store import Store
from submission import install_api_hook, mark_manifest, reconcile
from evaluation_lock import evaluation_lock
from contextlib import nullcontext
from task_annotations import annotate_exports, difficulty
import scene_reference


def run(station, eid, action, reason=''):
    sys.path.insert(0, str(station.file('client_root') / 'src'))
    os.chdir(station.file('client_root'))
    import colosseum_client.evaluation as ev
    from colosseum_client.robot_config import RobotClientConfig
    config = station.load_client_config()
    store = Store(station.file('database'))
    row = store.get(eid)
    if row:
        config = replace(config, evaluator=row['person'])
    root = Path(config.evaluation_dir).resolve()
    with evaluation_lock(root / eid):
        if action == 'submit' and station.robot == 'franka':
            document = json.loads((root / eid / 'manifest.json').read_text(encoding='utf-8'))
            difficulty(document.get('task_difficulty'), required=True)
            import colosseum_client.lerobot_export as exporter
            annotation = annotate_exports(exporter)
        else:
            annotation = nullcontext()
        with annotation:
            result = execute(ev, config, store, root, eid, action, reason)
        if station.robot == 'franka':
            try:
                scene_reference.cleanup(root / eid, closed=action == 'discard')
            except (OSError, ValueError) as exc:
                print('Initial scene cleanup: ' + str(exc))
        return result


def execute(ev, config, store, root, eid, action, reason):
    if action == 'discard':
        row = store.get(eid)
        if row and row['confirmed_at']:
            raise ValueError('This evaluation is already submitted')
        if row and row['discard_reason']:
            api = ev.EvalAPI(config)
            try:
                state = reconcile(api, store, root, eid)
                if state == 'discarded':
                    return
                if state == 'unknown':
                    raise RuntimeError('Discard status is unknown; query the Router again before retrying')
            finally:
                api.close()
        store.discard_intent(eid, reason)
    if action == 'submit':
        api = ev.EvalAPI(config)
        try:
            state = reconcile(api, store, root, eid)
            if state == 'submitted':
                print('Result already confirmed. Dataset upload remains on the existing upload path.')
                return
            if state == 'unknown':
                raise RuntimeError('Submission status is unknown; query the Router again before retrying')
            assignment = api.request('GET', '/assignments/' + eid)
            if assignment.get('state') != 'pending' or any(r.get('state') != 'finished' for r in assignment['runs']):
                raise ValueError('Both Router runs must be finished before submitting scores')
        finally:
            api.close()
    original_request = install_api_hook(ev, store, root)

    def answer(prompt=''):
        if action == 'discard' and prompt.startswith('Reason'):
            return reason
        if prompt.startswith('Continue with the next evaluation'):
            return 'n'
        raise RuntimeError('Unexpected Client prompt during review: ' + prompt)
    previous_input = ev.__dict__.get('input')
    ev.input = answer
    try:
        ev.run_evaluation(config, **({'resume': eid} if action == 'submit' else {'abort': eid}))
    except BaseException:
        if action == 'discard':
            store.state(eid, 'unknown')
        raise
    finally:
        ev.EvalAPI.request = original_request
        if previous_input is None:
            ev.__dict__.pop('input', None)
        else:
            ev.input = previous_input
    if action == 'discard':
        store.discard(eid)
        mark_manifest(root, eid, discarded=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--station', required=True)
    p.add_argument('--id', required=True)
    p.add_argument('--action', choices=['submit', 'discard'], required=True)
    a = p.parse_args()
    body = json.loads(sys.stdin.readline() or '{}')
    run(Station.load(a.station), a.id, a.action, body.get('reason', ''))
