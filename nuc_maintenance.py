"""Explicit NUC Docker restart through the existing local maintenance endpoint."""
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


class NucDockerHost:
    def __init__(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ('', '/')):
            raise ValueError('NUC maintenance requires the existing loopback HTTP service')
        self.url = url.rstrip('/')
        self.http = build_opener(ProxyHandler({}))

    def restart(self):
        request = Request(self.url + '/api/restart_docker', data=b'{}',
                          headers={'Content-Type': 'application/json'})
        # One explicit request, never retry an uncertain hardware operation.
        with self.http.open(request, timeout=120) as response:
            value = json.load(response)
        if not isinstance(value, dict) or type(value.get('ok')) is not bool:
            raise RuntimeError('Invalid NUC maintenance response; check status before retrying')
        return value
