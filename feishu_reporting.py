"""Per-evaluation receipts for the installed original Feishu form sender."""
import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import shutil
import sys
import time

import yaml
import scene_reference
from evaluation_lock import evaluation_lock
from station import Station
from store import Store

REPORT = 'ui-feishu.json'
PHOTOS = 'ui-feishu-photos'


def sender_settings(station):
    """Keep the original sender separate from candidate service maintenance.

    An explicitly supplied reporting section is authoritative: malformed values
    must not silently select the legacy maintenance sender instead.
    """
    if 'feishu_reporting' in station.data:
        config = station.data['feishu_reporting']
        if not isinstance(config, dict) or any(
                not isinstance(config.get(key), str) or not config[key].strip()
                for key in ('root', 'python')):
            raise ValueError('feishu_reporting must configure both root and python')
        return {key: config[key] for key in ('root', 'python')}
    config = station.data.get('maintenance', {})
    if not isinstance(config, dict):
        raise ValueError('Legacy Feishu sender configuration is invalid')
    return {key: config.get(key) for key in ('root', 'python')}


def sender_root(station):
    value = sender_settings(station)['root']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Feishu sender root is not configured')
    return Path(value).expanduser()


def sender_python(station):
    value = sender_settings(station)['python']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Feishu sender python is not configured')
    return value


def options(station):
    enabled = station.robot == 'franka' and station.data.get('feishu_reporting_enabled') is True
    if not enabled:
        return {'enabled': False, 'devices': []}
    config = yaml.safe_load((sender_root(station) / 'config.yaml').read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError('The original Feishu form configuration is invalid')
    if not config.get('feishu', {}).get('enabled', True) or not config.get('feishu', {}).get('form_url'):
        raise ValueError('The original Feishu form is not enabled')
    return {'enabled': True, 'devices': [x['name'] if isinstance(x, dict) else x for x in config.get('devices', [])]}


def selection(station, form):
    config = options(station)
    if not config['enabled']:
        return None
    value = form.get('scene', '')
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 4000:
        raise ValueError('Scene must contain 1 to 4000 characters')
    device = form.get('feishu_device')
    if device not in config['devices']:
        raise ValueError('Select the original Feishu device number')
    return {'enabled': True, 'scenario': value.strip(), 'device': device}


def origin(folder):
    path = Path(folder) / 'ui-origin.json'
    return json.loads(path.read_text(encoding='utf-8')).get('feishu') if path.exists() else None


def token(pid):
    try:
        return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def status(folder):
    path = Path(folder) / REPORT
    if not path.exists():
        return {'status': 'queued' if origin(folder) else 'not_enabled', 'error': ''}
    data = json.loads(path.read_text(encoding='utf-8'))
    if data['status'] in ('preparing', 'sending') and Path('/proc').exists():
        if not data.get('process_token') or token(data.get('pid')) != data['process_token']:
            data.update(status='unknown', error='The reporting process stopped. Check the Feishu table before retrying.')
    return data


def write(folder, data):
    path = Path(folder) / REPORT
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({**data, 'updated_at': time.time()}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def entry(folder, row):
    folder = Path(folder)
    selected = origin(folder)
    if not row or not row['confirmed_at'] or not selected:
        raise ValueError('Only confirmed evaluations with Feishu enabled can be reported')
    document = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    result = json.loads(row['intent'])
    value = {'instruction': document['assignment']['task']['instruction'], 'evaluator': row['person'],
             'scenario': selected['scenario'], 'device': selected['device'],
             'score_a': round(result['outcomes']['A']['partial_success'] * 100),
             'score_b': round(result['outcomes']['B']['partial_success'] * 100),
             'prefer': result['preference'], 'feedback': result['feedback']}
    # Keep the original sender's expected filename and the exact captured image bytes.
    for side in ('left', 'right'):
        source = scene_reference.image_path(folder, side + '_image')
        if not source:
            raise ValueError('Feishu scene photos are missing')
        target = folder / PHOTOS / side / '000000.png'
        if target.is_symlink() or target.parent.is_symlink() or target.parent.parent.is_symlink():
            raise ValueError('Invalid Feishu photo directory')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        value['scene_' + side] = str(target)
    return value


def cleanup(folder):
    folder = Path(folder)
    if status(folder)['status'] != 'sent':
        return
    scene_reference.cleanup(folder)
    for side in ('left', 'right'):
        target = folder / PHOTOS / side / '000000.png'
        if target.is_symlink() or target.parent.is_symlink() or target.parent.parent.is_symlink():
            raise ValueError('Invalid Feishu photo directory')
        target.unlink(missing_ok=True)
        if target.parent.exists():
            target.parent.rmdir()
    if (folder / PHOTOS).exists():
        (folder / PHOTOS).rmdir()


def retry(folder, checked_missing=False):
    with evaluation_lock(folder, blocking=False):
        current = status(folder)
        if current['status'] == 'sent':
            return
        if current['status'] == 'unknown' and not checked_missing:
            raise ValueError('Check that this evaluation is absent from Feishu before retrying')
        if current['status'] not in ('error', 'unknown'):
            raise ValueError('Feishu submission is already pending or running')
        write(folder, {'status': 'queued', 'error': ''})


def submit(station, folder, row, sender=None):
    """Never retry automatically after a possible form submission."""
    folder = Path(folder)
    with evaluation_lock(folder):
        current = status(folder)
        if current['status'] == 'sent':
            cleanup(folder)
            return
        if current['status'] != 'queued':
            return
        state = {'status': 'preparing', 'error': '', 'pid': os.getpid(), 'process_token': token(os.getpid())}
        write(folder, state)
        class Output:
            def write(self, text):
                if '[feishu] submitting:' in text:
                    state['status'] = 'sending'
                    write(folder, state)
                return sys.__stdout__.write(text)
            def flush(self):
                sys.__stdout__.flush()
        try:
            payload = entry(folder, row)
            if sender is None:
                # Same guarded function, form config, translations, success check and receipts as the old UI.
                from legacy_host import LegacyHost
                host = LegacyHost(sender_root(station), 'franka', '', '')
                host.load_module()
                config = host.module.CFG
                if not config.get('feishu', {}).get('enabled', True):
                    raise ValueError('The original Feishu form is not enabled')
                sender = lambda value: host.module.submit_feishu(value, config)
            with redirect_stdout(Output()):
                if sender(payload) is not True:
                    raise RuntimeError('The original Feishu sender did not confirm success')
            state.update(status='sent', error='', confirmed_at=time.time())
            write(folder, state)
        except Exception:
            # Full diagnostics remain private in the per-evaluation log; the browser receives no form tokens.
            import traceback
            traceback.print_exc()
            state.update(status='unknown' if state['status'] == 'sending' else 'error',
                         error='Feishu confirmation is unknown. Check the table before retrying.' if state['status'] == 'sending'
                         else 'Feishu submission failed before confirmation. You can retry Feishu only.')
            write(folder, state)
            return
        try:
            cleanup(folder)
        except (OSError, ValueError):
            import traceback
            traceback.print_exc()  # A cleanup error must never cause another form submission.


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--station', required=True)
    parser.add_argument('--folder', required=True)
    args = parser.parse_args()
    station = Station.load(args.station)
    folder = Path(args.folder).resolve()
    config = yaml.safe_load(station.file('robot_config').read_text(encoding='utf-8'))
    root = (station.file('client_root') / config['evaluation_dir']).resolve()
    if folder.parent != root:
        raise ValueError('Evaluation folder is outside the configured root')
    submit(station, folder, Store(station.file('database')).get(folder.name))
