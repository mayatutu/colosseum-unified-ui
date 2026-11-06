from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import SimpleNamespace
import threading

import numpy as np
import pytest
import yaml
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import create_app
import feishu_reporting as reporting
from runtime import Runtime
from scene_settings import read_scene, save_scene
import scene_reference
from store import Store
from test_api import FakeBridge
from test_station_hub import fixture_app


@pytest.mark.parametrize('old', ['scene: old # retain this comment\n', 'scene: |\n  old\n', ''])
def test_text_scene_roundtrip_preserves_other_yaml_and_private_backup(tmp_path, old):
    path = tmp_path / 'robot.yaml'
    original = ('# private settings\n' + old + 'router: "leave:this:unchanged" # exact\nsecret: "unit-test-only"\n').encode()
    path.write_bytes(original)
    path.chmod(0o600)
    before = yaml.safe_load(original)
    assert save_scene(path, ' 沙发旁 # 1: 冰箱旁 ', before.get('scene', '')) == '沙发旁 # 1: 冰箱旁'
    assert read_scene(path) == '沙发旁 # 1: 冰箱旁'
    assert yaml.safe_load(path.read_bytes()) == {**before, 'scene': '沙发旁 # 1: 冰箱旁'}
    assert b'router: "leave:this:unchanged" # exact\nsecret: "unit-test-only"\n' in path.read_bytes()
    assert next(tmp_path.glob('.robot.yaml.before-scene-*')).read_bytes() == original
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600


def test_stale_tab_and_invalid_scene_cannot_overwrite_config(tmp_path):
    path = tmp_path / 'robot.yaml'
    path.write_text('scene: 沙发旁\nkey: secret\n', encoding='utf-8')
    original = path.read_bytes()
    for value, expected in [('冰箱旁', 'old'), ('', '沙发旁'), (12, '沙发旁'), ('x'*4001, '沙发旁')]:
        with pytest.raises(ValueError):
            save_scene(path, value, expected)
        assert path.read_bytes() == original
    assert not list(tmp_path.glob('.*'))


def test_scene_request_is_station_scoped_and_ignores_client_paths(tmp_path):
    app, bridge = fixture_app(tmp_path, 'franka')
    with TestClient(app) as client:
        sid = client.get('/api/station-info').json()['id']
        result = client.post('/s/'+sid+'/api/scene', json={'scene':'沙发旁', 'expected_scene':'old'})
        assert result.status_code == 200
        assert bridge.calls == [('save_scene', {'scene':'沙发旁','expected_scene':'old'})]


def test_saving_scene_during_recording_is_rejected_before_disk_access():
    runtime = object.__new__(Runtime)
    runtime.station = SimpleNamespace(robot='franka')
    runtime.lock = threading.RLock()
    runtime.c = SimpleNamespace(recording=lambda: True, HTTPException=HTTPException)
    with pytest.raises(HTTPException) as error:
        runtime.dispatch('save_scene', {'scene': '冰箱旁', 'path':'ignored'})
    assert error.value.status_code == 409


def task(tmp_path):
    folder = tmp_path / 'ev_test'
    folder.mkdir()
    (folder/'manifest.json').write_text(json.dumps({'assignment':{'id':folder.name,
        'task':{'instruction':'Put the cup on the table'}, 'scene':'沙发旁',
        'runs':[{'id':'run_A','side':'A'},{'id':'run_B','side':'B'}]}}))
    (folder/'ui-origin.json').write_text(json.dumps({'feishu':{'enabled':True,'scenario':'沙发旁','device':'F2'}}))
    scene_reference.capture(folder, {'left_image':np.full((10,12,3),12,dtype=np.uint8),
                                      'right_image':np.full((10,12,3),240,dtype=np.uint8)})
    for side in ('A','B'):
        run = folder / ('run_'+side)
        run.mkdir()
        (run/'frames.jsonl').write_text('data')
        (run/'recording-status.json').write_text('{"complete":true}')
    store = Store(tmp_path/'stats.db')
    store.register(folder.name, 'franka', 'T3')
    payload={'outcomes':{'A':{'partial_success':0.8},'B':{'partial_success':0.4}},
             'preference':'A','feedback':'A completed more of the task.'}
    store.intent(folder.name,payload)
    store.confirm(folder.name,payload)
    return folder, store


