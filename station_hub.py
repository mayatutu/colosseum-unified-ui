"""Workstation registry and transport gateway. Never controls robot lifecycle."""
import asyncio
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request as URLRequest, build_opener, ProxyHandler, HTTPRedirectHandler

from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def open_url(url, *, data=None, headers=None, method='GET', timeout=3):
    request = URLRequest(url, data=data, headers=headers or {}, method=method)
    return build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def get_json(url, timeout=3):
    with open_url(url, timeout=timeout) as response:
        return json.load(response)


def normalize_address(value):
    value = str(value or '').strip()
    if '://' not in value:
        value = 'http://' + value
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError:
        raise HTTPException(400, 'Invalid workstation address') from None
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise HTTPException(400, 'Enter the workstation IP or base URL, without a path')
    host = '[' + parts.hostname + ']' if ':' in parts.hostname else parts.hostname
    if port is None:
        port = 8772
    return urlunsplit((parts.scheme, host + ':' + str(port), '', '', ''))


class Registry:
    def __init__(self, path, robot, name):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS stations (id TEXT PRIMARY KEY,name TEXT NOT NULL,'
                       'url TEXT NOT NULL UNIQUE,remote_id TEXT,robot TEXT,local INTEGER NOT NULL DEFAULT 0)')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('local_id', str(uuid.uuid4())))
            self.local_id = db.execute("SELECT value FROM metadata WHERE key='local_id'").fetchone()[0]
            db.execute('INSERT OR IGNORE INTO stations VALUES (?,?,?,?,?,1)',
                       (self.local_id, name, '', self.local_id, robot))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def rows(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM stations ORDER BY local DESC,rowid')]

    def get(self, sid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM stations WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Workstation not found')
        return dict(row)

    def save(self, body):
        name = str(body.get('name') or '').strip()
        if not name:
            raise HTTPException(400, 'Enter a robot name')
        old = self.get(body['id']) if body.get('id') else None
        url = '' if old and old['local'] else normalize_address(body.get('address'))
        with self.connect() as db:
            duplicate = db.execute('SELECT id FROM stations WHERE url=?', (url,)).fetchone()
            if duplicate and (not old or duplicate['id'] != old['id']):
                raise HTTPException(409, 'This address is already in the robot list')
            sid = old['id'] if old else str(uuid.uuid4())
            if old:
                db.execute('UPDATE stations SET name=?,url=? WHERE id=?', (name, url, sid))
            else:
                db.execute('INSERT INTO stations(id,name,url) VALUES(?,?,?)', (sid, name, url))
        return self.get(sid)

    def identify(self, row):
        if row['local']:
            return {'id': self.local_id, 'robot': row['robot'], 'protocol': 1}
        info = get_json(row['url'] + '/api/station-info')
        if (not isinstance(info, dict) or info.get('protocol') != 1
                or info.get('robot') not in ('yam', 'franka')):
            raise ValueError('Incompatible workstation service')
        remote_id = str(uuid.UUID(info['id']))
        if row['remote_id'] and row['remote_id'] != remote_id:
            raise ValueError('Workstation identity changed at this address')
        with self.connect() as db:
            other = db.execute('SELECT id FROM stations WHERE remote_id=? AND id<>?', (remote_id, row['id'])).fetchone()
            if other:
                raise ValueError('This workstation is already registered at another address')
            current = db.execute('SELECT url,remote_id FROM stations WHERE id=?', (row['id'],)).fetchone()
            if current['url'] != row['url'] or current['remote_id'] not in (None, remote_id):
                raise ValueError('Workstation configuration changed; refresh and retry')
            db.execute('UPDATE stations SET remote_id=?,robot=? WHERE id=?', (remote_id, info['robot'], row['id']))
        return info


class LocalStationRoutes:
    """Local prefixed HTTP/WS use the existing handlers without an HTTP loop."""
    def __init__(self, app, registry):
        self.app, self.registry = app, registry

    async def __call__(self, scope, receive, send):
        prefix = '/s/' + self.registry.local_id + '/'
        path = scope.get('path', '')
        if scope['type'] in ('http', 'websocket') and path.startswith(prefix):
            tail = path[len(prefix):]
            if tail.startswith(('api/', 'video/')) or tail == 'ws':
                scope = dict(scope, path='/' + tail, raw_path=('/' + tail).encode())
        await self.app(scope, receive, send)


def install_hub(app, station, client, root):
    registry = Registry(station.file('database').with_name('workstations.sqlite3'), station.robot,
                        station.data.get('display_name') or station.robot.upper())
    app.state.registry = registry
    app.add_middleware(LocalStationRoutes, registry=registry)

    def status(row):
        try:
            info = registry.identify(row)
            state = client.call('snapshot') if row['local'] else get_json(row['url'] + '/api/state')
            run = state.get('run') or {}
            pending = state.get('pending') or []
            return {**row, 'robot': info['robot'], 'online': True, 'phase': run.get('phase', 'idle'),
                    'side': run.get('side'), 'recording': bool(state.get('recording')),
                    'prompt': bool(state.get('prompt')), 'pending': len(pending), 'error': ''}
        except Exception as exc:
            return {**row, 'online': False, 'error': str(exc) if isinstance(exc, ValueError)
                    else 'Workstation unavailable or not yet running the compatible UI'}

    @app.get('/hub.html')
    def hub_html():
        return HTMLResponse((root / 'hub.html').read_text(encoding='utf-8'))

    @app.get('/hub.js')
    def hub_js():
        from fastapi.responses import FileResponse
        return FileResponse(root / 'hub.js', media_type='text/javascript')

    @app.get('/api/station-info')
    def station_info():
        row = registry.get(registry.local_id)
        return {'id': registry.local_id, 'name': row['name'], 'robot': row['robot'], 'protocol': 1}

    @app.get('/hub/stations')
    def stations(check: bool = True):
        rows = registry.rows()
        if check:
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = list(pool.map(status, rows))
        return {'local_id': registry.local_id, 'items': rows}

    @app.post('/hub/stations')
    def save_station(body: dict):
        return status(registry.save(body))

    @app.get('/hub/statistics')
    def statistics(date: str | None = None):
        from urllib.parse import urlencode
        def collect(row):
            try:
                registry.identify(row)
                value = client.call('stats', {'date': date}) if row['local'] else get_json(
                    row['url'] + '/api/stats' + ('?' + urlencode({'date': date}) if date else ''), timeout=10)
                return {'id': row['id'], 'name': row['name'], 'available': True,
                        'rows': [{**r, 'station_id': row['id'], 'station_name': row['name']} for r in value['rows']]}
            except Exception:
                return {'id': row['id'], 'name': row['name'], 'available': False, 'rows': []}
        with ThreadPoolExecutor(max_workers=4) as pool:
            sources = list(pool.map(collect, registry.rows()))
        return {'sources': sources, 'rows': [r for s in sources for r in s['rows']], 'timezone': 'Asia/Shanghai'}

    @app.get('/s/{sid}/')
    def station_page(sid: str):
        registry.get(sid)
        return HTMLResponse((root / 'eval_gui.html').read_text(encoding='utf-8'))

    def remote(sid):
        row = registry.get(sid)
        if row['local']:
            raise HTTPException(404)
        try:
            registry.identify(row)
        except Exception as exc:
            raise HTTPException(503, str(exc) if isinstance(exc, ValueError) else 'Workstation unavailable') from None
        return row

    @app.api_route('/s/{sid}/{path:path}', methods=['GET', 'POST'])
    async def proxy(sid: str, path: str, request: Request):
        if not path.startswith(('api/', 'video/')) or '..' in path.split('/'):
            raise HTTPException(404)
        row = await run_in_threadpool(remote, sid)
        query = '?' + request.url.query if request.url.query else ''
        body = await request.body() if request.method == 'POST' else None
        headers = {k: v for k, v in request.headers.items() if k.lower() in ('content-type', 'range')}
        try:
            response = await run_in_threadpool(open_url, row['url'] + '/' + path + query,
                                               data=body, headers=headers, method=request.method, timeout=240)
        except HTTPError as exc:
            response = exc
        except OSError:
            # Never retry mutations: a timeout can occur after the remote action succeeded.
            raise HTTPException(502, 'Workstation request failed; check its status before retrying') from None
        copied = {k: v for k, v in response.headers.items() if k.lower() in
                  ('content-type', 'content-length', 'content-range', 'accept-ranges', 'cache-control')}
        def chunks():
            try:
                while True:
                    data = response.read(65536)
                    if not data:
                        break
                    yield data
            finally:
                response.close()
        return StreamingResponse(chunks(), status_code=response.status, headers=copied)

    @app.websocket('/s/{sid}/ws')
    async def proxy_ws(sock: WebSocket, sid: str):
        await sock.accept()
        try:
            row = await run_in_threadpool(remote, sid)
            from websockets.asyncio.client import connect
            url = row['url'].replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/ws'
            async with connect(url, proxy=None, open_timeout=5, max_size=None) as peer:
                async def incoming():
                    async for message in peer:
                        if isinstance(message, bytes):
                            await sock.send_bytes(message)
                        else:
                            await sock.send_text(message)
                async def disconnected():
                    while True:
                        if (await sock.receive())['type'] == 'websocket.disconnect':
                            return
                tasks = [asyncio.create_task(incoming()), asyncio.create_task(disconnected())]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            try:
                await sock.close(code=1013)
            except RuntimeError:
                pass

    return registry
