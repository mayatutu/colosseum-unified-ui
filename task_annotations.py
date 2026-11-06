"""Task-level human difficulty, carried by the existing LeRobot exporter."""
from contextlib import contextmanager
import json
from pathlib import Path


def difficulty(value, *, required=False):
    if value is None or value == '':
        if required:
            raise ValueError('Task difficulty is required before submitting')
        return None
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int or not 1 <= value <= 10:
        raise ValueError('Task difficulty must be an integer from 1 to 10')
    return value


def save_difficulty(folder, value):
    folder = Path(folder)
    manifest = folder / 'manifest.json'
    document = json.loads(manifest.read_text(encoding='utf-8'))
    for run in document['assignment']['runs']:
        marker = folder / run['id'] / 'lerobot/meta/colosseum.json'
        if marker.exists() and json.loads(marker.read_text()).get('task_difficulty') != value:
            raise ValueError('Task difficulty cannot change after a dataset has been exported')
    if value is None:
        document.pop('task_difficulty', None)
        document.pop('task_difficulty_scale', None)
    else:
        document.update(task_difficulty=value, task_difficulty_scale=10)
    temporary = manifest.with_suffix('.difficulty.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(manifest)


@contextmanager
def annotate_exports(exporter):
    original = exporter.export_trial

    def export(path, *args, metadata, **kwargs):
        document = json.loads((Path(path).parent / 'manifest.json').read_text(encoding='utf-8'))
        value = difficulty(document.get('task_difficulty'), required=True)
        return original(path, *args, metadata={**metadata, 'task_difficulty': value,
                                               'task_difficulty_scale': 10}, **kwargs)
    exporter.export_trial = export
    try:
        yield
    finally:
        exporter.export_trial = original
