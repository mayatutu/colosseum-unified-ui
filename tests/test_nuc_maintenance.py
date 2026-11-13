import io
import threading
from types import SimpleNamespace
import pytest
from nuc_maintenance import NucDockerHost
from runtime import Runtime


def test_exact_old_route_without_network():
    host = NucDockerHost('http://127.0.0.1:8080')
    calls = []
    def open(request, timeout):
        calls.append((request.full_url, request.get_method(), request.data, timeout))
        return io.BytesIO(b'{"ok":true}')
    host.http = SimpleNamespace(open=open)
    assert host.restart() == {'ok': True}
    assert calls == [('http://127.0.0.1:8080/api/restart_docker', 'POST', b'{}', 120)]


@pytest.mark.parametrize('recording,pending', [(True,False),(False,True),(False,False)])
def test_candidate_routes_nuc_only_when_idle(recording,pending):
    runtime = Runtime.__new__(Runtime)
    events = []
    runtime.candidate = object()
    runtime.maintenance_lock = threading.Lock()
    runtime.lock = threading.RLock()
    runtime.round_stop_pending = pending
    runtime.c = SimpleNamespace(recording=lambda: recording,
        PREVIEW=SimpleNamespace(stop=lambda: events.append('preview_stop')),
        S=SimpleNamespace(set_check=lambda *a: events.append(a)))
    runtime.nuc = SimpleNamespace(restart=lambda: events.append('nuc') or {'ok':True})
    runtime.policy = lambda *a: pytest.fail('NUC restart must not call Policy maintenance')
    if recording or pending:
        with pytest.raises(RuntimeError): runtime.maintain('restart_docker')
        assert events == []
    else:
        assert runtime.maintain('restart_docker') == {'ok':True}
        assert events[:2] == ['preview_stop','nuc']
        assert events[2][0:2] == ('can','idle')
