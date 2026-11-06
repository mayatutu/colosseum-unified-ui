import io
import json
import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import station_hub as hub
from hub_fixture import fixture_app


def test_registry_identity_survives_restart_and_rename(tmp_path):
    r = hub.Registry(tmp_path/'registry.db', 'yam', 'YAM')
    sid = r.local_id
    r.save({'id': sid, 'name': 'Bench YAM'})
    again = hub.Registry(tmp_path/'registry.db', 'yam', 'ignored default')
    assert again.local_id == sid and again.get(sid)['name'] == 'Bench YAM'
    remote = again.save({'name': 'Franka', 'address': 'franka-client.example.invalid'})
    assert remote['url'] == 'http://franka-client.example.invalid:8772'
    with pytest.raises(HTTPException): again.save({'name': 'Duplicate', 'address': remote['url']})


@pytest.mark.parametrize('address', ['http://name/unsafe', 'file:///etc/passwd', 'http://user:secret@name', 'http://host:bad'])
def test_invalid_address_rejected(address):
    with pytest.raises((HTTPException, ValueError)): hub.normalize_address(address)


def test_remote_identity_change_does_not_redirect_actions(tmp_path, monkeypatch):
    r = hub.Registry(tmp_path/'registry.db', 'yam', 'YAM')
    row = r.save({'name': 'F', 'address': 'franka-client.example.invalid'})
    info = {'id': str(uuid.uuid4()), 'protocol': 1, 'robot': 'franka'}
    monkeypatch.setattr(hub, 'get_json', lambda *a, **k: info)
    r.identify(row)
    row = r.get(row['id'])
    info['id'] = str(uuid.uuid4())
    with pytest.raises(ValueError, match='identity changed'): r.identify(row)


def test_local_prefixed_calls_use_local_bridge_and_identity_is_passive(tmp_path):
    app, bridge = fixture_app(tmp_path, 'yam')
    with TestClient(app) as client:
        identity = client.get('/api/station-info').json()
        assert bridge.calls == []
        prefix = '/s/' + identity['id']
        assert 'robotPicker' in client.get('/').text
        assert 'v-review' in client.get(prefix+'/').text
        assert client.post(prefix+'/api/eval/start', json={'instruction': 'fixture'}).status_code == 200
        assert bridge.recording
        with client.websocket_connect(prefix+'/ws') as ws:
            assert ws.receive_json()['recording'] is True
        assert bridge.recording  # closing the browser connection is not a stop operation


def test_remote_mutations_range_and_offline_never_fall_back_to_local(tmp_path, monkeypatch):
    app, bridge = fixture_app(tmp_path, 'yam')
    row = app.state.registry.save({'name': 'F', 'address': 'franka-client.example.invalid'})
    monkeypatch.setattr(hub, 'get_json', lambda *a, **k: {'id': str(uuid.UUID(int=1)), 'protocol': 1, 'robot': 'franka'})
    requests = []
    class Reply(io.BytesIO):
        status = 206
        headers = {'Content-Type': 'video/mp4', 'Content-Range': 'bytes 2-4/10', 'Accept-Ranges': 'bytes'}
    def open_url(url, **kwargs):
        requests.append((url, kwargs))
        return Reply(b'234')
    monkeypatch.setattr(hub, 'open_url', open_url)
    with TestClient(app) as client:
        prefix = '/s/' + row['id']
        r = client.get(prefix+'/video/e/r/head_image', headers={'Range': 'bytes=2-4'})
        assert r.status_code == 206 and r.content == b'234'
        assert r.headers['content-range'] == 'bytes 2-4/10'
        assert requests[-1][1]['headers']['range'] == 'bytes=2-4'
        client.post(prefix+'/api/eval/start', json={'instruction': 'remote fixture'})
        assert requests[-1][0] == 'http://franka-client.example.invalid:8772/api/eval/start'
        assert json.loads(requests[-1][1]['data']) == {'instruction': 'remote fixture'}
        assert not bridge.recording and bridge.calls == []
        def offline(*a, **k): raise OSError('unreachable')
        monkeypatch.setattr(hub, 'get_json', offline)
        assert client.post(prefix+'/api/eval/start', json={}).status_code == 503
        assert len(requests) == 2 and bridge.calls == []


def test_stats_preserve_offline_sources_and_no_network_on_list_without_checks(tmp_path, monkeypatch):
    app, bridge = fixture_app(tmp_path, 'yam')
    row = app.state.registry.save({'name': 'Franka offline', 'address': 'franka-client.example.invalid'})
    def offline(*a, **k): raise OSError('offline')
    monkeypatch.setattr(hub, 'get_json', offline)
    with TestClient(app) as client:
        assert len(client.get('/hub/stations?check=false').json()['items']) == 2
        result = client.get('/hub/statistics').json()
        assert len(result['rows']) == 1
        assert next(s for s in result['sources'] if s['id'] == row['id'])['available'] is False
        assert bridge.calls == []


def test_uncertain_remote_post_is_never_retried(tmp_path, monkeypatch):
    app, bridge = fixture_app(tmp_path, 'yam')
    row = app.state.registry.save({'name': 'F', 'address': 'franka-client.example.invalid'})
    monkeypatch.setattr(hub, 'get_json', lambda *a, **k: {'id': str(uuid.UUID(int=2)), 'protocol': 1, 'robot': 'franka'})
    sent = []
    def timeout(url, **kwargs):
        sent.append(url)
        raise TimeoutError('Response lost after mutation')
    monkeypatch.setattr(hub, 'open_url', timeout)
    with TestClient(app) as client:
        response = client.post('/s/'+row['id']+'/api/evals/e', json={'action': 'submit'})
        assert response.status_code == 502
        assert len(sent) == 1 and bridge.calls == []
