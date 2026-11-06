import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT
sys.path[:0] = [str(SOURCE), str(SOURCE / 'tests')]
import app
from hub_fixture import SimulatedClient
from station import Station
import uvicorn

class Client(SimulatedClient):
    def call(self, method, params=None):
        result = super().call(method, params)
        if method == 'config':
            result.update(task_difficulty_enabled=True, feishu={'enabled': True, 'devices': ['F1','F2']})
        return result

app.ROOT = ROOT
with tempfile.TemporaryDirectory(prefix='submit-dialog-fixture-') as folder:
    root = Path(folder)
    uvicorn.run(app.create_app(Station(root / 'station.yaml', {'robot':'franka','database':str(root/'stats.db')}), Client('franka')),
                host='127.0.0.1',port=18874,log_level='warning')
