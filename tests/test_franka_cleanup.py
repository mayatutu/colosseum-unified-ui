import subprocess
from test_worker_process import ROOT, PYTHON
import pytest


@pytest.mark.skipif(not PYTHON.exists(), reason='Original Python 3.12 test environment unavailable')
def test_franka_actual_trial_cleanup_with_gui_stop():
    result = subprocess.run([str(PYTHON), '-X', 'utf8', '-m', 'pytest', str(ROOT / 'tests/franka_runtime_checks.py'),
                             '-q', '--junitxml=' + str(ROOT / 'validation/franka-cleanup-tests.xml')],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
