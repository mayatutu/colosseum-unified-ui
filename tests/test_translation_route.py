"""Translation forwarding stays independent of candidate service maintenance."""
import io
import json
from types import SimpleNamespace
import urllib.error

from fastapi.testclient import TestClient
import pytest

import app as ui_app


def client(data):
    def unexpected_worker(*args, **kwargs):
        pytest.fail('Translation must not call the robot worker or maintenance')
    return TestClient(ui_app.create_app(SimpleNamespace(data=data),
                                       bridge=SimpleNamespace(call=unexpected_worker)))


@pytest.mark.parametrize('data,expected_url', [
    ({'translation_url': 'http://127.0.0.1:8772/',
      'maintenance': {'url': 'http://127.0.0.1:19080'}}, 'http://127.0.0.1:8772/api/translate'),
    ({'translation_url': 'http://127.0.0.1:8772', 'maintenance': {}},
     'http://127.0.0.1:8772/api/translate'),
    ({'maintenance': {'url': 'http://127.0.0.1:8080/'}},
     'http://127.0.0.1:8080/api/translate'),
])
def test_translation_url_overrides_maintenance_with_legacy_fallback(monkeypatch, data, expected_url):
    seen = []
    def open_request(request, timeout):
        seen.append(request)
        assert request.full_url == expected_url
        assert request.get_method() == 'POST'
        assert json.loads(request.data) == {'text': '原始评语'}
        assert timeout == 45
        return io.BytesIO(json.dumps({'ok': True, 'text': '  Translated comment  '}).encode())
    monkeypatch.setattr(ui_app.urllib.request, 'build_opener',
                        lambda *args: SimpleNamespace(open=open_request))
    response = client(data).post('/api/translate', json={'text': '原始评语'})
    assert response.status_code == 200
    assert response.json() == {'text': 'Translated comment'}
    assert len(seen) == 1


@pytest.mark.parametrize('data', [
    {'maintenance': {}},
    {'translation_url': '', 'maintenance': {'url': 'http://127.0.0.1:8080'}},
    {'translation_url': None},
])
def test_missing_or_explicitly_disabled_translation_never_calls_backend(monkeypatch, data):
    monkeypatch.setattr(ui_app.urllib.request, 'build_opener',
                        lambda *args: pytest.fail('No HTTP request expected'))
    response = client(data).post('/api/translate', json={'text': 'Original'})
    assert response.status_code == 503


@pytest.mark.parametrize('result', [{'ok': False}, {'ok': True, 'text': ''}, ['bad']])
def test_backend_failure_preserves_original_comment(monkeypatch, result):
    monkeypatch.setattr(ui_app.urllib.request, 'build_opener', lambda *args:
                        SimpleNamespace(open=lambda *a, **kw: io.BytesIO(json.dumps(result).encode())))
    body = {'text': 'Original'}
    response = client({'translation_url': 'http://127.0.0.1:8772'}).post('/api/translate', json=body)
    assert response.status_code == 502
    assert 'original comment is unchanged' in response.json()['detail']
    assert body == {'text': 'Original'}


def test_empty_comment_never_calls_backend(monkeypatch):
    monkeypatch.setattr(ui_app.urllib.request, 'build_opener',
                        lambda *args: pytest.fail('No HTTP request expected'))
    response = client({'translation_url': 'http://127.0.0.1:8772'}).post('/api/translate', json={'text': '  '})
    assert response.status_code == 400


def test_transport_failure_is_reported_without_worker_side_effects(monkeypatch):
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError('offline test')
    monkeypatch.setattr(ui_app.urllib.request, 'build_opener',
                        lambda *args: SimpleNamespace(open=unavailable))
    response = client({'translation_url': 'http://127.0.0.1:8772'}).post(
        '/api/translate', json={'text': 'Original'})
    assert response.status_code == 502
    assert 'original comment is unchanged' in response.json()['detail']
