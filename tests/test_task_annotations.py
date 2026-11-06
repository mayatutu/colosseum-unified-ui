import json
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import create_app
from runtime import Runtime
from task_annotations import difficulty, save_difficulty, annotate_exports
import scene_reference as reference


def task(tmp_path):
    folder = tmp_path / 'ev_test'
    folder.mkdir()
    (folder / 'manifest.json').write_text(json.dumps({'assignment': {'id': folder.name,
        'runs': [{'id': 'run_A', 'side': 'A'}, {'id': 'run_B', 'side': 'B'}]}}))
    (folder / 'ui-origin.json').write_text('{"scene_reference_required":true}')
    return folder


def photos():
    return {'left_image': np.full((18, 24, 3), [255, 0, 0], dtype=np.uint8),
            'right_image': np.full((18, 24, 3), [0, 0, 255], dtype=np.uint8)}


@pytest.mark.parametrize('value', [0, 11, -1, 1.5, True, False, '1/10', '1.5', 'NaN'])
def test_difficulty_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        difficulty(value)


def test_one_task_difficulty_persists_and_enters_both_exports(tmp_path):
    folder = task(tmp_path)
    assert difficulty('10') == 10
    assert difficulty('', required=False) is None
    with pytest.raises(ValueError):
        difficulty('', required=True)
    save_difficulty(folder, difficulty('7'))
    seen = []
    def export(path, **kwargs):
        seen.append(kwargs['metadata'])
        return path / 'lerobot'
    module = SimpleNamespace(export_trial=export)
    with annotate_exports(module):
        for side in ('A', 'B'):
            module.export_trial(folder / ('run_'+side), metadata={'side': side, 'outcome': {'success': True}})
    assert module.export_trial is export
    assert [x['task_difficulty'] for x in seen] == [7, 7]
    assert all(x['task_difficulty_scale'] == 10 for x in seen)
    assert seen[0]['outcome'] == {'success': True}
    assert json.loads((folder / 'manifest.json').read_text())['task_difficulty'] == 7


def test_exported_annotation_is_frozen_and_failed_export_restores_function(tmp_path):
    folder = task(tmp_path)
    save_difficulty(folder, 2)
    marker = folder / 'run_A/lerobot/meta/colosseum.json'
    marker.parent.mkdir(parents=True)
    marker.write_text('{"task_difficulty":2}')
    save_difficulty(folder, 2)
    with pytest.raises(ValueError, match='cannot change'):
        save_difficulty(folder, 3)
    def fail(*a, **k):
        raise OSError('encoder failed')
    module = SimpleNamespace(export_trial=fail)
    with pytest.raises(OSError), annotate_exports(module):
        module.export_trial(folder / 'run_B', metadata={})
    assert module.export_trial is fail


def test_references_survive_resume_then_only_owned_files_are_removed(tmp_path):
    folder = task(tmp_path)
    reference.capture(folder, photos())
    saved = reference.describe(folder)
    reference.capture(folder, {k: np.zeros_like(v) for k, v in photos().items()})
    assert reference.describe(folder) == saved
    assert Image.open(reference.image_path(folder, 'left_image')).getpixel((0, 0)) == (255, 0, 0)
    assert reference.image_path(folder, '../manifest') is None
    extra = folder / reference.DIRECTORY / 'unrelated.txt'
    extra.write_text('keep')
    for side in ('A', 'B'):
        path = folder / ('run_'+side)
        path.mkdir()
        (path / 'frames.jsonl').write_text('recorded numeric data')
        (path / 'recording-status.json').write_text('{"complete":true}')
        if side == 'A':
            assert reference.cleanup(folder) is False
    assert reference.cleanup(folder) is True
    assert reference.describe(folder) is None
    assert extra.read_text() == 'keep'
    assert (folder / 'run_A/frames.jsonl').read_text() == 'recorded numeric data'
    assert not list(folder.glob('*/lerobot/**/*'))


