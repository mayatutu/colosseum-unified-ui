"""Persist one scene scalar without rewriting other private YAML settings."""
import json
import os
from pathlib import Path
import stat
import tempfile

import yaml


def read_scene(path):
    value = yaml.safe_load(Path(path).read_text(encoding='utf-8')).get('scene', '')
    if not isinstance(value, str):
        raise ValueError('The saved scene must be text')
    return value


def save_scene(path, value, expected):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 4000:
        raise ValueError('Scene must contain 1 to 4000 characters')
    value, path = value.strip(), Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Invalid robot configuration file')
    original = path.read_bytes()
    text = original.decode('utf-8')
    document, node = yaml.safe_load(text), yaml.compose(text, Loader=yaml.SafeLoader)
    if not isinstance(document, dict) or not isinstance(node, yaml.MappingNode):
        raise ValueError('Invalid robot configuration mapping')
    current = document.get('scene', '')
    if not isinstance(expected, str) or current != expected:
        raise ValueError('The saved scene changed. Refresh before saving again.')
    if value == current:
        return value
    matches = [v for k, v in node.value if k.value == 'scene']
    if len(matches) > 1:
        raise ValueError('Duplicate scene fields')
    scalar = json.dumps(value, ensure_ascii=False)
    newline = '\r\n' if '\r\n' in text else '\n'
    if matches:
        old = matches[0]
        if not isinstance(old, yaml.ScalarNode):
            raise ValueError('The saved scene must be text')
        start, end = old.start_mark.index, old.end_mark.index
        updated = text[:start] + scalar + (newline if text[start:end].endswith('\n') else '') + text[end:]
    else:
        updated = text + ('' if text.endswith('\n') else newline) + 'scene: ' + scalar + newline
    if yaml.safe_load(updated) != {**document, 'scene': value}:
        raise ValueError('Scene cannot be changed without affecting other settings')
    mode = stat.S_IMODE(path.stat().st_mode)
    backup_fd, backup = tempfile.mkstemp(prefix='.' + path.name + '.before-scene-', dir=path.parent)
    with os.fdopen(backup_fd, 'wb') as output:
        output.write(original)
        output.flush()
        os.fsync(output.fileno())
    os.chmod(backup, mode)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.scene-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(updated.encode('utf-8'))
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        if path.read_bytes() != original:
            raise ValueError('Robot configuration changed. Refresh before saving again.')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return value