def test_confirmed_report_uses_exact_photos_text_scene_then_deletes_only_temporary_files(tmp_path):
    folder,store=task(tmp_path)
    originals={side:scene_reference.image_path(folder,side+'_image').read_bytes() for side in ('left','right')}
    assert scene_reference.cleanup(folder) is False
    calls=[]
    def sender(value):
        calls.append(value)
        assert value['scenario']=='沙发旁' and value['device']=='F2' and value['evaluator']=='T3'
        assert (value['score_a'],value['score_b'],value['prefer'])==(80,40,'A')
        for side in ('left','right'):
            assert Path(value['scene_'+side]).read_bytes()==originals[side]
            assert Path(value['scene_'+side]).name=='000000.png'
        print('[feishu] submitting: test-receipt')
        return True
    reporting.submit(None,folder,store.get(folder.name),sender)
    assert reporting.status(folder)['status']=='sent'
    assert scene_reference.describe(folder) is None
    assert not (folder/reporting.PHOTOS).exists()
    assert (folder/'run_A/frames.jsonl').read_text()=='data'
    reporting.submit(None,folder,store.get(folder.name),sender)
    assert len(calls)==1 and store.stats()['rows'][0]['count']==1


@pytest.mark.parametrize('clicked,expected',[(False,'error'),(True,'unknown')])
def test_failed_feishu_preserves_photos_and_never_reposts_router_or_form_automatically(tmp_path,clicked,expected):
    folder,store=task(tmp_path)
    calls=[]
    def sender(value):
        calls.append(value)
        if clicked: print('[feishu] submitting: possible-write')
        raise TimeoutError('fake network failure')
    reporting.submit(None,folder,store.get(folder.name),sender)
    assert reporting.status(folder)['status']==expected
    assert scene_reference.describe(folder)
    assert scene_reference.cleanup(folder) is False
    reporting.submit(None,folder,store.get(folder.name),sender)
    assert len(calls)==1
    assert store.get(folder.name)['state']=='submitted'
    if clicked:
        with pytest.raises(ValueError): reporting.retry(folder)
    reporting.retry(folder,checked_missing=clicked)
    assert reporting.status(folder)['status']=='queued'


def test_history_without_opt_in_is_never_reported_and_discard_still_cleans(tmp_path):
    folder,store=task(tmp_path)
    (folder/'ui-origin.json').write_text('{}')
    assert reporting.status(folder)['status']=='not_enabled'
    reporting.submit(None,folder,store.get(folder.name),lambda e:pytest.fail('No historical reporting'))
    assert scene_reference.cleanup(folder,closed=True)


def test_original_device_options_and_text_scene_are_used_without_tokens_in_response(tmp_path):
    (tmp_path/'config.yaml').write_text(yaml.safe_dump({'devices':[{'name':'F1'},{'name':'F2'}],
        'feishu':{'enabled':True,'form_url':'https://example.invalid/private-form','form_token':'private-test-token'}}))
    station=SimpleNamespace(robot='franka',data={'feishu_reporting_enabled':True,'maintenance':{'root':str(tmp_path)}})
    assert reporting.options(station)=={'enabled':True,'devices':['F1','F2']}
    assert reporting.selection(station,{'scene':'冰箱旁','feishu_device':'F2'})=={'enabled':True,'scenario':'冰箱旁','device':'F2'}
    with pytest.raises(ValueError): reporting.selection(station,{'scene':'沙发旁','feishu_device':'F3'})


def test_confirmation_triggers_only_opted_in_feishu_job_without_starting_an_evaluation(tmp_path, monkeypatch):
    folder, store = task(tmp_path)
    runtime = object.__new__(Runtime)
    runtime.root, runtime.store, runtime.closed = tmp_path, store, threading.Event()
    runtime.station = SimpleNamespace(path=tmp_path/'station.yaml', data={'maintenance':{'python':'legacy-python'}})
    calls=[]
    def run(command, **kwargs):
        calls.append(command)
        runtime.closed.set()
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('runtime.subprocess.run',run)
    runtime.report_feishu_loop()
    assert len(calls)==1
    assert calls[0][0]=='legacy-python' and calls[0][-1]==str(folder)
    assert calls[0][3].endswith('feishu_reporting.py')
    assert store.get(folder.name)['state']=='submitted'
