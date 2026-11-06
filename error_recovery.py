"""Local-only cleanup requested by the operator before starting a fresh A/B."""
import json
from pathlib import Path
import re
import shutil
import time

from submission import mark_manifest


def _child(parent, name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid evaluation artifact ID')
    path = parent / name
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Linked evaluation artifacts cannot be deleted')
    if path.resolve().parent != parent.resolve():
        raise ValueError('Evaluation artifact escapes its parent')
    return path


def cleanup(root, eid, store):
    root = Path(root).resolve()
    folder = _child(root, eid)
    manifest = folder / 'manifest.json'
    if manifest.is_symlink():
        raise ValueError('Linked manifest cannot be used for cleanup')
    document = json.loads(manifest.read_text(encoding='utf-8'))
    recovery = document.get('error_recovery')
    row = store.get(eid)
    if not recovery or recovery.get('mode') != 'local_restart' or not row:
        raise ValueError('Explicit local restart is required before deleting captures')
    if row['confirmed_at'] or row['intent'] or document.get('submitted') or document.get('uploaded'):
        raise ValueError('Submitted or uploaded data cannot be deleted here')
    if recovery.get('cleanup_complete'):
        return
    assignment = document['assignment']
    if assignment['id'] != eid:
        raise ValueError('Evaluation identity mismatch')
    paths = [_child(folder, run['id']) for run in assignment['runs']]
    paths.append(_child(folder, 'ui-initial-scene'))
    cache = root.parent / 'eval_review_cache'
    if cache.exists():
        if cache.is_symlink() or cache.resolve().parent != root.parent:
            raise ValueError('Linked preview cache cannot be deleted')
        paths.append(_child(cache, eid))
    # Validate the whole deletion set before touching any artifact. Never follow links.
    for path in paths:
        if path.exists():
            if not path.is_dir():
                raise ValueError('Expected artifact directory: ' + path.name)
            for child in path.rglob('*'):
                if child.is_symlink() or (hasattr(child, 'is_junction') and child.is_junction()):
                    raise ValueError('Linked artifact cannot be deleted: ' + child.name)
                if not child.resolve().is_relative_to(path.resolve()):
                    raise ValueError('Artifact escapes its directory')
    for path in paths:
        if path.exists():
            shutil.rmtree(path)
    mark_manifest(root, eid, discarded=True, error_recovery={**recovery, 'cleanup_complete': True,
                                           'cleaned_at': time.time()})
