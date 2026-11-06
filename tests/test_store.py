from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sqlite3

import pytest
from store import Store, PendingEvaluation
from submission import install_api_hook, reconcile

RESULT = {'outcomes': {'A': {'success': True, 'partial_success': 1.0},
                       'B': {'success': False, 'partial_success': .5}}, 'preference': 'A', 'feedback': ''}


def test_each_robot_one_pending_person_snapshot_and_no_historical_import(tmp_path):
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'franka', '甲')
    store.register('b', 'yam', '乙')
    with pytest.raises(PendingEvaluation):
        store.register('c', 'yam', '乙')
    with pytest.raises(ValueError):
        store.register('b', 'yam', '甲')
    store.discard('b')
    store.register('c', 'yam', '乙')
    store.intent('historical', RESULT)
    assert store.confirm('historical', RESULT) is False
    assert store.stats()['rows'] == []


def test_confirmation_date_is_beijing_and_does_not_change_on_upload_or_retry(tmp_path):
    now = [datetime(2026, 10, 30, 15, 59, 59, tzinfo=timezone.utc)]
    store = Store(tmp_path / 'stats.db', clock=lambda: now[0])
    store.register('a', 'yam', '甲')
    store.intent('a', RESULT)
    assert store.stats()['rows'] == []
    now[0] = datetime(2026, 10, 30, 16, 0, tzinfo=timezone.utc)
    assert store.confirm('a', RESULT)
    now[0] = datetime(2026, 11, 2, tzinfo=timezone.utc)
    for _ in range(4):
        assert store.confirm('a', RESULT) is False
    assert store.stats()['rows'] == [{'date': '2026-10-31', 'person': '甲', 'robot': 'yam', 'count': 1}]
    assert store.stats('2026-10-30')['rows'] == []


def test_concurrent_duplicate_confirmation_counts_once(tmp_path):
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'yam', '甲')
    store.intent('a', RESULT)
    with ThreadPoolExecutor(max_workers=8) as workers:
        confirmed = list(workers.map(lambda _: store.confirm('a', RESULT), range(16)))
    assert sum(confirmed) == 1
    assert store.stats()['rows'][0]['count'] == 1


def test_crash_after_result_response_before_manifest_write_recovers(tmp_path):
    import json
    folder = tmp_path / 'a'
    folder.mkdir()
    (folder / 'manifest.json').write_text(json.dumps({'submitted': False}))
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'yam', '甲')
    store.intent('a', RESULT)
    store.confirm('a', RESULT)
    class API:
        def request(self, *args):
            raise AssertionError('Already-confirmed receipts need no network call')
    assert reconcile(API(), Store(store.path), tmp_path, 'a') == 'submitted'
    assert json.loads((folder / 'manifest.json').read_text())['submitted']


def test_lost_response_queries_remote_and_requires_matching_result(tmp_path):
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'yam', '甲')
    store.intent('a', RESULT)
    class API:
        response = {'state': 'completed', 'result': {'feedback': 'another result'}}
        def request(self, method, path):
            assert method == 'GET'
            return self.response
    api = API()
    assert reconcile(api, store, tmp_path, 'a') == 'unknown'
    assert store.stats()['rows'] == []
    api.response = {'state': 'completed', 'result': RESULT}
    assert reconcile(api, store, tmp_path, 'a') == 'submitted'
    assert store.stats()['rows'][0]['count'] == 1


def test_network_error_and_pending_remote_never_count(tmp_path):
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'yam', '甲')
    store.intent('a', RESULT)
    class API:
        def request(self, *args):
            raise TimeoutError()
    assert reconcile(API(), store, tmp_path, 'a') == 'unknown'
    API.request = lambda *a: {'state': 'pending'}
    assert reconcile(API(), store, tmp_path, 'a') == 'scored'
    assert store.stats()['rows'] == []


def test_result_hook_confirms_only_after_success_not_uploads(tmp_path):
    from types import SimpleNamespace
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'franka', '甲')
    class API:
        fail = True
        def request(self, method, path, body=None):
            if self.fail:
                raise TimeoutError('lost response')
            return {'ok': True}
    ev = SimpleNamespace(EvalAPI=API)
    install_api_hook(ev, store, tmp_path)
    api = API()
    with pytest.raises(TimeoutError):
        api.request('POST', '/assignments/a/result', RESULT)
    assert store.get('a')['state'] == 'unknown'
    assert store.stats()['rows'] == []
    api.fail = False
    api.request('POST', '/assignments/a/result', RESULT)
    api.request('POST', '/runs/r/dataset/complete', {})
    api.request('POST', '/assignments/a/result', RESULT)
    assert store.stats()['rows'][0]['count'] == 1


def test_lost_discard_confirmation_reconciles_without_workload(tmp_path):
    store = Store(tmp_path / 'stats.db')
    store.register('a', 'yam', '甲')
    store.discard_intent('a', 'test')
    store.state('a', 'unknown')
    class API:
        def request(self, method, route):
            assert method == 'GET'
            return {'state': 'aborted'}
    assert reconcile(API(), store, tmp_path, 'a') == 'discarded'
    assert store.pending() == []
    assert store.stats()['rows'] == []
