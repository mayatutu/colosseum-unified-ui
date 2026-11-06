"""Owned, temporary left/right placement images, outside all dataset folders."""
import hashlib
import json
from pathlib import Path
import tempfile
import time

CAMERAS = ('left_image', 'right_image')
DIRECTORY = 'ui-initial-scene'


def describe(folder):
    folder = Path(folder)
    directory = folder / DIRECTORY
    if not directory.exists():
        return None
    if directory.is_symlink():
        raise ValueError('Invalid initial scene reference directory')
    marker = directory / 'reference.json'
    if not marker.exists():
        return None
    if marker.is_symlink():
        raise ValueError('Invalid initial scene reference metadata')
    data = json.loads(marker.read_text(encoding='utf-8'))
    if data.get('version') != 1 or data.get('evaluation_id') != folder.name or set(data.get('sha256', {})) != set(CAMERAS):
        raise ValueError('Invalid initial scene reference metadata')
    for camera in CAMERAS:
        path = directory / (camera + '.png')
        if path.is_symlink() or not path.is_file():
            raise ValueError('Initial scene reference image is missing')
    return data


def capture(folder, images):
    from PIL import Image
    import numpy as np
    folder = Path(folder)
    if describe(folder):
        return  # Never replace the original scene with the second run's placement.
    if set(CAMERAS) - set(images):
        raise ValueError('Both left and right cameras are required to save the initial scene')
    staging = Path(tempfile.mkdtemp(prefix='.ui-initial-scene-', dir=folder))
    try:
        hashes = {}
        for camera in CAMERAS:
            rgb = np.asarray(images[camera])
            if rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 1 or rgb.dtype != np.uint8:
                raise ValueError('Invalid initial scene camera image: ' + camera)
            path = staging / (camera + '.png')
            Image.fromarray(rgb).save(path, format='PNG')
            hashes[camera] = hashlib.sha256(path.read_bytes()).hexdigest()
        data = {'version': 1, 'evaluation_id': folder.name, 'captured_at_ns': time.time_ns(), 'sha256': hashes}
        (staging / 'reference.json').write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
        staging.rename(folder / DIRECTORY)
    finally:
        if staging.exists():
            for name in [*(camera+'.png' for camera in CAMERAS), 'reference.json']:
                (staging / name).unlink(missing_ok=True)
            staging.rmdir()


def image_path(folder, camera):
    if camera not in CAMERAS:
        return None
    data = describe(folder)
    if not data:
        return None
    path = Path(folder) / DIRECTORY / (camera + '.png')
    if hashlib.sha256(path.read_bytes()).hexdigest() != data['sha256'][camera]:
        raise ValueError('Initial scene reference image changed')
    return path


def cleanup(folder, *, closed=False):
    folder = Path(folder)
    origin = folder / 'ui-origin.json'
    if not closed and origin.exists() and json.loads(origin.read_text(encoding='utf-8')).get('feishu', {}).get('enabled'):
        receipt = folder / 'ui-feishu.json'
        if not receipt.exists() or json.loads(receipt.read_text(encoding='utf-8')).get('status') != 'sent':
            return False
    data = describe(folder)
    if not data:
        return False
    document = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    runs = document['assignment']['runs']
    if not closed:
        if not runs:
            return False
        for run in runs:
            path = folder / run['id']
            status = path / 'recording-status.json'
            if not (path / 'frames.jsonl').exists() or not status.exists() or json.loads(status.read_text()).get('complete') is not True:
                return False
    # Delete only the exact owned files. Leave unrelated files and recording data alone.
    paths = [image_path(folder, camera) for camera in CAMERAS]
    for path in paths:
        path.unlink()
    (folder / DIRECTORY / 'reference.json').unlink()
    try:
        (folder / DIRECTORY).rmdir()
    except OSError:
        pass
    return True
