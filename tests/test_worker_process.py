import os
from pathlib import Path
import sys
import yaml
import pytest
from bridge import Bridge
from station import Station

ROOT = Path(__file__).resolve().parents[1]
CLIENT = Path(os.environ.get('COLOSSEUM_TEST_YAM_CLIENT',
                             os.environ.get('COLOSSEUM_TEST_CLIENT', str(ROOT.parent / 'client'))))
PYTHON = Path(sys.executable)


@pytest.mark.skipif(not (CLIENT / 'src/colosseum_client').is_dir(), reason='Set COLOSSEUM_TEST_CLIENT to the compatible Client source')
def test_real_worker_config_statistics_and_empty_original_review(tmp_path):
    config = tmp_path / 'robot.yaml'
    config.write_text(yaml.safe_dump({'url': 'ws://127.0.0.1:1', 'api_url': 'http://127.0.0.1:1',
        'token': 'offline-unit-test', 'robot_type': 'yam', 'test': True, 'cameras': {},
        'evaluation_dir': str(tmp_path / 'evals'), 'skip_upload': True}), encoding='utf-8')
    station_path = tmp_path / 'station.yaml'
    station_path.write_text(yaml.safe_dump({'robot': 'yam', 'client_root': str(CLIENT),
        'client_python': str(PYTHON), 'robot_config': str(config), 'database': str(tmp_path / 'stats.db')}))
    station = Station.load(station_path)
    bridge = Bridge(station.worker_command(), cwd=ROOT)
    try:
        result = bridge.call('config', timeout=30)
        assert result['robot'] == 'yam'
        assert bridge.call('list')['items'] == []
        assert bridge.call('stats')['rows'] == []
        assert bridge.call('people', {'name': '评测员'}) == ['评测员']
        state = bridge.call('snapshot')
        assert state['run']['phase'] == 'idle'
        assert state['checks']['server']['status'] != 'ok'
        assert state['pending'] == []
    finally:
        bridge.close()
    assert bridge.proc.wait(timeout=15) == 0
