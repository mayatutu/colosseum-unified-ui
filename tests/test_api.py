from types import SimpleNamespace
from fastapi.testclient import TestClient
from app import create_app
from bridge import RemoteError
import io
import json
import pytest
import urllib.error


class FakeBridge:
    """Transport unit tests only, never a served demo backend."""
    def __init__(self):
        self.calls = []
    def start(self): pass
    def close(self): pass
    def call(self, method, params=None):
        self.calls.append((method, params))
        if method == 'list':
            return {'items': [{'id': 'ev_test'}], 'total': 1, **params}
        if method == 'maintenance' and params['action'] == 'bad':
            raise RemoteError('not supported', 400)
        return {'ok': True}


def test_original_ui_extended_and_api_is_compatible():
    bridge = FakeBridge()
    with TestClient(create_app(SimpleNamespace(), bridge)) as client:
        page = client.get('/').text
        for marker in ('v-setup', 'v-record', 'v-review', 'v-stats', 'keysUnlock'):
            assert marker in page
        assert 'fieldset id="keyInputs" disabled' in page
        assert client.get('/api/evals').json() == [{'id': 'ev_test'}]
        result = client.get('/api/evals?paginated=true&offset=3&limit=10').json()
        assert result['offset'] == 3 and result['limit'] == 10
        assert client.post('/api/stats', json={'count': 999}).status_code == 405
        assert client.put('/api/stats', json={}).status_code == 405
        assert client.post('/api/evals/x', json={'action': 'save'}).status_code == 200
        assert bridge.calls[-1] == ('act', {'id': 'x', 'body': {'action': 'save'}})
        assert client.post('/api/maintenance/bad').status_code == 400


def test_video_response_supports_seek_range(tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'0123456789')
    bridge = FakeBridge()
    bridge.call = lambda *a, **k: str(video)
    with TestClient(create_app(SimpleNamespace(), bridge)) as client:
        response = client.get('/video/ev/r/head_image', headers={'Range': 'bytes=2-5'})
        assert response.status_code == 206
        assert response.content == b'2345'


@pytest.mark.parametrize('reply,status', [
    ({'ok': True, 'text': 'A completed the task.'}, 200),
    ({'ok': False, 'error': 'quota exceeded'}, 502),
    ({'ok': True, 'text': ''}, 502),
    ([], 502),
    ('invalid json', 502),
    (urllib.error.URLError('connection refused'), 502),
    (TimeoutError('timeout'), 502),
])
def test_translation_reuses_old_ui_without_worker_or_evaluation_writes(monkeypatch, reply, status):
    calls = []
    def open_request(request, timeout):
        calls.append((request.full_url, json.loads(request.data), timeout))
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO((reply if isinstance(reply, str) else json.dumps(reply)).encode())
    monkeypatch.setattr('app.urllib.request.build_opener', lambda *a: SimpleNamespace(open=open_request))
    bridge = FakeBridge()
    station = SimpleNamespace(data={'maintenance': {'url': 'http://127.0.0.1:8080/'}})
    with TestClient(create_app(station, bridge)) as client:
        response = client.post('/api/translate', json={'text': 'A 完成了任务。', 'url': 'https://ignored.invalid'})
    assert response.status_code == status
    assert calls == [('http://127.0.0.1:8080/api/translate', {'text': 'A 完成了任务。'}, 45)]
    assert bridge.calls == []
    if status == 200:
        assert response.json() == {'text': 'A completed the task.'}


def test_translation_empty_input_and_missing_backend_do_not_access_network(monkeypatch):
    def unexpected(*a):
        pytest.fail('No network expected')
    monkeypatch.setattr('app.urllib.request.build_opener', unexpected)
    with TestClient(create_app(SimpleNamespace(data={}), FakeBridge())) as client:
        for text in (None, '', '  ', 12):
            assert client.post('/api/translate', json={'text': text}).status_code == 400
        assert client.post('/api/translate', json={'text': '中文'}).status_code == 503
