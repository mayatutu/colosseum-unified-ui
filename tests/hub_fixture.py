"""Loopback-only simulated stations for gateway tests. No robot or Router imports."""
import copy
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from station import Station


class SimulatedClient:
    def __init__(self, robot):
        self.robot, self.calls, self.recording, self.preview = robot, [], False, False
        self.detail = {'id': 'same_record_id', 'instruction': robot + ' fixture task', 'scene': 'fixture',
                       'state': 'review', 'time': 1700000000, 'busy': False, 'managed': True,
                       'preference': '', 'feedback': '', 'factors': {}, 'log': '',
                       'runs': [{'id': 'run_' + side, 'side': side, 'model_name': robot + '_' + side,
                                 'recorded': True, 'cams': ['head_image'], 'score': None, 'stop': None}
                                for side in ('A', 'B')]}

    def start(self): pass
    def close(self): pass

    def call(self, method, params=None):
        params = params or {}
        if method not in ('snapshot', 'config', 'list', 'detail', 'stats', 'logs'):
            self.calls.append((method, copy.deepcopy(params)))
        if method == 'config':
            return {'robot': self.robot, 'station': self.robot, 'institution': 'SIMULATED ONLY', 'scene': '',
                    'evaluator': '', 'evaluator_options': ['T0', 'T1'], 'cameras': [], 'max_steps': 800,
                    'settings_mode': 'host' if self.robot == 'franka' else 'keys', 'managed_providers': [],
                    'people': [], 'maintenance': ['restart_policy'], 'feedback_generation_enabled': False}
        if method == 'snapshot':
            return {'checks': {k: {'status': 'ok', 'detail': ''} for k in ('gpu','can','arms','cameras','router','keys','server')},
                    'run': {'phase': 'running' if self.recording else 'idle', 'side': 'A', 'step': 1,
                            'max_steps': 800, 'instruction': self.robot + ' simulation', 'eval_id': 'same_record_id'},
                    'log': [], 'keys': [], 'thumbs': [], 'prompt': None, 'preview': self.preview,
                    'recording': self.recording, 'pending': [], 'models': {}}
        if method == 'list':
            return {'items': [self.detail], 'total': 1, 'offset': 0, 'limit': params.get('limit', 100)}
        if method == 'detail': return copy.deepcopy(self.detail)
        if method == 'video': return str(Path(__file__).resolve().parents[1] / 'validation/feedback-test-video.mp4')
        if method == 'stats': return {'rows': [{'date': '2026-10-30', 'person': 'T0', 'robot': self.robot, 'count': 1}]}
        if method == 'logs': return {'client': self.robot + ' client', 'policy': self.robot + ' policy'}
        if method == 'preview': self.preview = params['action'] == 'start'
        if method == 'start': self.recording = True
        if method == 'finish': self.recording = False
        if method == 'act' and params['body'].get('action') == 'save':
            b = params['body'];self.detail.update(feedback=b['feedback'], preference=b['preference'])
            for r in self.detail['runs']: r['score'] = b.get('score_' + r['side'])
        return {'ok': True, 'msg': 'Draft saved.'}


def fixture_app(path, robot):
    station = Station(path / 'station.yaml', {'robot': robot, 'database': str(path / 'stats.sqlite3')})
    bridge = SimulatedClient(robot)
    app = create_app(station, bridge)
    @app.get('/test/events')
    def events(): return {'calls': bridge.calls, 'recording': bridge.recording}
    @app.post('/test/reset')
    def reset():
        bridge.__init__(robot)
        with app.state.registry.connect() as db:
            db.execute('DELETE FROM stations WHERE local=0')
        return {'ok': True}
    return app, bridge


if __name__ == '__main__':
    import uvicorn
    robot, port = sys.argv[1], int(sys.argv[2])
    with tempfile.TemporaryDirectory(prefix='colosseum-hub-fixture-') as directory:
        app, _ = fixture_app(Path(directory), robot)
        uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
