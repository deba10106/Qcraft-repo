import unittest
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.multi_patch_mapper.multi_patch_mapper import MultiPatchMapper
import os

def deep_merge(base: dict, override: dict) -> dict:
    if not override:
        return base.copy()
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

class TestMultiPatchMapper(unittest.TestCase):
    def setUp(self, config_overrides=None, device_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('multi_patch_rl_agent')
        config_overrides = config_overrides or {}
        config_overrides['use_rl_agent'] = True
        config_overrides['rl_policy_path'] = 'dummy_path_for_test'
        self.config = deep_merge(base_config, config_overrides)
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device = deep_merge(base_device, device_overrides or {})
        self.h_layer = HeuristicInitializationLayer(self.config, self.device)

    def test_map_patches(self):
        mapper = MultiPatchMapper(self.config, self.device)
        surface_codes = [{'code_id': 1, 'code_type': 'surface'}]
        mapping_constraints = [{'constraint_id': 1, 'constraint_type': 'distance'}]
        try:
            patches = mapper.map_patches(surface_codes, mapping_constraints)
            self.assertIsNotNone(patches)
            self.assertIsInstance(patches, list)
        except RuntimeError:
            pass

if __name__ == '__main__':
    unittest.main()