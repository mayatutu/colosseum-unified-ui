"""Read existing model metadata and retain the legacy Policy log stream."""
import json
import threading
from pathlib import Path
from urllib.parse import urlsplit


def model_name(path):
    try:
        model = json.loads(Path(path).read_text(encoding='utf-8')).get('model', {})
        if model.get('name'):
            return str(model['name'])
        url = urlsplit(model.get('url', ''))
        return url.path.strip('/').split('/')[-1] if url.hostname == 'huggingface.co' else ''
    except (OSError, ValueError, TypeError, AttributeError):
        return ''


def tail(path, size=64000):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - size))
            return stream.read().decode('utf-8', errors='replace')
    except FileNotFoundError:
        return ''


class LogMirror:
    def __init__(self, path):
        self.path = Path(path)
        self.previous = tail(self.path, 40000)
        self.lock = threading.Lock()

    def append_snapshot(self, current):
        if not isinstance(current, str) or not current:
            return
        with self.lock:
            previous = self.previous
            if current == previous or previous.endswith(current):
                self.previous = current
                return
            overlap = min(len(previous), len(current))
            # Legacy buffer returns a suffix; find its overlap with the last snapshot.
            while overlap and previous[-overlap:] != current[:overlap]:
                overlap -= 1
            added = current[overlap:]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8', newline='') as stream:
                if previous and not overlap:
                    stream.write('\n[Policy log buffer changed; earlier output may be unavailable]\n')
                stream.write(added)
            self.previous = current
