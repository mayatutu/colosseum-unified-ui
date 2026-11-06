"""Observe real Client API confirmations; preserve the original export/upload order."""
import json
from pathlib import Path


def mark_manifest(root, eid, **fields):
    path = Path(root) / eid / 'manifest.json'
    if not path.exists():
        return
    value = json.loads(path.read_text(encoding='utf-8'))
    value.update(fields)
    tmp = path.with_suffix('.ui.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def reconcile(api, store, root, eid):
    row = store.get(eid)
    if not row or row['confirmed_at']:
        if row and row['confirmed_at']:
            mark_manifest(root, eid, submitted=True)
        return 'submitted' if row and row['confirmed_at'] else 'historical'
    if row['state'] == 'discarded':
        mark_manifest(root, eid, discarded=True)
        return 'discarded'
    if not row['intent'] and not row['discard_reason']:
        return row['state']
    try:
        remote = api.request('GET', '/assignments/' + eid)
    except Exception:
        store.state(eid, 'unknown')
        return 'unknown'
    if row['discard_reason'] and remote.get('state') in ('aborted', 'discarded', 'cancelled'):
        store.discard(eid)
        mark_manifest(root, eid, discarded=True)
        return 'discarded'
    if row['intent'] and remote.get('state') == 'completed' and remote.get('result') == json.loads(row['intent']):
        store.confirm(eid, remote['result'], 'assignment_get')
        mark_manifest(root, eid, submitted=True)
        return 'submitted'
    if remote.get('state') == 'pending':
        store.state(eid, 'scored')
        return 'scored'
    store.state(eid, 'unknown')
    return 'unknown'


def install_api_hook(ev, store, root, on_assignment=None):
    original = ev.EvalAPI.request

    def request(api, method, path, body=None):
        is_result = method.upper() == 'POST' and path.endswith('/result')
        eid = path.split('/')[2] if is_result else None
        if is_result:
            row = store.get(eid)
            if row and row['confirmed_at']:
                return {'ok': True}
            store.intent(eid, body)
        try:
            result = original(api, method, path, body)
        except BaseException:
            if is_result:
                store.state(eid, 'unknown')
            raise
        if is_result:
            store.confirm(eid, body)
        if method.upper() == 'POST' and path == '/next' and on_assignment:
            on_assignment(result)
        return result
    ev.EvalAPI.request = request
    return original
