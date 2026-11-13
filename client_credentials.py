"""Client-owned API key settings validated by the pinned official Client."""
from dataclasses import replace
import json
import os
import tempfile
from pathlib import Path

from colosseum_client.llm_credentials import API_URLS


def save_client_keys(station, body):
    if not isinstance(body, dict) or set(body) - API_URLS.keys():
        raise ValueError('Expected API keys for openai, xai, or anthropic')
    if any(not isinstance(value, str) for value in body.values()):
        raise ValueError('API keys must be strings')
    config = station.load_client_config()
    path = station.file('database').with_name('llm-settings.json')
    document = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    keys = dict(document.get('llm_api_keys', {}))
    keys.update({provider: key.strip() for provider, key in body.items() if key.strip()})
    # Validate the actual resulting config before persisting anything. This
    # invokes official provider resolution, auth conflicts and secure URL rules.
    replace(config, llm_api_keys={**config.llm_api_keys, **keys})
    document.pop('llm_providers', None)
    document['llm_api_keys'] = keys
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='llm-settings-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(document, output, ensure_ascii=False, indent=2)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
