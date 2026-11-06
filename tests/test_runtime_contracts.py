import subprocess
from pathlib import Path
import pytest
from test_worker_process import ROOT, PYTHON


@pytest.mark.parametrize('robot', ['franka', 'yam'])
@pytest.mark.parametrize('scenario', ['workflow', 'lost_response'])
@pytest.mark.skipif(not PYTHON.exists(), reason='Original Python 3.12 test environment unavailable')
def test_actual_client_loop_contracts(robot, scenario):
    result = subprocess.run([str(PYTHON), '-X', 'utf8', str(ROOT / 'tests/runtime_scenario.py'), robot, scenario],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS ' + robot + ' ' + scenario in result.stderr + result.stdout
