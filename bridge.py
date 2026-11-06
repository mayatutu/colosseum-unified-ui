"""Concurrent JSON-lines RPC over local pipes (no listening control port)."""
import itertools
import json
import os
import queue
import subprocess
import threading


class RemoteError(RuntimeError):
    def __init__(self, message, status=500):
        super().__init__(message)
        self.status_code = status


class Bridge:
    def __init__(self, command, cwd=None, log_path=None):
        self.command, self.cwd = command, cwd
        self.log_path = log_path
        self.log_file = None
        self.proc = None
        self.lock = threading.Lock()
        self.pending = {}
        self.ids = itertools.count(1)

    def start(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            if self.log_path:
                from pathlib import Path
                path = Path(self.log_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                self.log_file = path.open('a', encoding='utf-8')
            self.proc = subprocess.Popen(self.command, cwd=self.cwd, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=self.log_file or subprocess.DEVNULL,
                                         text=True, encoding='utf-8', bufsize=1,
                                         env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'})
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        try:
            for line in proc.stdout:
                try:
                    message = json.loads(line)
                    with self.lock:
                        waiting = self.pending.get(message.get('id'))
                    if waiting:
                        waiting.put(message)
                except (ValueError, AttributeError):
                    continue
        finally:
            with self.lock:
                if self.proc is proc:
                    for waiting in self.pending.values():
                        waiting.put({'error': 'Station worker exited; inspect the local worker log', 'status': 503})
                    if self.log_file:
                        self.log_file.close()

    def call(self, method, params=None, timeout=240):
        # Do not automatically restart a dead worker: lifecycle startup can affect live services.
        if self.proc is None:
            self.start()
        waiting = queue.Queue()
        with self.lock:
            if self.proc.poll() is not None:
                raise RemoteError('Station worker exited; restart the UI after checking its log', 503)
            key = next(self.ids)
            self.pending[key] = waiting
            try:
                self.proc.stdin.write(json.dumps({'id': key, 'method': method, 'params': params or {}}) + '\n')
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self.pending.pop(key, None)
                raise RemoteError('Station worker connection closed', 503)
        try:
            message = waiting.get(timeout=timeout)
        except queue.Empty:
            raise RemoteError('Operation is still running or its result is unknown; check station status', 504)
        finally:
            with self.lock:
                self.pending.pop(key, None)
        if 'error' in message:
            raise RemoteError(message['error'], message.get('status', 500))
        return message.get('result')

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.call('shutdown', timeout=180)
            finally:
                # EOF asks the process to finish cleanup; never force-kill a live robot worker.
                self.proc.stdin.close()


def serve(dispatch):
    import sys
    output, input_stream = sys.stdout, sys.stdin
    sys.stdout = sys.stderr  # project print statements must not corrupt the protocol
    output_lock = threading.Lock()

    def answer(message):
        try:
            result = dispatch(message['method'], message.get('params', {}))
            response = {'id': message['id'], 'result': result}
        except BaseException as e:
            response = {'id': message.get('id'), 'error': str(e),
                        'status': getattr(e, 'status_code', 400 if isinstance(e, ValueError) else 500)}
        with output_lock:
            output.write(json.dumps(response, ensure_ascii=False) + '\n')
            output.flush()
    threads = []
    for line in input_stream:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        thread = threading.Thread(target=answer, args=(message,), daemon=False)
        thread.start()
        threads = [x for x in threads if x.is_alive()] + [thread]
    for thread in threads:
        thread.join()
