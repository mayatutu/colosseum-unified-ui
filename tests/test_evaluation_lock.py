import subprocess
import sys
from pathlib import Path
from evaluation_lock import evaluation_lock


def test_a_surviving_submit_job_is_busy_even_after_gui_restart(tmp_path):
    script = '''
import sys
from evaluation_lock import evaluation_lock
try:
    with evaluation_lock(sys.argv[1], blocking=False): pass
except OSError:
    print('busy')
else:
    print('available')
'''
    root = Path(__file__).resolve().parents[1]
    with evaluation_lock(tmp_path):
        result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], cwd=root, capture_output=True, text=True)
        assert result.stdout.strip() == 'busy'
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], cwd=root, capture_output=True, text=True)
    assert result.stdout.strip() == 'available'
