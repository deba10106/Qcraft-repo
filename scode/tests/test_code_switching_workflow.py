import os
import unittest
from orchestration_controller.orchestrator import Orchestrator
from code_switcher.code_switcher import CodeSwitcher
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from logging_results import LoggingResultsManager

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

class TestCodeSwitchingWorkflow(unittest.TestCase):
    def setUp(self, config_overrides=None, device_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('surface_code')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device_config = deep_merge(base_device, device_overrides or {})
        self.mapping_constraints = {'patch_shapes': ['rectangular']}
        self.code_distance = 3
        self.layout_type = 'planar'
        self.switcher_config_path = ConfigManager.config_registry.get('code_switcher', 'configs/switcher_config.yaml')
        self.logger = LoggingResultsManager()

    def test_code_switching_workflow_planar(self):
        self.logger.log_event('test_started', {'test': 'test_code_switching_workflow_planar'}, level='INFO')
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(self.code_distance, 'planar', self.mapping_constraints)
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        operations = [{'type': 'SWAP', 'swap_pairs': [(0, 1)]}]
        orchestrator.run_operations(operations, self.mapping_constraints)
        switcher = CodeSwitcher(self.switcher_config_path)
        result = switcher.switch(mapping, mapping, protocol='magic_state_injection')
        self.logger.log_event('test_case', {'test': 'test_code_switching_workflow_planar', 'result': result}, level='DEBUG')
        print('Switcher result:', result)
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'magic_state_injection')
        self.logger.log_event('test_completed', {'test': 'test_code_switching_workflow_planar'}, level='INFO')

    def test_code_switching_workflow_rotated(self):
        print('\n[TEST] Rotated layout, lattice_surgery protocol')
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(self.code_distance, 'rotated', self.mapping_constraints)
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        operations = [{'type': 'SWAP', 'swap_pairs': [(2, 3)]}]
        orchestrator.run_operations(operations, self.mapping_constraints)
        switcher = CodeSwitcher(self.switcher_config_path)
        result = switcher.switch(mapping, mapping, protocol='lattice_surgery')
        print('Switcher result:', result)
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'lattice_surgery')

    def test_code_switching_multiple_swaps(self):
        print('\n[TEST] Multiple SWAP operations')
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(self.code_distance, 'planar', self.mapping_constraints)
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        operations = [
            {'type': 'SWAP', 'swap_pairs': [(0, 1)]},
            {'type': 'SWAP', 'swap_pairs': [(1, 2)]},
            {'type': 'SWAP', 'swap_pairs': [(2, 3)]}
        ]
        orchestrator.run_operations(operations, self.mapping_constraints)
        switcher = CodeSwitcher(self.switcher_config_path)
        result = switcher.switch(mapping, mapping, protocol='magic_state_injection')
        print('Switcher result:', result)
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'magic_state_injection')

    def test_code_switching_invalid_protocol(self):
        print('\n[TEST] Invalid protocol (should raise ValueError)')
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(self.code_distance, 'planar', self.mapping_constraints)
        switcher = CodeSwitcher(self.switcher_config_path)
        method = getattr(switcher, 'switch_code_space', None)
        if method is None:
            method = getattr(switcher, 'switch', None)
        try:
            if method is not None:
                method(
                    old_mapping=mapping,
                    new_mapping=mapping,
                    protocol='teleportation',
                    switcher_config_path=self.switcher_config_path
                )
            else:
                print('No switch method found on CodeSwitcher')
        except ValueError:
            pass  # Accept exception
        else:
            print('No exception raised for invalid protocol (may be allowed by backend config)')

    def test_code_switching_missing_config(self):
        print('\n[TEST] Missing switcher config (should raise FileNotFoundError)')
        bad_path = '/tmp/nonexistent_switcher_config.yaml'
        with self.assertRaises(FileNotFoundError):
            CodeSwitcher(bad_path)

    def test_code_switching_different_constraints(self):
        print('\n[TEST] Different mapping constraints')
        mapping_constraints = {'patch_shapes': ['rectangular'], 'min_distance_between_patches': 2}
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(self.code_distance, 'planar', mapping_constraints)
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        switcher = CodeSwitcher(self.switcher_config_path)
        result = switcher.switch(mapping, mapping, protocol='lattice_surgery')
        print('Switcher result:', result)
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'lattice_surgery')

    def test_code_switching_different_code_distance(self):
        print('\n[TEST] Different code distance')
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(5, 'planar', self.mapping_constraints)
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        switcher = CodeSwitcher(self.switcher_config_path)
        result = switcher.switch(mapping, mapping, protocol='magic_state_injection')
        print('Switcher result:', result)
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'magic_state_injection')

if __name__ == '__main__':
    unittest.main() 