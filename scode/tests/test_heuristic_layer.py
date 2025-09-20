import unittest
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
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

class TestHeuristicInitializationLayer(unittest.TestCase):
    def setUp(self, config_overrides=None, device_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('multi_patch_rl_agent')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device = deep_merge(base_device, device_overrides or {})
        self.h_layer = HeuristicInitializationLayer(self.config, self.device)

    def test_planar_nearest_neighbour(self):
        code = self.h_layer.generate_surface_code(3, 'planar')
        self.assertTrue(len(code.qubit_layout) > 0)
        self.assertTrue(len(code.stabilizer_map) > 0)
        self.assertTrue(len(code.logical_operators) > 0)

    def test_rotated_all_to_all(self):
        code = self.h_layer.generate_surface_code(3, 'rotated')
        self.assertTrue(len(code.qubit_layout) > 0)
        self.assertTrue(len(code.stabilizer_map) > 0)
        self.assertTrue(len(code.logical_operators) > 0)

if __name__ == '__main__':
    unittest.main() 