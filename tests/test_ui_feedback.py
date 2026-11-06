import json
from pathlib import Path

from legacy_host import LegacyHost
from station import Station
from ui_diagnostics import LogMirror, model_name, tail


def test_model_names_use_actual_run_metadata(tmp_path):
    path = tmp_path / 'policy.json'
    assert model_name(path) == ''
    path.write_text(json.dumps({'model': {'name': 'grok-4.7', 'url': 'https://relay.example/v1'}}))
    assert model_name(path) == 'grok-4.7'
    path.write_text(json.dumps({'model': {'url': 'https://huggingface.co/org/lingbot-yam'}}))
    assert model_name(path) == 'lingbot-yam'
    path.write_text('partial write')
    assert model_name(path) == ''


def test_legacy_evaluator_roster_is_reused(tmp_path):
    (tmp_path / 'config.yaml').write_text('evaluators:\n'+''.join(f'  - name: T{i}\n' for i in range(10)))
    station = Station(tmp_path / 'station.yaml', {'maintenance': {'root': str(tmp_path)}, 'people': []})
    assert station.evaluator_options() == [f'T{i}' for i in range(10)]


def test_policy_log_survives_overlapping_snapshots_and_restart(tmp_path):
    path = tmp_path / 'policy.log'
    mirror = LogMirror(path)
    mirror.append_snapshot('one\ntwo\n')
    mirror.append_snapshot('two\nthree\n')
    mirror.append_snapshot('two\nthree\n')
    assert path.read_text() == 'one\ntwo\nthree\n'
    mirror = LogMirror(path)
    mirror.append_snapshot('three\nfour\n')
    assert tail(path) == 'one\ntwo\nthree\nfour\n'
    mirror.append_snapshot('new server\n')
    assert 'buffer changed' in tail(path)
    assert tail(path).endswith('new server\n')


def test_local_policy_probe_does_not_open_incomplete_websocket(monkeypatch, tmp_path):
    import legacy_host
    host = LegacyHost(tmp_path, 'yam', 'unused', 'ws://127.0.0.1:8000')
    monkeypatch.setattr(Path, 'exists', lambda self: True)
    monkeypatch.setattr(Path, 'read_text', lambda self: 'header\n0: 0100007F:1F40 00000000:0000 0A\n')
    def unexpected(*args, **kwargs):
        raise AssertionError('Must not connect to the live Policy')
    monkeypatch.setattr(legacy_host.socket, 'create_connection', unexpected)
    assert host.status()['ok']
