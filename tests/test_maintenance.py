from types import SimpleNamespace
import pytest
from legacy_host import LegacyHost


def test_external_legacy_service_is_reused_without_starting_another_policy(monkeypatch, tmp_path):
    host = LegacyHost(tmp_path, 'yam', 'http://127.0.0.1:8080', 'ws://127.0.0.1:8000')
    calls = []
    def request(route, post=False):
        calls.append((route, post))
        return {'ok': True}
    monkeypatch.setattr(host, 'http_request', request)
    monkeypatch.setattr(host, 'status', lambda: {'ok': True, 'external': host.external})
    assert host.call('startup', {})['external']
    assert host.module is None
    assert calls == [('/api/state', False)]
    host.call('restart_policy', {})
    assert calls[-1] == ('/api/restart_policy', True)


def test_franka_docker_uses_exact_legacy_route_and_yam_has_no_docker(monkeypatch, tmp_path):
    host = LegacyHost(tmp_path, 'franka', 'http://127.0.0.1:8080', 'ws://policy-host.example.invalid:8000')
    host.started, host.external = True, True
    calls = []
    monkeypatch.setattr(host, 'http_request', lambda route, post=False: calls.append((route, post)) or {'ok': True})
    host.call('restart_docker', {})
    assert calls == [('/api/restart_docker', True)]
    host.robot = 'yam'
    with pytest.raises(ValueError):
        host.call('restart_docker', {})


def test_franka_start_only_checks_never_recovers(tmp_path):
    host = LegacyHost(tmp_path, 'franka', 'unused', 'unused')
    calls = []
    host.started = True
    host.module = SimpleNamespace(start_policy_server=lambda: calls.append('check') or False)
    assert not host.call('start_policy', {})['ok']
    assert calls == ['check']


@pytest.mark.parametrize('result, expected, detail', [
    ((False, 'Policy unavailable'), False, 'Policy unavailable'),
    ((True, ''), True, 'Franka Policy startup check'),
    (False, False, 'Franka Policy startup check'),
    (True, True, 'Franka Policy startup check'),
])
def test_franka_startup_preserves_installed_health_result(tmp_path, result, expected, detail):
    host = LegacyHost(tmp_path, 'franka', 'unused', 'unused')
    calls = []
    host.started = host.external = True
    host.module = SimpleNamespace(start_policy_server=lambda: calls.append('check') or result)
    status = host.call('start_policy', {})
    assert status['ok'] is expected
    assert status['detail'] == detail
    assert status['external'] is True
    assert calls == ['check']


def test_yam_owned_stop_disables_watchdog_and_start_reuses_existing(tmp_path):
    host = LegacyHost(tmp_path, 'yam', 'unused', 'unused')
    calls = []
    proc = SimpleNamespace(poll=lambda: None, terminate=lambda: calls.append('terminate'), wait=lambda **kw: calls.append('wait'))
    host.started = True
    host.module = SimpleNamespace(_POLICY_PROC=proc, _policy_restarting=False,
                                  start_policy_server=lambda: calls.append('start'))
    host.status = lambda: {'ok': True}
    host.call('start_policy', {})
    assert not calls
    host.call('stop_policy', {})
    assert host.module._policy_restarting
    assert calls == ['terminate', 'wait']


def test_yam_without_old_web_runs_existing_startup_and_watchdog(tmp_path, monkeypatch):
    from urllib.error import URLError
    import time
    (tmp_path / 'app.py').write_text('''
events = []
def start_policy_server(): events.append('start')
def _policy_watchdog(): events.append('watchdog')
def start_franka_logs(): events.append('logs')
''')
    host = LegacyHost(tmp_path, 'yam', 'http://unused', 'ws://unused')
    monkeypatch.setattr(host, 'http_request', lambda *a, **k: (_ for _ in ()).throw(URLError('offline test')))
    monkeypatch.setattr(host, 'status', lambda: {'ok': True})
    monkeypatch.chdir(tmp_path)
    host.call('startup', {})
    for _ in range(20):
        if 'watchdog' in host.module.events:
            break
        time.sleep(.01)
    assert host.module.events.count('start') == 1
    assert 'watchdog' in host.module.events and 'logs' in host.module.events
    host.call('startup', {})
    assert host.module.events.count('start') == 1
