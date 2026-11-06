import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from error_recovery import cleanup
from runtime import Runtime
from store import Store


def fixture(tmp_path):
    root = tmp_path / 'evals'
    folder = root / 'ev_failed'
    folder.mkdir(parents=True)
    store = Store(tmp_path / 'stats.db')
    store.register('ev_failed', 'franka', 'test')
    data = {'assignment': {'id': 'ev_failed', 'runs': [{'id': 'run_A'}, {'id': 'run_B'}]},
            'error_recovery': {'mode': 'local_restart', 'cleanup_complete': False}}
    (folder / 'manifest.json').write_text(json.dumps(data))
    for name in ('run_A', 'run_B', 'ui-initial-scene'):
        (folder / name).mkdir()
        (folder / name / 'recording').write_text('capture')
    cache = tmp_path / 'eval_review_cache/ev_failed/run_A'
    cache.mkdir(parents=True)
    (cache / 'preview.mp4').write_bytes(b'video')
    (folder / 'diagnostic.log').write_text('error')
    return root, folder, store, data


def test_deletes_only_failed_captures_without_router_and_is_idempotent(tmp_path):
    root, folder, store, data = fixture(tmp_path)
    (root / 'ev_other').mkdir()
    cleanup(root, folder.name, store)
    cleanup(root, folder.name, store)
    assert sorted(p.name for p in folder.iterdir()) == ['diagnostic.log', 'manifest.json']
    assert (root / 'ev_other').is_dir()
    assert not (tmp_path / 'eval_review_cache/ev_failed').exists()


@pytest.mark.parametrize('change', ['no_local_intent', 'submitted', 'uploaded', 'escape'])
def test_invalid_cleanup_never_deletes_capture(tmp_path, change):
    root, folder, store, data = fixture(tmp_path)
    if change == 'no_local_intent':
        data.pop('error_recovery')
    elif change in ('submitted', 'uploaded'):
        data[change] = True
    else:
        data['assignment']['runs'][1]['id'] = '../other'
    (folder / 'manifest.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cleanup(root, folder.name, store)
    assert (folder / 'run_A/recording').exists()


def test_symlink_refused_before_any_deletion(tmp_path):
    root, folder, store, data = fixture(tmp_path)
    try:
        (folder / 'run_B/link').symlink_to(tmp_path / 'outside')
    except OSError:
        pytest.skip('OS does not permit creating symlinks')
    with pytest.raises(ValueError, match='Linked'):
        cleanup(root, folder.name, store)
    assert (folder / 'run_A/recording').exists()


@pytest.mark.parametrize('case', ['recording', 'router_busy', 'submitted', 'intent', 'healthy', 'foreign'])
def test_restart_guards_before_writes(case):
    runtime = object.__new__(Runtime)
    class Conflict(Exception):
        pass
    row = dict(robot='franka', confirmed_at=None, intent=None)
    document = {'recording_error': 'injected failure'}
    if case in ('submitted', 'intent'):
        row['confirmed_at' if case == 'submitted' else 'intent'] = 'pending'
    if case == 'healthy':
        document = {}
    if case == 'foreign':
        row['robot'] = 'yam'
    runtime.station = SimpleNamespace(robot='franka')
    runtime.store = SimpleNamespace(get=lambda eid: row)
    runtime.c = SimpleNamespace(HTTPException=Conflict, recording=lambda: case == 'recording',
        rv=SimpleNamespace(JOBS={'other': None}, busy=lambda eid: case == 'router_busy', load=lambda eid: document),
        S=SimpleNamespace(run={'phase': 'done', 'eval_id': 'ev'}))
    with pytest.raises(Conflict):
        runtime.restart_failed('ev')
