import os
from pathlib import Path
import subprocess
import sys
import venv

import pytest

from station import Station


@pytest.mark.skipif(os.name == 'nt', reason='Linux venv executable symlink regression')
def test_worker_python_keeps_virtual_environment(tmp_path):
    env = tmp_path / 'client-env'
    venv.EnvBuilder(with_pip=False, symlinks=True).create(env)
    python = env / 'bin/python'
    station = Station(tmp_path / 'station.yaml', {'client_python': str(python)})
    command = station.worker_command()
    prefix = subprocess.check_output([command[0], '-c', 'import sys; print(sys.prefix)'], text=True).strip()
    assert Path(prefix) == env


def test_relative_python_path_is_anchored_to_station(tmp_path):
    station = Station(tmp_path / 'config/station.yaml', {'client_python': '../env/bin/python'})
    assert station.file('client_python') == tmp_path / 'env/bin/python'
