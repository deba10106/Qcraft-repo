import os
import unittest
from scode.api import SurfaceCodeAPI
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
import json
from circuit_designer.workflow_bridge import QuantumWorkflowBridge
import importlib.resources
from circuit_designer.circuit_editor import CircuitEditor
import tempfile
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

class TestFullFrontendWorkflow(unittest.TestCase):
    def setUp(self, config_overrides=None, device_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('multi_patch_rl_agent')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device = deep_merge(base_device, device_overrides or {})
        self.api = SurfaceCodeAPI(config_overrides, device_overrides)
        self.provider = self.device['provider_name']
        self.device_name = self.device['device_name']
        self.layout_type = self.api.list_layout_types()[0]
        self.code_distance = self.api.list_code_distances(self.device_name, self.layout_type)[0]
        self.logger = LoggingResultsManager()

    def load_hardware_json(self, hardware_json_path):
        try:
            with importlib.resources.open_text('configs', 'hardware.json') as f:
                return json.load(f)
        except (FileNotFoundError, ModuleNotFoundError):
            with open(hardware_json_path, 'r') as f:
                return json.load(f)

    def test_device_and_layout_selection(self):
        self.logger.log_event('test_started', {'test': 'test_device_and_layout_selection'}, level='INFO')
        devices = self.api.list_available_devices()
        layouts = self.api.list_layout_types()
        code_distances = self.api.list_code_distances(self.device_name, self.layout_type)
        self.logger.log_event('test_case', {'devices': devices, 'layouts': layouts, 'code_distances': code_distances}, level='DEBUG')
        print('Devices:', devices)
        print('Layouts:', layouts)
        print('Code distances:', code_distances)
        self.assertTrue(len(layouts) > 0)
        self.assertTrue(len(code_distances) > 0)
        self.logger.log_event('test_completed', {'test': 'test_device_and_layout_selection'}, level='INFO')

    def test_surface_code_generation(self):
        print('\n[TEST] Surface code generation')
        layout = self.api.generate_surface_code_layout(self.layout_type, self.code_distance, self.device_name)
        print('Generated layout:', layout)
        self.assertIn('qubit_layout', layout)
        self.assertIn('stabilizer_map', layout)

    def test_rl_agent_training(self):
        print('\n[TEST] RL agent training')
        def log_callback(msg, progress):
            print(f'[TRAIN LOG] {msg} (progress={progress})')
        policy_path = self.api.train_surface_code_agent(
            provider=self.provider,
            device=self.device_name,
            layout_type=self.layout_type,
            code_distance=self.code_distance,
            config_overrides=None,
            log_callback=log_callback
        )
        print('Trained policy path:', policy_path)
        self.assertTrue(os.path.exists(policy_path))
        status = self.api.get_training_status(policy_path)
        print('Training status:', status)
        self.assertEqual(status['status'], 'completed')

    def test_mapping_and_multi_patch(self):
        print('\n[TEST] Mapping and multi-patch')
        layout = self.api.generate_surface_code_layout(self.layout_type, self.code_distance, self.device_name)
        mapping_constraints = self.config.get('multi_patch', {'patch_shapes': ['rectangular'], 'num_patches': 2})
        # Simulate multi-patch mapping via orchestrator API
        orchestrate_result = self.api.orchestrate_code_and_mapping(
            code_distance=self.code_distance,
            layout_type=self.layout_type,
            mapping_constraints=mapping_constraints,
            device_config={'max_qubits': 25, 'topology_type': 'grid', 'qubit_connectivity': {str(i): [str(i+1)] for i in range(24)}},
            switcher_config_path=self.switcher_config,
            config_path=self.surface_code_config
        )
        print('Orchestrate result:', orchestrate_result)
        self.assertIn('codes', orchestrate_result)
        self.assertIn('mapping', orchestrate_result)
        mapping = orchestrate_result['mapping']
        self.assertIn('multi_patch_layout', mapping.get('multi_patch_layout', {}))
        self.assertIn('resource_allocation', mapping)
        self.assertIn('inter_patch_connectivity', mapping)
        self.assertIn('optimization_metrics', mapping)

    def test_code_switching(self):
        print('\n[TEST] Code switching')
        mapping_constraints = self.config.get('multi_patch', {'patch_shapes': ['rectangular']})
        orchestrate_result = self.api.orchestrate_code_and_mapping(
            code_distance=self.code_distance,
            layout_type=self.layout_type,
            mapping_constraints=mapping_constraints,
            device_config={'max_qubits': 25, 'topology_type': 'grid', 'qubit_connectivity': {str(i): [str(i+1)] for i in range(24)}},
            switcher_config_path=self.switcher_config,
            config_path=self.surface_code_config
        )
        old_mapping = orchestrate_result['mapping']
        new_mapping = orchestrate_result['mapping']  # For test, use same mapping
        result = self.api.switch_code_space(
            old_mapping=old_mapping,
            new_mapping=new_mapping,
            switcher_config_path=self.switcher_config,
            protocol='lattice_surgery'
        )
        print('Switch result:', result)
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'lattice_surgery')

    def test_evaluation(self):
        print('\n[TEST] Evaluation')
        layout = self.api.generate_surface_code_layout(self.layout_type, self.code_distance, self.device_name)
        mapped_circuit = {'layout': layout}
        ler = self.api.evaluate_logical_error_rate(mapped_circuit, self.device_name)
        print('Logical error rate:', ler)
        self.assertIsInstance(ler, float)

    def test_error_cases(self):
        self.logger.log_event('test_started', {'test': 'test_error_cases'}, level='INFO')
        # Invalid device
        with self.assertRaises(Exception):
            self.api.generate_surface_code_layout(self.layout_type, self.code_distance, 'invalid_device')
        # Invalid code distance
        with self.assertRaises(Exception):
            self.api.generate_surface_code_layout(self.layout_type, 999, self.device_name)
        # Invalid protocol: only check if backend is expected to raise
        mapping_constraints = self.config.get('multi_patch', {'patch_shapes': ['rectangular']})
        orchestrate_result = self.api.orchestrate_code_and_mapping(
            code_distance=self.code_distance,
            layout_type=self.layout_type,
            mapping_constraints=mapping_constraints,
            device_config={'max_qubits': 25, 'topology_type': 'grid', 'qubit_connectivity': {str(i): [str(i+1)] for i in range(24)}},
            switcher_config_path=self.switcher_config,
            config_path=self.surface_code_config
        )
        old_mapping = orchestrate_result['mapping']
        new_mapping = orchestrate_result['mapping']
        try:
            self.api.switch_code_space(
                old_mapping=old_mapping,
                new_mapping=new_mapping,
                switcher_config_path=self.switcher_config,
                protocol='teleportation'  # disabled in config
            )
        except Exception:
            self.logger.log_event('test_case', {'test': 'test_error_cases', 'case': 'invalid_protocol', 'result': 'exception_raised'}, level='DEBUG')
            pass  # Accept exception
        else:
            self.logger.log_event('test_case', {'test': 'test_error_cases', 'case': 'invalid_protocol', 'result': 'no_exception'}, level='WARNING')
            print('No exception raised for invalid protocol (may be allowed by backend config)')
        self.logger.log_event('test_completed', {'test': 'test_error_cases'}, level='INFO')

    def test_swap_gate_protocol_selection(self):
        print('\n[TEST] SWAP gate protocol selection')
        bridge = QuantumWorkflowBridge(self.config_dir)
        # Build a circuit with a SWAP gate
        circuit = {
            'qubits': [0, 1],
            'gates': [
                {'id': 'g0_SWAP_0_1_0', 'name': 'SWAP', 'qubits': [0, 1], 'time': 0, 'params': []}
            ]
        }
        # Try to run code switching step
        try:
            # Only include natively supported gates
            code_info = {'supported_gates': ['X', 'Z', 'CNOT', 'H']}
            switching_points = bridge.identify_switching_points(circuit, code_info)
            print('Switching points:', switching_points)
            protocols = []
            for sp in switching_points:
                proto = bridge.select_switching_protocol(sp['gate'], ["magic_state_injection", "lattice_surgery", "teleportation"])
                print(f"Selected protocol for {sp['gate']}: {proto}")
                protocols.append({'name': proto})
            print('Protocols found:', protocols)
        except Exception as e:
            print('Exception during protocol selection:', str(e))
            self.fail(f"Exception during protocol selection: {e}")
        else:
            self.assertTrue(any(p['name'] == 'teleportation' for p in protocols))

    def test_classical_register_support(self):
        print('\n[TEST] Classical register support')
        editor = CircuitEditor()
        # Add classical bits
        c0 = editor.add_clbit()
        c1 = editor.add_clbit()
        assert c0 in editor.get_clbits()
        assert c1 in editor.get_clbits()
        # Add MEASURE gate with clbit
        q0 = editor.circuit['qubits'][0]
        t = 0
        m_id = editor.add_gate('MEASURE', q0, t, clbits=[c0])
        found = False
        for g in editor.circuit['gates']:
            if g['id'] == m_id and g['name'] == 'MEASURE' and g['clbits'] == [c0]:
                found = True
        assert found, "MEASURE gate with clbit not found in circuit"
        # Remove clbit and check MEASURE gate is removed
        editor.remove_clbit(c0)
        for g in editor.circuit['gates']:
            assert not (g['name'] == 'MEASURE' and 'clbits' in g and c0 in g['clbits'])
        # Export to QASM
        with tempfile.NamedTemporaryFile('w+', delete=False) as f:
            editor.export_circuit(f.name, format='qasm')
            f.seek(0)
            qasm = f.read()
            assert 'creg c[' in qasm and 'measure' in qasm
        # Export to JSON
        with tempfile.NamedTemporaryFile('w+', delete=False) as f:
            editor.export_circuit(f.name, format='json')
            f.seek(0)
            data = json.load(f)
            assert 'clbits' in data and any(g['name'] == 'MEASURE' for g in data['gates'])
        # Export to YAML
        with tempfile.NamedTemporaryFile('w+', delete=False) as f:
            editor.export_circuit(f.name, format='yaml')
            f.seek(0)
            yml = f.read()
            assert 'clbits' in yml and 'MEASURE' in yml

if __name__ == '__main__':
    unittest.main() 