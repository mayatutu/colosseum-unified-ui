"""Stage an isolated Franka UI candidate. Never start services or import robot code."""
import argparse
import ast
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import tarfile
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--prepare-env', action='store_true')
    args = parser.parse_args()
    with zipfile.ZipFile(args.bundle) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        payload = {}
        for name, digest in manifest['files'].items():
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
            content = archive.read(name)
            assert sha(content) == digest, name
            if name.endswith('.py'):
                ast.parse(content.decode('utf-8-sig'), filename=name)
            payload[name] = content
    if not args.stage:
        print(json.dumps({'bundle_verified': True, 'files': len(payload), 'mutated': False}))
        return
    base = Path('/path/to/franka-workspace')
    target = base / 'colosseum-unified-ui-v1'
    assert not target.exists(), 'Candidate directory already exists; no overwrite allowed'
    client_python = base / 'envs/droid-client/bin/python'
    assert client_python.is_file()
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    backup = base / 'backups' / ('unified-ui-stage-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    client = base / 'repos/colosseum-client-local'
    legacy = base / 'colosseum-eval-web'
    originals = list((client / 'src').rglob('*.py')) + list(legacy.glob('*.py'))
    originals += [p for p in (legacy / 'static').rglob('*') if p.is_file() and p.suffix in ('.html', '.js', '.css')]
    originals += [base / 'private/robot-minipc.yaml', legacy / 'config.yaml']
    before = {str(p): sha(p.read_bytes()) for p in originals}
    with tarfile.open(backup / 'baseline.tar.gz', 'w:gz') as archive:
        for p in originals:
            archive.add(p, arcname=p.relative_to(base).as_posix(), recursive=False)
    with tarfile.open(backup / 'baseline.tar.gz') as archive:
        for p in originals:
            assert sha(archive.extractfile(p.relative_to(base).as_posix()).read()) == before[str(p)]
    (backup / 'baseline.json').write_text(json.dumps(before, indent=2))
    for p in backup.iterdir():
        p.chmod(0o600)
    target.mkdir(mode=0o700)
    for name, content in payload.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        assert sha(path.read_bytes()) == manifest['files'][name]
    data = target / 'data'
    data.mkdir(mode=0o700)
    receipt = {'backup': str(backup), 'root': str(target), 'files': manifest['files'],
               'services_started': False, 'environment_ready': False,
               'status': 'files_staged_not_started', 'hardware_tested': False,
               'multi_station_gateway_implemented': False}
    receipt_path = data / 'franka-staging.json'
    receipt_path.write_text(json.dumps(receipt, indent=2))
    if args.prepare_env:
        subprocess.run([str(client_python), '-m', 'venv', str(target / '.venv-gui')], check=True)
        gui_python = target / '.venv-gui/bin/python'
        subprocess.run([str(gui_python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--no-cache-dir', '-r', str(target / 'requirements-gui.txt')], check=True)
        subprocess.run([str(gui_python), '-m', 'pip', 'check'], check=True)
        # --inspect only reads paths and config; it does not import Runtime.
        subprocess.run([str(gui_python), '-B', str(target / 'worker.py'), '--station',
                        str(target / 'configs/franka.yaml'), '--inspect'], check=True)
        receipt['environment_ready'] = True
        receipt['status'] = 'environment_ready_not_started'
    receipt['original_files_changed'] = [name for name, digest in before.items()
                                         if sha(Path(name).read_bytes()) != digest]
    receipt_path.write_text(json.dumps(receipt, indent=2))
    print(json.dumps({k: v for k, v in receipt.items() if k != 'files'}))


if __name__ == '__main__':
    main()
