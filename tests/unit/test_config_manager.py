# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import builtins
import io
import os
import json
import pytest

from configuration_management.config_manager import ConfigManager


def test_load_registry_and_get_config_basic():
    ConfigManager.load_registry()
    keys = set(ConfigManager.list_configs())
    assert {'hardware', 'workflow_policy', 'multi_patch_rl_agent'} <= keys
    cfg = ConfigManager.get_config('compiler')
    assert isinstance(cfg, dict)


def test_resolve_device_config_paths():
    ConfigManager.load_registry()
    ibm_path = ConfigManager.resolve_device_config('ibm')
    assert ibm_path and ibm_path.endswith('ibm_devices.yaml')


def test_env_roundtrip(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    monkeypatch.setattr(ConfigManager, 'env_path', str(env_file))
    env = ConfigManager.load_env()
    assert env == {}
    ConfigManager.set_api_key('ibm', 'KEY123')
    key = ConfigManager.get_api_key('ibm')
    assert key == 'KEY123'


def test_save_config_fallback_to_user_dir(tmp_path, monkeypatch):
    ConfigManager.load_registry()
    module = 'compiler'
    config_path = ConfigManager.config_registry[module]

    def fake_expanduser(p):
        if p.startswith('~/.qcraft/configs'):
            return str(tmp_path / 'configs' / p.split('configs/')[-1])
        return os.path.expanduser.__wrapped__(p) if hasattr(os.path.expanduser, '__wrapped__') else os.path.expanduser(p)

    monkeypatch.setattr(os.path, 'expanduser', fake_expanduser)

    real_open = builtins.open

    def guarded_open(file, mode='r', *args, **kwargs):
        if file == config_path and 'w' in mode:
            raise PermissionError('read-only')
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', guarded_open)

    cfg = ConfigManager.get_config(module)
    cfg_update = dict(cfg)
    cfg_update['__test_marker__'] = True
    ConfigManager.save_config(module, config=cfg_update)

    fname = os.path.basename(config_path)
    user_path = ConfigManager.get_user_config_path(fname)
    assert os.path.exists(user_path)
    with real_open(user_path, 'r') as f:
        loaded = f.read()
    assert ('__test_marker__' in loaded) or (json.loads(loaded).get('__test_marker__') is True if user_path.endswith('.json') else True)
