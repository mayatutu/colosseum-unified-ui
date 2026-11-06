"""Actual the Franka workstation run_trial + GUI Stop hooks; hardware/Policy/recording use existing offline fakes."""
import importlib.util
import sys
import threading
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT.parent / 'client-reset-timing-20261027'
sys.path.insert(0, str(DEPLOY / 'candidate/src'))
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('reset_simulation', DEPLOY / 'test_reset_simulation.py')
simulation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simulation)
from stop_hooks import install_action_hooks


@pytest.mark.parametrize('g05', [False, True])
def test_stop_after_inference_blocks_action_and_preserves_real_cleanup(tmp_path, monkeypatch, g05):
    ev = simulation.e
    stop, latest = threading.Event(), [None]
    read = ev.read_observation
    def observe(*args, **kwargs):
        latest[0] = read(*args, **kwargs)
        return latest[0]
    monkeypatch.setattr(ev, 'read_observation', observe)
    originals = install_action_hooks(ev, stop, lambda: latest[0])
    class PatchProxy:
        def setitem(self, *args, **kwargs):
            return monkeypatch.setitem(*args, **kwargs)
        def setattr(self, obj, name, value):
            if name == 'action_chunk':
                original = value
                def value(*args, **kwargs):
                    stop.set()  # Stop arrived while inference was in flight
                    return original(*args, **kwargs)
            if name == 'LocalPolicyClient' and g05:
                init = value.__init__
                def wrapped(client, *args, **kwargs):
                    init(client, *args, **kwargs)
                    client.model.update(name='g05', url='https://huggingface.co/OpenGalaxea/G05')
                monkeypatch.setattr(value, '__init__', wrapped)
            return monkeypatch.setattr(obj, name, value)
    try:
        events, error = simulation.scenario(tmp_path, PatchProxy())
        assert error is None
        assert not any(name == 'action' for name, _ in events)
        simulation.check_reset_order(events)
    finally:
        for name, original in originals.items():
            setattr(ev, name, original)


@pytest.mark.parametrize('failure', ['infer', 'save', 'client_close'])
def test_original_error_cleanup_is_preserved(tmp_path, monkeypatch, failure):
    events, error = simulation.scenario(tmp_path, monkeypatch, failure=failure)
    assert isinstance(error, RuntimeError)
    simulation.check_reset_order(events)
