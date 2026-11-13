"""Feishu sender configuration and lifecycle tests; all sends are simulated."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

import feishu_reporting as reporting
from runtime import Runtime
import scene_reference
from store import Store


def station(tmp_path, *, legacy=False):
    root = tmp_path / 'original-sender'
    root.mkdir()
    (root / 'config.yaml').write_text(yaml.safe_dump({
        'devices': [{'name': 'F1'}, {'name': 'F2'}],
        'feishu': {'enabled': True, 'form_url': 'https://example.invalid/form',
                   'form_token': 'fixture-token-not-returned'},
    }), encoding='utf-8')
    sender = {'root': str(root), 'python': 'original-python'}
    data = {'feishu_reporting_enabled': True}
    if legacy:
        data['maintenance'] = sender
    else:
        data.update(maintenance={'mode': 'candidate'}, feishu_reporting=sender)
    return SimpleNamespace(robot='franka', data=data, path=tmp_path / 'station.yaml')


def confirmed_task(tmp_path):
    folder = tmp_path / 'ev_report'
    folder.mkdir()
    (folder / 'manifest.json').write_text(json.dumps({'assignment': {
        'task': {'instruction': 'Put the cup on the table'},
        'runs': [{'id': 'run_A'}, {'id': 'run_B'}],
    }}), encoding='utf-8')
    (folder / 'ui-origin.json').write_text(json.dumps({
        'feishu': {'enabled': True, 'scenario': '桌子旁', 'device': 'F2'},
    }), encoding='utf-8')
    scene_reference.capture(folder, {
        'left_image': np.full((10, 12, 3), 12, dtype=np.uint8),
        'right_image': np.full((10, 12, 3), 240, dtype=np.uint8),
    })
    for side in ('A', 'B'):
        run = folder / ('run_' + side)
        run.mkdir()
        (run / 'frames.jsonl').write_text('preserve recording', encoding='utf-8')
        (run / 'recording-status.json').write_text('{"complete":true}', encoding='utf-8')
    store = Store(tmp_path / 'stats.db')
    store.register(folder.name, 'franka', 'T3')
    result = {'outcomes': {'A': {'partial_success': .8}, 'B': {'partial_success': .4}},
              'preference': 'A', 'feedback': 'A completed more of the task.'}
    store.intent(folder.name, result)
    store.confirm(folder.name, result)
    return folder, store


@pytest.mark.parametrize('legacy', [False, True])
def test_sender_options_work_with_separate_config_and_legacy_fallback(tmp_path, legacy):
    config = station(tmp_path, legacy=legacy)
    assert reporting.options(config) == {'enabled': True, 'devices': ['F1', 'F2']}
    assert reporting.sender_python(config) == 'original-python'
    assert reporting.selection(config, {'scene': '桌子旁', 'feishu_device': 'F2'}) == {
        'enabled': True, 'scenario': '桌子旁', 'device': 'F2',
    }
    assert 'fixture-token' not in json.dumps(reporting.options(config))
    with pytest.raises(ValueError, match='device'):
        reporting.selection(config, {'scene': '桌子旁', 'feishu_device': 'F3'})


@pytest.mark.parametrize('invalid', [None, {}, [], {'root': 'wrong'},
                                    {'root': 'wrong', 'python': ''},
                                    {'root': 123, 'python': 'python'}])
def test_explicit_invalid_reporting_config_never_falls_back_to_maintenance(tmp_path, invalid):
    config = station(tmp_path, legacy=True)
    config.data['feishu_reporting'] = invalid
    with pytest.raises(ValueError, match='both root and python'):
        reporting.options(config)


def test_disabled_reporting_does_not_load_sender_config():
    config = SimpleNamespace(robot='franka', data={'feishu_reporting': None})
    assert reporting.options(config) == {'enabled': False, 'devices': []}
    config.data['feishu_reporting_enabled'] = True
    config.robot = 'yam'
    assert reporting.options(config) == {'enabled': False, 'devices': []}


def test_confirmed_job_uses_separate_python_and_only_confirmed_opt_in(tmp_path, monkeypatch):
    folder, store = confirmed_task(tmp_path)
    store.register('unconfirmed', 'franka', 'T0')
    runtime = object.__new__(Runtime)
    runtime.root, runtime.store = tmp_path, store
    runtime.station = station(tmp_path)
    class Once:
        closed = False
        def is_set(self):
            return self.closed
        def wait(self, timeout):
            self.closed = True
    runtime.closed = Once()
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('runtime.subprocess.run', run)
    runtime.report_feishu_loop()
    assert len(calls) == 1
    assert calls[0][0] == 'original-python'
    assert calls[0][-1] == str(folder)
    assert store.get('unconfirmed')['confirmed_at'] is None
    assert store.get(folder.name)['state'] == 'submitted'


def test_default_sender_loads_only_reporting_root_and_never_maintenance_lifecycle(tmp_path, monkeypatch):
    folder, store = confirmed_task(tmp_path)
    config = station(tmp_path)
    captures, payloads = [], []
    originals = {side: scene_reference.image_path(folder, side + '_image').read_bytes() for side in ('left', 'right')}
    def sender(value, sender_config):
        payloads.append(value)
        assert (value['score_a'], value['score_b'], value['prefer']) == (80, 40, 'A')
        assert (value['evaluator'], value['scenario'], value['device']) == ('T3', '桌子旁', 'F2')
        for side in ('left', 'right'):
            assert Path(value['scene_' + side]).name == '000000.png'
            assert Path(value['scene_' + side]).read_bytes() == originals[side]
        print('[feishu] submitting: simulated')
        return True
    class SenderHost:
        def __init__(self, root, *args):
            captures.append(root)
        def load_module(self):
            self.module = SimpleNamespace(CFG={'feishu': {'enabled': True}}, submit_feishu=sender)
        def initialize(self):
            pytest.fail('Maintenance lifecycle must not be called by reporting')
    monkeypatch.setattr('legacy_host.LegacyHost', SenderHost)
    reporting.submit(config, folder, store.get(folder.name))
    reporting.submit(config, folder, store.get(folder.name))
    assert captures == [Path(config.data['feishu_reporting']['root'])]
    assert len(payloads) == 1
    assert reporting.status(folder)['status'] == 'sent'
    assert not (folder / reporting.PHOTOS).exists()
    assert scene_reference.describe(folder) is None
    assert (folder / 'run_A/frames.jsonl').read_text() == 'preserve recording'
    assert store.stats()['rows'][0]['count'] == 1


@pytest.mark.parametrize('clicked,expected', [(False, 'error'), (True, 'unknown')])
def test_failure_preserves_photos_and_does_not_automatically_resend(tmp_path, clicked, expected):
    folder, store = confirmed_task(tmp_path)
    calls = []
    def sender(value):
        calls.append(value)
        if clicked:
            print('[feishu] submitting: simulated-uncertain-result')
        raise TimeoutError('Simulated failure')
    reporting.submit(None, folder, store.get(folder.name), sender)
    reporting.submit(None, folder, store.get(folder.name), sender)
    assert len(calls) == 1
    assert reporting.status(folder)['status'] == expected
    assert scene_reference.describe(folder)
    assert store.get(folder.name)['state'] == 'submitted'
    if clicked:
        with pytest.raises(ValueError, match='absent'):
            reporting.retry(folder)
    reporting.retry(folder, checked_missing=clicked)
    assert reporting.status(folder)['status'] == 'queued'


def test_history_without_opt_in_is_never_uploaded(tmp_path):
    folder, store = confirmed_task(tmp_path)
    (folder / 'ui-origin.json').write_text('{}', encoding='utf-8')
    reporting.submit(None, folder, store.get(folder.name), lambda value: pytest.fail('No historical upload'))
    assert reporting.status(folder)['status'] == 'not_enabled'
