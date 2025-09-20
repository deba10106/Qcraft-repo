import unittest
import os
import json
import tempfile
from circuit_designer.workflow_bridge import QuantumWorkflowBridge
from circuit_designer.circuit_editor import CircuitEditor
from scode.api import SurfaceCodeAPI
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
import mock
from logging_results import LoggingResultsManager

class TestWorkflowBridge(unittest.TestCase):
    def setUp(self):
        self.config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../configs'))
        self.bridge = QuantumWorkflowBridge(self.config_dir)
        # Load device and provider from hardware.json
        hardware_json_path = os.path.join(self.config_dir, 'hardware.json')
        hw = self.load_hardware_json(hardware_json_path)
        self.provider = hw['provider_name']
        self.device = hw['device_name']
        self.layout_type = 'planar'  # Default layout type
        self.code_distance = 3  # Default code distance
        
        # Mock device info for testing
        self.mock_device_info = {
            'max_qubits': 25,
            'topology_type': 'grid',
            'qubit_connectivity': {str(i): [str(i+1)] for i in range(24)},
            'native_gates': ['X', 'Z', 'CNOT', 'H'],
            'gate_error_rates': {'X': 0.001, 'Z': 0.001, 'CNOT': 0.01, 'H': 0.001},
            'qubit_properties': {
                str(i): {'readout_error': 0.01, 'T1': 50, 'T2': 70} for i in range(25)
            }
        }
        self.logger = LoggingResultsManager()

    def load_hardware_json(self, hardware_json_path):
        try:
            with open(hardware_json_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Fallback to a default configuration for testing
            return {'provider_name': 'simulator', 'device_name': 'default'}

    def test_initialization(self):
        self.logger.log_event('test_started', {'test': 'test_initialization'}, level='INFO')
        self.assertIsNotNone(self.bridge.orchestrator)
        self.assertIsNotNone(self.bridge.optimizer)
        self.assertIsNotNone(self.bridge.surface_code_api)
        self.assertIsNotNone(self.bridge.code_switcher)
        self.assertIsNotNone(self.bridge.executor)
        self.assertIsNotNone(self.bridge.logger)
        self.assertIsNotNone(self.bridge.ft_builder)
        self.logger.log_event('test_completed', {'test': 'test_initialization'}, level='INFO')

    @mock.patch('hardware_abstraction.device_abstraction.DeviceAbstraction.get_device_info')
    def test_device_info(self, mock_get_device_info):
        self.logger.log_event('test_started', {'test': 'test_device_info'}, level='INFO')
        mock_get_device_info.return_value = self.mock_device_info
        device_info = self.bridge.get_device_info(self.provider, self.device)
        self.assertIsInstance(device_info, dict)
        self.assertIn('max_qubits', device_info)
        self.logger.log_event('test_completed', {'test': 'test_device_info'}, level='INFO')

    def test_config_management(self):
        self.logger.log_event('test_started', {'test': 'test_config_management'}, level='INFO')
        config = self.bridge.get_config('surface_code')
        self.assertIsInstance(config, dict)
        configs = self.bridge.list_configs()
        self.assertIsInstance(configs, list)
        schema = self.bridge.get_schema('surface_code')
        self.assertIsInstance(schema, dict)
        self.logger.log_event('test_completed', {'test': 'test_config_management'}, level='INFO')

    @mock.patch('orchestration_controller.orchestrator.OrchestratorController.generate_surface_code_layout')
    def test_surface_code_generation(self, mock_generate_layout):
        """Test surface code layout generation."""
        # Setup mock
        mock_layout = {
            'qubit_layout': {
                'data_qubits': {str(i): {'x': i, 'y': i} for i in range(5)},
                'ancilla_qubits': {str(i+5): {'x': i, 'y': i+1, 'type': 'X'} for i in range(5)}
            },
            'stabilizer_map': {'X': {}, 'Z': {}}
        }
        mock_generate_layout.return_value = mock_layout
        
        # Call method
        layout = self.bridge.generate_surface_code_layout(
            self.layout_type, 
            self.code_distance, 
            self.device, 
            config_overrides=None
        )
        
        # Assert
        self.assertIsInstance(layout, dict)
        self.assertIn('qubit_layout', layout)
        self.assertIn('stabilizer_map', layout)

    def test_identify_switching_points(self):
        """Test identification of switching points in a circuit."""
        # Create a sample circuit with gates that would need switching
        circuit = {
            'qubits': [0, 1],
            'gates': [
                {'id': 'g0_SWAP_0_1_0', 'name': 'SWAP', 'qubits': [0, 1], 'time': 0, 'params': []}
            ]
        }
        
        # Define code info with supported gates that don't include SWAP
        code_info = {'supported_gates': ['X', 'Z', 'CNOT', 'H']}
        
        # Identify switching points
        switching_points = self.bridge.identify_switching_points(circuit, code_info)
        self.assertIsInstance(switching_points, list)
        self.assertGreater(len(switching_points), 0)
        
        # Verify that SWAP gate is identified as a switching point
        found_swap = False
        for point in switching_points:
            if point['gate'] == 'SWAP':
                found_swap = True
                break
        self.assertTrue(found_swap, "SWAP gate should be identified as a switching point")

    def test_select_switching_protocol(self):
        """Test selection of switching protocol for a gate."""
        # Test with SWAP gate
        protocol = self.bridge.select_switching_protocol(
            'SWAP', 
            ["magic_state_injection", "lattice_surgery"]
        )
        self.assertEqual(protocol, 'teleportation', "Teleportation should be selected for SWAP")
        
        # Test with T gate
        protocol = self.bridge.select_switching_protocol(
            'T', 
            ["magic_state_injection", "lattice_surgery"]
        )
        self.assertIn(protocol, ["magic_state_injection", "lattice_surgery"])

    def test_logging_functionality(self):
        self.logger.log_event('test_started', {'test': 'test_logging_functionality'}, level='INFO')
        self.bridge.log_event("test_event", {"test": "data"}, "INFO")
        self.bridge.log_metric("test_metric", 0.95, 1, "test_run")
        result = {"test_result": "success"}
        self.bridge.store_result("test_run", result)
        retrieved = self.bridge.get_result("test_run")
        self.assertEqual(retrieved, result)
        self.logger.log_event('test_completed', {'test': 'test_logging_functionality'}, level='INFO')

    def test_api_key_management(self):
        """Test API key management."""
        # Set API key
        self.bridge.set_api_key("test_provider", "test_key_12345")
        
        # Get API key
        key = self.bridge.get_api_key("test_provider")
        self.assertEqual(key, "test_key_12345")
        
        # Get current provider key
        current_key = self.bridge.get_current_provider_api_key()
        self.assertIsNotNone(current_key)

    @mock.patch('orchestration_controller.orchestrator.OrchestratorController.optimize_circuit')
    def test_circuit_optimization(self, mock_optimize):
        """Test circuit optimization functionality."""
        # Create a simple circuit
        editor = CircuitEditor()
        q0 = editor.add_qubit()
        q1 = editor.add_qubit()
        editor.add_gate('H', q0, 0)
        # Fixed: Using the correct signature
        editor.add_gate('CNOT', q0, 1)
        
        # Setup mock
        mock_optimize.return_value = {
            'circuit': editor.circuit,
            'metrics': {'depth': 2, 'gate_count': 2}
        }
        
        # Call method
        optimized = self.bridge.optimize_circuit(
            editor.circuit,
            self.mock_device_info,
            config_overrides=None
        )
        
        # Assert
        self.assertIsInstance(optimized, dict)
        self.assertIn('circuit', optimized)

    @mock.patch('orchestration_controller.orchestrator.OrchestratorController.assemble_fault_tolerant_circuit')
    @mock.patch('fault_tolerant_circuit_builder.ft_circuit_builder.FaultTolerantCircuitBuilder.validate_fault_tolerant_circuit')
    def test_fault_tolerant_circuit(self, mock_validate, mock_assemble):
        """Test fault-tolerant circuit functionality."""
        # Create a simple logical circuit
        logical_circuit = {
            'qubits': [0, 1],
            'gates': [
                {'id': 'g0_H_0_0', 'name': 'H', 'qubits': [0], 'time': 0, 'params': []},
                {'id': 'g1_CNOT_0_1_1', 'name': 'CNOT', 'qubits': [0, 1], 'time': 1, 'params': []}
            ]
        }
        
        # Setup mock layout
        mock_layout = {
            'qubit_layout': {
                'data_qubits': {str(i): {'x': i, 'y': i} for i in range(5)},
                'ancilla_qubits': {str(i+5): {'x': i, 'y': i+1, 'type': 'X'} for i in range(5)}
            },
            'stabilizer_map': {'X': {}, 'Z': {}}
        }
        
        # Create mapping info
        mapping_info = {
            'logical_to_physical': {0: 0, 1: 1},
            'multi_patch_layout': mock_layout
        }
        
        # Create code spaces
        code_spaces = [mock_layout]
        
        # Setup mocks
        mock_ft_circuit = {
            'qubits': list(range(10)),
            'gates': [
                {'id': 'g0', 'name': 'H', 'qubits': [0], 'time': 0},
                {'id': 'g1', 'name': 'CNOT', 'qubits': [0, 1], 'time': 1}
            ]
        }
        mock_assemble.return_value = mock_ft_circuit
        mock_validate.return_value = True
        
        # Call methods
        ft_circuit = self.bridge.assemble_fault_tolerant_circuit(
            logical_circuit,
            mapping_info,
            code_spaces,
            self.mock_device_info
        )
        
        # Validate fault-tolerant circuit
        valid = self.bridge.validate_fault_tolerant_circuit(
            ft_circuit,
            self.mock_device_info
        )
        
        # Assert
        self.assertIsInstance(ft_circuit, dict)
        self.assertTrue(valid)

    @mock.patch('orchestration_controller.orchestrator.OrchestratorController.run_workflow')
    def test_run_full_workflow(self, mock_run_workflow):
        """Test the full workflow integration."""
        # Create a simple circuit
        editor = CircuitEditor()
        q0 = editor.add_qubit()
        q1 = editor.add_qubit()
        editor.add_gate('H', q0, 0)
        # Fixed: Using the correct signature
        editor.add_gate('CNOT', q0, 1)
        
        # Setup progress callback
        progress_log = []
        def progress_callback(step, progress, message):
            progress_log.append((step, progress, message))
        
        # Setup mock
        mock_result = {
            'workflow_id': 'test-1234',
            'status': 'completed',
            'steps': [
                {'name': 'optimize', 'status': 'completed'},
                {'name': 'map', 'status': 'completed'},
                {'name': 'assemble', 'status': 'completed'}
            ],
            'result': {
                'circuit': editor.circuit,
                'metrics': {'depth': 2, 'gate_count': 2}
            }
        }
        mock_run_workflow.return_value = mock_result
        
        # Call method
        result = self.bridge.run_full_workflow(
            editor.circuit,
            user_config={
                'code_distance': self.code_distance,
                'layout_type': self.layout_type,
                'device': self.device,
                'provider': self.provider
            },
            progress_callback=progress_callback
        )
        
        # Assert
        self.assertIsInstance(result, dict)
        self.assertEqual(result['status'], 'completed')

if __name__ == '__main__':
    unittest.main() 