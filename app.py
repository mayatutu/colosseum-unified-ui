"""GUI environment: HTTP/UI transport only. Robot code lives in a local worker."""
import argparse
import asyncio
import base64
import json
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
import uvicorn

from bridge import Bridge, RemoteError
from station import Station

ROOT = Path(__file__).resolve().parent


def create_app(station, bridge=None):
    client = bridge or Bridge(station.worker_command(), cwd=ROOT,
                              log_path=station.file('database').with_name('worker.log'))

    @asynccontextmanager
    async def lifespan(app):
        client.start()
        try:
            yield
        finally:
            await asyncio.to_thread(client.close)
    app = FastAPI(title='Colosseum Unified Eval Station', lifespan=lifespan)
    if hasattr(station, 'data') and hasattr(station, 'file'):
        from station_hub import install_hub
        install_hub(app, station, client, ROOT)

    @app.exception_handler(RemoteError)
    async def remote_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=exc.status_code)

    @app.get('/')
    def index():
        page = 'hub.html' if hasattr(app.state, 'registry') else 'eval_gui.html'
        return HTMLResponse((ROOT / page).read_text(encoding='utf-8'))

    @app.get('/station')
    def standalone_station():
        return HTMLResponse((ROOT / 'eval_gui.html').read_text(encoding='utf-8'))

    @app.get('/station.js')
    def station_script():
        return FileResponse(ROOT / 'station.js', media_type='text/javascript')

    @app.get('/i18n.js')
    def translations():
        return FileResponse(ROOT / 'i18n.js', media_type='text/javascript')

    @app.get('/api/config')
    def config():
        return client.call('config')

    @app.get('/api/state')
    def state():
        return client.call('snapshot')

    @app.post('/api/check/{name}')
    def check(name: str):
        return client.call('check', {'name': name})

    @app.post('/api/preview/{action}')
    def preview(action: str):
        return client.call('preview', {'action': action})

    @app.post('/api/keys')
    def keys(body: dict):
        return client.call('keys', body)

    @app.post('/api/eval/{action}')
    def evaluation(action: str, body: dict):
        if action not in ('start', 'reply', 'finish', 'reset'):
            raise HTTPException(404)
        return client.call(action, body)

    @app.get('/api/evals')
    def evaluations(offset: int = 0, limit: int = 60, paginated: bool = False):
        page = client.call('list', {'offset': offset, 'limit': limit})
        return page if paginated else page['items']  # original list contract remains valid

    @app.get('/api/evals/{eid}')
    def evaluation_detail(eid: str):
        return client.call('detail', {'id': eid})

    @app.post('/api/evals/{eid}')
    def evaluation_action(eid: str, body: dict):
        return client.call('act', {'id': eid, 'body': body})

    @app.post('/api/evals/{eid}/generate')
    def generate(eid: str, body: dict):
        return client.call('generate', {'id': eid, 'body': body})

    @app.post('/api/translate')
    def translate(body: dict):
        text = body.get('text')
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(400, 'Write an overall comment first')
        url = station.data.get('maintenance', {}).get('url', '').rstrip('/')
        if not url:
            raise HTTPException(503, 'Translation backend is not configured')
        # Reuse only the old UI's translation route; no robot/worker operations.
        request = urllib.request.Request(url + '/api/translate',
            data=json.dumps({'text': text}, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST')
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=45) as response:
                result = json.load(response)
        except (OSError, ValueError, urllib.error.URLError):
            raise HTTPException(502, 'Translation failed. Your original comment is unchanged.') from None
        if (not isinstance(result, dict) or result.get('ok') is not True
                or not isinstance(result.get('text'), str) or not result['text'].strip()):
            raise HTTPException(502, 'Translation failed. Your original comment is unchanged.')
        return {'text': result['text'].strip()}

    @app.post('/api/reconcile')
    def reconcile():
        return client.call('reconcile')

    @app.get('/api/stats')
    def stats(date: str | None = None):
        return client.call('stats', {'date': date})

    @app.get('/api/people')
    def people():
        return client.call('people')

    @app.post('/api/people')
    def add_person(body: dict):
        return client.call('people', body)

    @app.post('/api/maintenance/{action}')
    def maintenance(action: str):
        return client.call('maintenance', {'action': action})

    @app.get('/api/maintenance/logs')
    def logs():
        return client.call('logs')

    @app.get('/api/thumb/{cam}.jpg')
    def thumbnail(cam: str):
        data = client.call('thumb', {'cam': cam})
        if not data:
            raise HTTPException(404)
        return Response(base64.b64decode(data), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

    @app.get('/api/scene-reference/{eid}/{cam}.png')
    def scene_reference(eid: str, cam: str):
        path = client.call('scene_reference', {'id': eid, 'camera': cam})
        if not path:
            raise HTTPException(404)
        return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store'})

    @app.get('/video/{eid}/{run_id}/{cam}')
    def video(eid: str, run_id: str, cam: str):
        path = client.call('video', {'id': eid, 'run': run_id, 'cam': cam})
        if not path:
            raise HTTPException(404)
        return FileResponse(path, media_type='video/mp4')

    @app.websocket('/ws')
    async def websocket(sock: WebSocket):
        await sock.accept()
        last_frame = None
        try:
            while True:
                value = await asyncio.to_thread(client.call, 'snapshot')
                frame = value.pop('frame', None)
                await sock.send_text(json.dumps(value, ensure_ascii=False))
                if frame and value.get('frame_seq') != last_frame:
                    last_frame = value.get('frame_seq')
                    await sock.send_bytes(base64.b64decode(frame))
                await asyncio.sleep(.2)
        except (WebSocketDisconnect, RuntimeError):
            return
    return app


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--station', required=True)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8770)
    a = p.parse_args()
    uvicorn.run(create_app(Station.load(a.station)), host=a.host, port=a.port)
