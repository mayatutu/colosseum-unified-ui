"""Apply the reviewed station selection UI update on the YAM workstation, only after user approval."""
import argparse
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import tarfile
import time
import urllib.request
import zipfile

ROOT = Path('/path/to/colosseum-unified-ui')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with zipfile.ZipFile(args.bundle) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        payload = {name: archive.read(name) for name in manifest['files']}
    for name, record in manifest['files'].items():
        assert name in {'station_hub.py', 'station.js', 'hub.html', 'app.py', 'hub.js', 'eval_gui.html', 'i18n.js'}, 'Unexpected update path'
        assert hashlib.sha256(payload[name]).hexdigest() == record['after']
        if name.endswith('.py'):
            ast.parse(payload[name].decode('utf-8-sig'), filename=name)
    if not args.apply:
        print('Bundle verified; no changes made.')
        return
    for name, record in manifest['files'].items():
        path = ROOT / name
        before = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        assert before == record['before'], 'Source changed since review: ' + name
    http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(route):
        with http.open('http://127.0.0.1:8772' + route, timeout=15) as response:
            return json.load(response)
    state = get('/api/state')
    assert not state['recording'] and not state['preview'], 'UI is using hardware; update deferred'
    page = get('/api/evals?paginated=true&limit=100000')
    assert not any(row.get('busy') for row in page['items']), 'Submission job is active'
    pids = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            command = (proc / 'cmdline').read_bytes().split(b'\0')
            if str(ROOT / 'app.py').encode() in command and b'8772' in command:
                pids.append(int(proc.name))
        except OSError:
            pass
    assert len(pids) == 1, 'Expected exactly one new UI process'
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    backup = ROOT.parent / 'backups' / ('unified-ui-station-hub-' + stamp)
    backup.mkdir(mode=0o700)
    with tarfile.open(backup / 'before.tar.gz', 'w:gz') as archive:
        for name, record in manifest['files'].items():
            if record['before'] is not None:
                archive.add(ROOT / name, arcname=name)
    with tarfile.open(backup / 'before.tar.gz') as archive:
        for name, record in manifest['files'].items():
            if record['before'] is not None:
                assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == record['before']
    with sqlite3.connect('file:' + str(ROOT / 'data/yam.sqlite3') + '?mode=ro', uri=True) as source:
        with sqlite3.connect(backup / 'yam.sqlite3') as destination:
            source.backup(destination)
    registry_db = ROOT / 'data/workstations.sqlite3'
    if registry_db.exists():
        with sqlite3.connect('file:' + str(registry_db) + '?mode=ro', uri=True) as source:
            with sqlite3.connect(backup / 'workstations.sqlite3') as destination:
                source.backup(destination)
    (backup / 'update-manifest.json').write_text(json.dumps(manifest, indent=2))
    for path in backup.iterdir():
        path.chmod(0o600)
    os.kill(pids[0], signal.SIGTERM)
    for _ in range(150):
        if not Path('/proc/' + str(pids[0])).exists():
            break
        time.sleep(.2)
    else:
        raise RuntimeError('New UI did not exit; no force kill or source overwrite performed')
    for name, content in payload.items():
        temporary = ROOT / (name + '.station-hub-update')
        temporary.write_bytes(content)
        temporary.replace(ROOT / name)
    import sys
    sys.path.insert(0, str(ROOT))
    from station_hub import Registry
    registry = Registry(ROOT / 'data/workstations.sqlite3', 'yam', 'YAM (the YAM workstation)')
    if not any(row['url'] == 'http://franka-client.example.invalid:8772' for row in registry.rows()):
        registry.save({'name': 'Franka (the Policy host)', 'address': 'http://franka-client.example.invalid:8772'})
    with (ROOT / 'data/gui.log').open('ab') as log:
        process = subprocess.Popen([str(ROOT / 'start-yam.sh'), '8772'], cwd=ROOT,
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    (ROOT / 'data/station-hub-update.json').write_text(json.dumps({'backup': str(backup), 'pid': process.pid,
        'manifest': manifest, 'hardware_tested': False}, indent=2))
    print(json.dumps({'backup': str(backup), 'pid': process.pid, 'files': list(payload)}))


if __name__ == '__main__':
    main()
