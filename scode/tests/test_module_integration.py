import unittest
from unittest import mock
import os
import json
from typing import Dict, Any, Optional

from circuit_designer.workflow_bridge import QuantumWorkflowBridge
from orchestration_controller.orchestrator import OrchestratorController
from scode.api import SurfaceCodeAPI
from scode.rl_agent.environment import SurfaceCodeEnvironment
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from logging_results.logging_results_manager import LoggingResultsManager

class TestModuleIntegration(unittest.TestCase):
    def setUp(self):
        """Set up test environment with mock device and config."""
        self.logger = LoggingResultsManager()
        self.logger.log_event('test_started', {'test': 'module_integration'}, level='INFO')
        
        # Load configs
        ConfigManager.load_registry()
        self.base_config = ConfigManager.get_config('multi_patch_rl_agent')
        self.device_config = {
            'provider_name': 'test_provider',
            'device_name': 'test_device',
            'max_qubits': 20,
            'qubit_connectivity': {str(i): [str(j) for j in range(20) if j != i] for i in range(20)},
            'qubit_properties': {str(i): {'readout_error': 0.001} for i in range(20)},
            'native_gates': ['H', 'CNOT', 'X', 'Z'],
            'gate_error_rates': {'H': 0.001, 'CNOT': 0.002, 'X': 0.001, 'Z': 0.001}
        }
        
        # Initialize components
        self.bridge = QuantumWorkflowBridge()
        self.orchestrator = OrchestratorController()
        self.surface_code_api = SurfaceCodeAPI()
        
        # Test parameters
        self.code_distance = 3
        self.layout_type = 'planar'
        self.test_circuit = {
            'qubits': [0, 1],
            'gates': [
                {'id': 'g0', 'name': 'H', 'qubits': [0], 'time': 0},
                {'id': 'g1', 'name': 'CNOT', 'qubits': [0, 1], 'time': 1}
            ]
        }

    def test_workflow_bridge_to_orchestrator(self):
        """Test interaction between workflow bridge and orchestrator."""
        self.logger.log_event('test_case', {'test': 'workflow_bridge_to_orchestrator'}, level='INFO')
        
        # Test surface code generation flow
        layout = self.bridge.generate_surface_code_layout(
            self.layout_type,
            self.code_distance,
            'test_device'
        )
        self.assertIsInstance(layout, dict)
        self.assertIn('qubit_layout', layout)
        
        # Test mapping flow
        mapping = self.bridge.map_circuit_to_surface_code(
            self.test_circuit,
            'test_device',
            self.layout_type,
            self.code_distance
        )
        self.assertIsInstance(mapping, dict)
        self.assertIn('mapping_info', mapping)

    def test_orchestrator_to_surface_code(self):
        """Test interaction between orchestrator and surface code API."""
        self.logger.log_event('test_case', {'test': 'orchestrator_to_surface_code'}, level='INFO')
        
        # Test surface code initialization
        code, mapping = self.orchestrator.initialize_code(
            self.code_distance,
            self.layout_type,
            {'num_patches': 1, 'patch_shapes': ['rectangular']}
        )
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        
        # Test multi-patch mapping
        mapping_info = self.orchestrator.map_circuit_to_surface_code(
            self.test_circuit,
            'test_device',
            self.layout_type,
            self.code_distance
        )
        self.assertIsInstance(mapping_info, dict)
        self.assertIn('device', mapping_info)
        self.assertIn('layout_type', mapping_info)

    def test_surface_code_environment_integration(self):
        """Test surface code environment integration with the full pipeline."""
        self.logger.log_event('test_case', {'test': 'surface_code_environment_integration'}, level='INFO')
        
        # Generate a surface code layout
        layout = self.surface_code_api.generate_surface_code_layout(
            layout_type=self.layout_type,
            code_distance=self.code_distance,
            device='test_device'
        )
        
        # Create environment
        env = SurfaceCodeEnvironment(
            config=self.base_config,
            hardware_graph=self.device_config
        )
        
        # Test environment reset
        obs = env.reset()
        self.assertIsInstance(obs, dict)
        self.assertIn('node_features', obs)
        self.assertIn('adjacency', obs)
        self.assertIn('action_mask', obs)
        
        # Test environment step
        action = env.action_space.sample()
        obs, reward, done, truncated, info = env.step(action)
        self.assertIsInstance(obs, dict)
        self.assertIsInstance(reward, float)
        self.assertIsInstance(done, bool)
        self.assertIsInstance(info, dict)

    def test_error_handling_and_recovery(self):
        """Test error handling and recovery across module boundaries."""
        self.logger.log_event('test_case', {'test': 'error_handling_and_recovery'}, level='INFO')
        
        # Test invalid code distance handling
        with self.assertRaises(Exception):
            self.bridge.generate_surface_code_layout(
                self.layout_type,
                -1,  # Invalid code distance
                'test_device'
            )
        
        # Test invalid device handling
        result = self.bridge.map_circuit_to_surface_code(
            self.test_circuit,
            'nonexistent_device',  # Invalid device
            self.layout_type,
            self.code_distance
        )
        self.assertEqual(result.get('status'), 'failed')
        
        # Test recovery from mapping failure
        result = self.bridge.map_circuit_to_surface_code(
            self.test_circuit,
            'test_device',
            self.layout_type,
            self.code_distance,
            mapping_constraints={'num_patches': 1}  # Valid constraints
        )
        self.assertNotEqual(result.get('status'), 'failed')

    def test_configuration_propagation(self):
        """Test configuration changes propagate correctly through modules."""
        self.logger.log_event('test_case', {'test': 'configuration_propagation'}, level='INFO')
        
        # Update config through bridge
        test_config = {'surface_code': {'code_distance': 5}}
        self.bridge.update_config('surface_code', test_config)
        
        # Verify config propagated to surface code API
        layout = self.surface_code_api.generate_surface_code_layout(
            layout_type=self.layout_type,
            device='test_device'
        )
        self.assertIsInstance(layout, dict)
        
        # Verify config affects environment creation
        env = SurfaceCodeEnvironment(
            config=ConfigManager.get_config('surface_code'),
            hardware_graph=self.device_config
        )
        self.assertIsNotNone(env)

    def tearDown(self):
        """Clean up after tests."""
        self.logger.log_event('test_completed', {'test': 'module_integration'}, level='INFO')

if __name__ == '__main__':
    unittest.main() 