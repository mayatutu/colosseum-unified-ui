"""Reuse installed maintenance code, without invoking its evaluation/upload/Feishu routes.

If the old Web service is alive, forward maintenance requests to it. Otherwise
load its module under its existing Python environment and own Policy lifecycle.
"""
import argparse
import importlib.util
import json
import os
import socket
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from bridge import serve


class LegacyHost:
    ROUTES = {'restart_policy': '/api/restart_policy', 'restart_docker': '/api/restart_docker',
              'restart_can': '/api/restart_can'}

    def __init__(self, root, robot, url, policy_url):
        self.root, self.robot, self.url, self.policy_url = Path(root), robot, url.rstrip('/'), policy_url
        self.module = None
        self.external = False
        self.started = False
        self.lock = threading.RLock()
        self.http = build_opener(ProxyHandler({}))
        self.last = {}

    def http_request(self, route, post=False):
        req = Request(self.url + route, data=b'{}' if post else None,
                      headers={'Content-Type': 'application/json'})
        with self.http.open(req, timeout=120 if post else 4) as response:
            return json.load(response)

    def initialize(self):
        if self.started:
            return
        try:
            state = self.http_request('/api/state')
            if not isinstance(state, dict):
                raise ValueError('Unexpected legacy state')
            self.external = True
        except HTTPError as e:
            raise RuntimeError('Existing Web service returned HTTP ' + str(e.code) + '; no second supervisor was started')
        except (URLError, OSError, ValueError):
            pass
        if not self.external or self.robot == 'franka':
            self.load_module()
        if not self.external:
            if self.robot == 'yam':
                self.module.start_policy_server()
                threading.Thread(target=self.module._policy_watchdog, daemon=True).start()
            for name in ('start_policy_logs', 'start_franka_logs'):
                if hasattr(self.module, name):
                    getattr(self.module, name)()
        self.started = True

    def load_module(self):
        # Import does not execute __main__; verified on the two installed legacy revisions.
        sys.path.insert(0, str(self.root))
        os.chdir(self.root)
        spec = importlib.util.spec_from_file_location('installed_eval_web', self.root / 'app.py')
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)

    def policy_pids(self):
        """Identify the configured YAM supervisor and descendants, including externally owned ones."""
        import yaml
        config = yaml.safe_load((self.root / 'config.yaml').read_text(encoding='utf-8'))
        command = config.get('policy_server', {}).get('start_cmd', [])
        roots, children = set(), {}
        if not command:
            return []
        for path in Path('/proc').glob('[0-9]*'):
            try:
                args = (path / 'cmdline').read_bytes().decode(errors='replace').split('\0')
                pid = int(path.name)
                if command[0] in args and all(arg in args for arg in command[1:]):
                    roots.add(pid)
                parent = int((path / 'stat').read_text().rsplit(')', 1)[1].split()[1])
                children.setdefault(parent, []).append(pid)
            except (OSError, ValueError, IndexError):
                continue
        todo = list(roots)
        while todo:
            for pid in children.get(todo.pop(), []):
                if pid not in roots:
                    roots.add(pid)
                    todo.append(pid)
        return sorted(roots)

    def startup_check(self):
        if self.module and self.robot == 'franka':
            # Exact existing health check, including loaded model worker detection.
            ok = self.module.start_policy_server()
            return {'ok': bool(ok), 'external': self.external, 'detail': 'Franka Policy startup check', 'last': self.last}
        return self.status()

    def status(self):
        parts = urlsplit(self.policy_url)
        try:
            if parts.hostname in ('127.0.0.1', 'localhost', '::1') and Path('/proc/net/tcp').exists():
                # Passive local listener check: bare TCP probes pollute WebSocket logs.
                port = parts.port or 80
                ok = any(int(row.split()[1].rsplit(':', 1)[1], 16) == port and row.split()[3] == '0A'
                         for path in (Path('/proc/net/tcp'), Path('/proc/net/tcp6')) if path.exists()
                         for row in path.read_text().splitlines()[1:])
            else:
                with socket.create_connection((parts.hostname, parts.port or 80), timeout=3):
                    ok = True
        except OSError:
            ok = False
        return {'ok': ok, 'external': self.external,
                'detail': 'Policy TCP reachable (protocol/model readiness is checked by the Client)' if ok else 'Policy unavailable',
                'last': self.last}

    def call(self, method, params):
        with self.lock:
            if method == 'shutdown':
                # As upstream, stop only a locally owned Policy; external services remain available.
                if self.module and not self.external and self.robot == 'yam':
                    self.module._policy_restarting = True
                    proc = self.module._POLICY_PROC
                    if proc and proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=30)
                return {'ok': True}
            self.initialize()
            if method == 'startup':
                return self.startup_check()
            if method == 'status':
                return self.status()
            if method == 'logs':
                if self.external:
                    state = self.http_request('/api/state')
                    return {k: v for k, v in state.items() if 'log' in k.lower() or 'policy' in k.lower()}
                result = {}
                for key in ('POLICY_BUF', 'FRANKA_BUF'):
                    buf = getattr(self.module, key, None)
                    if buf is not None:
                        # Different legacy revisions use different ring-buffer readers.
                        for attr in ('text', 'get', 'read'):
                            getter = getattr(buf, attr, None)
                            if callable(getter):
                                result[key] = getter()
                                break
                return result
            if method == 'pids':
                return self.policy_pids()
            if method == 'stop_policy':
                if self.external or self.robot == 'franka':
                    return {'ok': True, 'detail': 'Policy was started outside this UI; left running'}
                self.module._policy_restarting = True
                proc = self.module._POLICY_PROC
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=30)
                return {'ok': True}
            if method == 'start_policy':
                if self.robot == 'franka':
                    return self.startup_check()
                if self.external:
                    return self.status() if self.status()['ok'] else self.call('restart_policy', {})
                proc = self.module._POLICY_PROC
                if proc is None or proc.poll() is not None:
                    self.module.start_policy_server()
                return self.status()
            if method not in self.ROUTES or (method == 'restart_docker' and self.robot != 'franka'):
                raise ValueError('Unsupported station maintenance action')
            if self.external:
                result = self.http_request(self.ROUTES[method], post=True)
            else:
                with self.module.app.test_client() as client:
                    response = client.post(self.ROUTES[method], json={})
                    result = response.get_json()
                    if response.status_code >= 400:
                        raise RuntimeError((result or {}).get('error', 'Legacy maintenance failed'))
            self.last = result
            return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True)
    p.add_argument('--robot', required=True)
    p.add_argument('--url', default='http://127.0.0.1:8080')
    p.add_argument('--policy-url', required=True)
    a = p.parse_args()
    host = LegacyHost(a.root, a.robot, a.url, a.policy_url)
    serve(host.call)