def test_partial_capture_cannot_publish_a_single_reference(tmp_path, monkeypatch):
    folder = task(tmp_path)
    original = Image.Image.save
    def save(image, path, *a, **kw):
        if Path(path).name == 'right_image.png':
            raise OSError('disk full')
        return original(image, path, *a, **kw)
    monkeypatch.setattr(Image.Image, 'save', save)
    with pytest.raises(OSError):
        reference.capture(folder, photos())
    assert reference.describe(folder) is None
    assert not list(folder.glob('.ui-initial-scene-*'))


def runtime(tmp_path):
    folder = task(tmp_path)
    r = object.__new__(Runtime)
    r.root, r.lock, r.last_replied_prompt = tmp_path, threading.RLock(), None
    r.station = SimpleNamespace(robot='franka')
    state = SimpleNamespace(lock=threading.RLock(), run={'eval_id': folder.name},
                            prompt={'id': 101, 'kind': 'scene', 'side': 'A'})
    events = []
    r.c = SimpleNamespace(S=state, known=lambda eid: eid,
        rv=SimpleNamespace(load=lambda eid: json.loads((folder / 'manifest.json').read_text())),
        HTTPException=HTTPException, reply=lambda body: events.append('reply') or {'ok': True})
    r.camera_reader = lambda: (lambda: photos(), lambda: events.append('closed'))
    return r, folder, events


def test_scene_confirm_capture_before_release_and_b_reuses_original(tmp_path):
    r, folder, events = runtime(tmp_path)
    r.reply({'id': 101, 'kind': 'scene', 'answer': ''})
    assert events == ['closed', 'reply']
    assert reference.describe(folder)
    with pytest.raises(HTTPException):
        r.reply({'id': 101, 'kind': 'scene', 'answer': ''})
    r.c.S.prompt = {'id': 102, 'kind': 'scene', 'side': 'B'}
    r.camera_reader = lambda: pytest.fail('B must not open or replace the reference camera images')
    r.reply({'id': 102, 'kind': 'scene', 'answer': ''})
    assert events == ['closed', 'reply', 'reply']


def test_large_prompt_identifier_round_trips_as_text(tmp_path):
    r, folder, events = runtime(tmp_path)
    r.c.S.prompt['id'] = 1793939937123456789
    r.reply({'id': '1793939937123456789', 'kind': 'scene', 'answer': ''})
    assert events == ['closed', 'reply']


def test_capture_failure_keeps_confirmation_pending_and_camera_closed(tmp_path):
    r, folder, events = runtime(tmp_path)
    r.camera_reader = lambda: (lambda: {}, lambda: events.append('closed'))
    with pytest.raises(ValueError):
        r.reply({'id': 101, 'kind': 'scene', 'answer': ''})
    assert events == ['closed'] and r.last_replied_prompt is None
    assert r.c.S.prompt['id'] == 101 and reference.describe(folder) is None
    r.reply({'id': 101, 'kind': 'scene', 'answer': None})
    assert events == ['closed', 'reply']


def test_missing_b_reference_or_stale_prompt_never_releases_trial(tmp_path):
    r, folder, events = runtime(tmp_path)
    r.c.S.prompt.update(side='B')
    with pytest.raises(ValueError):
        r.reply({'id': 101, 'kind': 'scene', 'answer': ''})
    with pytest.raises(HTTPException):
        r.reply({'id': 99, 'kind': 'scene', 'answer': ''})
    assert events == []


def test_reference_http_serves_only_owned_images_with_no_cache(tmp_path):
    folder = task(tmp_path)
    reference.capture(folder, photos())
    class Bridge:
        def start(self): pass
        def close(self): pass
        def call(self, method, body):
            assert method == 'scene_reference'
            p = reference.image_path(folder, body['camera'])
            return str(p) if p else None
    with TestClient(create_app(SimpleNamespace(), Bridge())) as client:
        result = client.get('/api/scene-reference/ev_test/left_image.png')
        assert result.status_code == 200 and result.content.startswith(b'\x89PNG')
        assert result.headers['cache-control'] == 'no-store'
        assert client.get('/api/scene-reference/ev_test/head_image.png').status_code == 404
