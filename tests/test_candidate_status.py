from types import SimpleNamespace
import pytest
from runtime import Runtime
from colosseum_client import local_policy


@pytest.mark.parametrize('online',[True,False])
def test_unmanaged_policy_reports_actual_endpoint(monkeypatch,online):
    calls=[]
    runtime=Runtime.__new__(Runtime);runtime.legacy=None
    runtime.c=SimpleNamespace(CONFIG=SimpleNamespace(policy_server_url='ws://127.0.0.1:18001'),
                              S=SimpleNamespace(set_check=lambda *args:calls.append(args)))
    async def capabilities(url):
        assert url=='ws://127.0.0.1:18001'
        if not online:raise ConnectionError()
        return {'verification_only':False}
    monkeypatch.setattr(local_policy,'capabilities',capabilities)
    assert runtime.policy('status')['ok'] is online
    assert calls[-1][1]==('ok' if online else 'fail')
    assert runtime.policy('stop_policy')['ok'] is False
