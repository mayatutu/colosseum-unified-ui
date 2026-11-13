from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from colosseum_client.robot_config import RobotClientConfig
from colosseum_client.llm_credentials import local_preparation
from client_credentials import save_client_keys


def station(tmp_path, policy_url='ws://127.0.0.1:18001'):
    config = RobotClientConfig(url='https://router.example.invalid', token='', cameras={},
                               policy_server_url=policy_url)
    return SimpleNamespace(file=lambda key: tmp_path / 'station.db', load_client_config=lambda: config)


def test_save_keys_preserves_blank_and_removes_legacy_provider_selection(tmp_path):
    target = tmp_path / 'llm-settings.json'
    target.write_text(json.dumps({'llm_providers': ['xai'], 'llm_api_keys': {'openai': 'fake-old'}}))
    selected = station(tmp_path)
    save_client_keys(selected, {'openai': '', 'anthropic': ' fake-new '})
    data = json.loads(target.read_text())
    assert data == {'llm_api_keys': {'openai': 'fake-old', 'anthropic': 'fake-new'}}
    config = replace(selected.load_client_config(), llm_api_keys=data['llm_api_keys'])
    prepared = local_preparation({'model': {'model_type': 'llm', 'name': 'gpt-test'}},
                                config.llm_api_keys, config.policy_server_url)
    assert prepared['api_key'] == 'fake-old'
    assert 'anthropic' not in prepared


def test_plaintext_remote_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError, match='SSH tunnel'):
        save_client_keys(station(tmp_path, 'ws://policy.example.invalid:18001'), {'openai': 'fake'})
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('body', [{'llm_providers': ['openai']}, {'openai': 123}, {'other': 'fake'}])
def test_invalid_input_never_writes(tmp_path, body):
    with pytest.raises(ValueError):
        save_client_keys(station(tmp_path), body)
    assert not list(tmp_path.iterdir())


def test_no_policy_secret_fallback(tmp_path):
    with pytest.raises(ValueError, match='no matching Client API key'):
        local_preparation({'model': {'model_type': 'llm', 'name': 'gpt-test'}}, {},
                          station(tmp_path).load_client_config().policy_server_url)
