from types import SimpleNamespace
from pathlib import Path
import threading
import yaml
import pytest
from runtime import Runtime
from station import Station


def station(tmp_path, robot='yam', **extra):
    path = tmp_path / 'station.yaml'
    path.write_text(yaml.safe_dump({'robot': robot, 'client_root': str(tmp_path),
        'client_python': 'python', 'robot_config': 'robot.yaml', 'database': 'stats.db', **extra}))
    return Station.load(path)


@pytest.mark.parametrize('feedback', [None, '', ' \n\t', '\u3000'])
def test_submit_requires_nonblank_feedback_before_any_router_or_store_work(feedback):
    runtime = object.__new__(Runtime)
    class Required(Exception):
        def __init__(self, status, detail):
            self.status = status
    runtime.c = SimpleNamespace(HTTPException=Required)
    with pytest.raises(Required) as error:
        runtime._act_locked('test', {'action': 'submit', 'feedback': feedback})
    assert error.value.status == 400


@pytest.mark.parametrize('flag', [None, False, 'false'])
def test_feedback_disabled_never_reads_keys_or_invokes_ai(tmp_path, flag):
    runtime = object.__new__(Runtime)
    runtime.station = station(tmp_path, feedback_generation_enabled=flag)
    class Disabled(Exception):
        def __init__(self, status, message):
            self.status = status
    runtime.c = SimpleNamespace(HTTPException=Disabled)
    with pytest.raises(Disabled) as error:
        runtime.generate_feedback('unused', {'feedback': 'User comment'})
    assert error.value.status == 403


def test_enabled_feedback_uses_only_overall_comment_without_factors(tmp_path):
    runtime = object.__new__(Runtime)
    runtime.station = station(tmp_path, feedback_generation_enabled=True)
    runtime.station.load_client_config = lambda: SimpleNamespace(llm_api_keys={})
    prompts = []
    runtime.c = SimpleNamespace(known=lambda eid: eid,
        rv=SimpleNamespace(load=lambda eid: {'assignment': {'task': {'instruction': 'Pick up cup'}}}),
        feedback_via_claude_code=lambda prompt: prompts.append(prompt) or 'Rewritten overall comment')
    assert runtime.generate_feedback('test', {'feedback': 'A succeeded; B dropped the cup.',
        'score_A': 100, 'score_B': 50, 'preference': 'A'})['feedback'] == 'Rewritten overall comment'
    assert 'A succeeded; B dropped the cup.' in prompts[0]
    assert 'A score: 100/100' in prompts[0]


def test_provider_verification_uses_actual_yam_model_url_and_auth(tmp_path):
    policy = tmp_path / 'policy.yaml'
    policy.write_text(yaml.safe_dump({'models': [
        {'name': 'gpt-6-astra', 'model_type': 'llm', 'url': 'https://relay.example/v1'},
        {'name': 'claude-opus-5-5', 'model_type': 'llm', 'url': 'https://relay.example',
         'backend_options': {'api_auth': 'bearer'}},
        {'name': 'grok-4.7', 'model_type': 'llm', 'url': 'https://relay.example/v1'}]}))
    runtime = object.__new__(Runtime)
    runtime.station = station(tmp_path, policy_config=str(policy))
    requests = []
    def get(url, **kw):
        requests.append((url, kw))
        return SimpleNamespace(is_success=True)
    runtime.c = SimpleNamespace(httpx=SimpleNamespace(get=get, HTTPError=OSError))
    assert runtime.verify_key('anthropic', 'unit-test-key') == (True, 'Verified')
    assert requests[0][0] == 'https://relay.example/v1/models'
    assert requests[0][1]['headers']['Authorization'] == 'Bearer unit-test-key'
    assert 'x-api-key' not in requests[0][1]['headers']
    assert requests[0][1]['follow_redirects'] is False
    runtime.verify_key('openai', 'another-unit-key')
    assert requests[1][0] == 'https://relay.example/v1/models'


def test_franka_saves_keys_on_client_with_official_transport_validation(tmp_path):
    runtime = object.__new__(Runtime)
    runtime.station = station(tmp_path, 'franka')
    runtime.c = SimpleNamespace()
    runtime.station.file('robot_config').write_text(yaml.safe_dump({
        'url': 'ws://127.0.0.1:1', 'token': 'offline-test', 'cameras': {}, 'test': True,
        'policy_server_url': 'ws://127.0.0.1:18001'}))
    runtime.save_keys({'openai': 'offline-test-key'})
    assert runtime.c.CONFIG.llm_api_keys == {'openai': 'offline-test-key'}
    assert (tmp_path / 'llm-settings.json').exists()


def test_exported_lerobot_video_survives_deleted_pngs(tmp_path):
    runtime = object.__new__(Runtime)
    runtime.c = SimpleNamespace(CAMS=('head_image', 'left_image', 'right_image'))
    runtime.root = tmp_path
    mp4 = tmp_path / 'ev/run/lerobot/videos/observation.images.left_image/chunk-000/file-000.mp4'
    mp4.parent.mkdir(parents=True)
    mp4.write_bytes(b'test')
    runtime.original_preview = lambda *a: (_ for _ in ()).throw(AssertionError('Must not try missing PNGs'))
    assert runtime.video_path('ev', 'run', 'left_image') == mp4


def test_second_start_cannot_change_person_while_first_is_running():
    runtime = object.__new__(Runtime)
    runtime.lock = threading.RLock()
    runtime.current_person = '甲'
    class Conflict(Exception):
        pass
    runtime.c = SimpleNamespace(recording=lambda: True, HTTPException=Conflict)
    with pytest.raises(Conflict):
        runtime.start({'evaluator': '乙'})
    assert runtime.current_person == '甲'


def test_maintenance_stops_new_recording_then_uses_existing_command():
    runtime = object.__new__(Runtime)
    runtime.maintenance_lock = threading.Lock()
    calls = []
    runtime.stop_recording = lambda: calls.append('stop_recording')
    runtime.c = SimpleNamespace(PREVIEW=SimpleNamespace(stop=lambda: calls.append('stop_preview')))
    runtime.policy = lambda method, **kw: calls.append(method) or {'ok': True}
    runtime.maintain('restart_docker')
    assert calls == ['stop_recording', 'stop_preview', 'restart_docker']


def test_startup_restores_failed_round_without_starting_a_trial(monkeypatch):
    runtime = object.__new__(Runtime)
    calls = []
    runtime.station = SimpleNamespace(robot='franka')
    runtime.store = SimpleNamespace(pending=lambda robot: [{'id': 'ev_failed'}])
    runtime.legacy = None
    runtime.c = SimpleNamespace(rv=SimpleNamespace(load=lambda eid: {
        'recording_error': 'controller timeout', 'assignment': {'task': {'instruction': 'pick'}}}),
        S=SimpleNamespace(set_run=lambda **kw: calls.append(kw), set_check=lambda *a: None))
    monkeypatch.setattr(threading, 'Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    runtime.startup()
    assert calls == [dict(phase='error', eval_id='ev_failed', side=None, step=0,
                          instruction='pick', message='controller timeout')]
