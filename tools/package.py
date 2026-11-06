"""Package reviewable candidate sources/evidence, excluding live data, keys and caches."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
excluded = {'.git', 'data', '__pycache__', '.pytest_cache', '.venv', '.venv-gui', 'browser-profile'}
files = [p for p in root.rglob('*') if p.is_file() and not (set(p.relative_to(root).parts) & excluded)
         and p.suffix != '.zip' and p.name != 'PACKAGE-MANIFEST.json']
manifest = {'version': 1, 'status': 'local candidate; not deployed',
            'files': [{'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in sorted(files)]}
manifest_path = root / 'PACKAGE-MANIFEST.json'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
destination = root.parent / 'colosseum-unified-ui-v1-candidate.zip'
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files + [manifest_path]:
        archive.write(path, root.name + '/' + path.relative_to(root).as_posix())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
print(destination)
print('SHA256 ' + hashlib.sha256(destination.read_bytes()).hexdigest())
