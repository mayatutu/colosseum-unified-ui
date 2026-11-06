"""Station paths/configuration. This module never imports a robot driver."""
from dataclasses import dataclass
from pathlib import Path
import os
import yaml


@dataclass
class Station:
    path: Path
    data: dict

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        if data.get('robot') not in ('franka', 'yam'):
            raise ValueError('station.robot must be franka or yam')
        for key in ('client_root', 'client_python', 'robot_config', 'database'):
            if not data.get(key):
                raise ValueError('Missing station field: ' + key)
        return cls(path, data)

    def file(self, key):
        p = Path(self.data[key]).expanduser()
        if key == 'client_python':
            # Resolving a venv executable symlink bypasses its pyvenv.cfg.
            return Path(os.path.abspath(p if p.is_absolute() else self.path.parent / p))
        return p.resolve() if p.is_absolute() else (self.path.parent / p).resolve()

    @property
    def robot(self):
        return self.data['robot']

    def worker_command(self):
        return [str(self.file('client_python')), '-u', str(Path(__file__).with_name('worker.py')),
                '--station', str(self.path)]

    def evaluator_options(self):
        names = list(self.data.get('people', []))
        root = self.data.get('maintenance', {}).get('root')
        if root:
            path = Path(root) / 'config.yaml'
            if path.exists():
                config = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
                names += [row.get('name', '') if isinstance(row, dict) else row
                          for row in config.get('evaluators', [])]
        return list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))

    def load_client_config(self):
        from dataclasses import fields, replace
        import json
        from colosseum_client.robot_config import RobotClientConfig
        config = RobotClientConfig.from_yaml(self.file('robot_config'))
        settings = self.file('database').with_name('llm-settings.json')
        overrides = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {}
        names = {f.name for f in fields(config)}
        if 'llm_api_keys' in names:
            config = replace(config, llm_api_keys={**config.llm_api_keys, **overrides.get('llm_api_keys', {})})
        elif 'llm_providers' in names and 'llm_providers' in overrides:
            config = replace(config, llm_providers=tuple(overrides['llm_providers']))
        return config
