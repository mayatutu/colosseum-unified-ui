"""Loopback browser fixture: real scene persistence, simulated evaluation/reporting."""
import json
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from bridge import RemoteError
from hub_fixture import SimulatedClient
from scene_settings import read_scene, save_scene
from station import Station


class Client(SimulatedClient):
    def __init__(self, root):
        super().__init__('franka')
        self.config = root / 'robot.yaml'
        self.config.write_text('scene: old-scene\nprivate_value: untouched\n', encoding='utf-8')

    def call(self, method, params=None):
        params = params or {}
        if method == 'save_scene':
            try:
                return {'ok': True, 'scene': save_scene(self.config, params.get('scene'), params.get('expected_scene'))}
            except ValueError as error:
                raise RemoteError(str(error), 400)
        value = super().call(method, params)
        if method == 'config':
            value.update(scene=read_scene(self.config), scene_persistence_enabled=True,
                         feishu={'enabled':True,'devices':['F1','F2']})
        if method == 'stats':
            value['feishu_reports']=[{'id':'ev_'+status, 'person':'T0','date':'2026-11-06','status':status,'error':''}
                                     for status in ('sent','error','unknown')]
        return value


if __name__ == '__main__':
    import uvicorn
    with tempfile.TemporaryDirectory(prefix='scene-feishu-browser-') as directory:
        root=Path(directory)
        bridge=Client(root)
        app=create_app(Station(root/'station.yaml',{'robot':'franka','database':str(root/'stats.db')}),bridge)
        @app.get('/test/config')
        def config(): return {'text':bridge.config.read_text(encoding='utf-8'),'calls':bridge.calls}
        uvicorn.run(app,host='127.0.0.1',port=18873,log_level='warning')
