import os
import yaml
import json
import uuid
from typing import Dict, Any, List, Optional
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from circuit_optimization.api import CircuitOptimizationAPI
from scode.api import SurfaceCodeAPI
# from code_switcher.api import CodeSwitcherAPI  # Placeholder for real code switcher
# from execution_simulation.api import ExecutionSimulatorAPI  # Placeholder for real execution
from fault_tolerant_circuit_builder.ft_circuit_builder import FaultTolerantCircuitBuilder
from logging_results import LoggingResultsManager

# Utility for deep merging dicts (API > config)
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

class OrchestratorController:
    """
    Orchestration/Controller Module for managing the workflow of quantum circuit design, optimization, mapping, code switching, and execution.
    All configuration is YAML/JSON-driven and APIs are pure Python for frontend/backend integration.
    """
    def __init__(self, config_overrides: dict = None, device_overrides: dict = None, switcher_config_path: str = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('workflow_policy')
        self.config = deep_merge(base_config, config_overrides or {})
        self.current_policy = self.config.get('workflow_policy', self.config)
        # Track the workflow policy config path for reference (may not be writable)
        self.config_path = ConfigManager.config_registry.get('workflow_policy')
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device_config = deep_merge(base_device, device_overrides or {})
        self.switcher_config_path = switcher_config_path
        self.optimizer_api = CircuitOptimizationAPI()
        self.surface_code_api = SurfaceCodeAPI(config_overrides, device_overrides)
        # self.code_switcher_api = CodeSwitcherAPI()  # Uncomment when available
        # self.execution_api = ExecutionSimulatorAPI()  # Uncomment when available
        self.ft_builder = FaultTolerantCircuitBuilder()
        self.workflow_status = {}
        self.logger = LoggingResultsManager()

    def run_workflow(self, circuit: dict, user_config: Optional[dict] = None, progress_callback=None) -> dict:
        workflow_id = str(uuid.uuid4())
        self.workflow_status[workflow_id] = {'status': 'running', 'steps': []}
        self.logger.log_event('workflow_started', {'workflow_id': workflow_id, 'user_config': user_config}, level='INFO')
        try:
            if progress_callback:
                progress_callback("Loading device info...", 0.05)
            device_info = self.device_config
            self.workflow_status[workflow_id]['steps'].append('device_loaded')
            module_sequence = self.config.get('workflow_policy', {}).get('module_sequence', [
                'surface_code', 'mapper', 'ft_builder', 'optimizer', 'code_switcher', 'executor'])
            step_results = {'circuit': circuit, 'device_info': device_info}
            for idx, module in enumerate(module_sequence):
                if progress_callback:
                    progress_callback(f"Running module: {module}", 0.1 + 0.8 * idx / len(module_sequence))
                self.logger.log_event('module_started', {'workflow_id': workflow_id, 'module': module, 'step': idx}, level='INFO')
                if module == 'surface_code':
                    code_params = self.decide_surface_code(device_info, circuit, user_config)
                    layout = self.generate_surface_code_layout(
                        code_params['layout'], code_params['distance'], device_info.get('name') or device_info.get('device_name'),
                        user_config, progress_callback=progress_callback
                    )
                    step_results['surface_code'] = code_params
                    step_results['surface_code_layout'] = layout
                    self.workflow_status[workflow_id]['steps'].append({'surface_code': code_params})
                elif module == 'optimizer':
                    # Optimize the FT circuit if available, else fallback to logical
                    circuit_to_optimize = step_results.get('ft_circuit', step_results.get('optimized_circuit', step_results['circuit']))
                    optimized_circuit = self.optimize_circuit(circuit_to_optimize, device_info, user_config, progress_callback=progress_callback)
                    step_results['optimized_circuit'] = optimized_circuit
                    self.workflow_status[workflow_id]['steps'].append('circuit_optimized')
                elif module == 'mapper':
                    mapping_constraints = user_config.get('multi_patch', {'num_patches': 1, 'patch_shapes': ['rectangular']}) if user_config else {'num_patches': 1, 'patch_shapes': ['rectangular']}
                    mapping_info = self.map_circuit_to_surface_code(
                        step_results.get('optimized_circuit', step_results['circuit']),
                        device_info.get('name') or device_info.get('device_name'),
                        step_results['surface_code']['layout'],
                        step_results['surface_code']['distance'],
                        None, user_config, progress_callback=progress_callback, mapping_constraints=mapping_constraints
                    )
                    step_results['mapping_info'] = mapping_info
                    self.workflow_status[workflow_id]['steps'].append('circuit_mapped')
                elif module == 'ft_builder':
                    code_spaces = []
                    if 'mapping_info' in step_results and 'multi_patch_mapping' in step_results['mapping_info']:
                        mp = step_results['mapping_info']['multi_patch_mapping']
                        if 'multi_patch_layout' in mp:
                            code_spaces = [patch['layout'] for patch in mp['multi_patch_layout'].values()]
                    ft_circuit = self.assemble_fault_tolerant_circuit(
                        step_results.get('optimized_circuit', step_results['circuit']),
                        step_results['mapping_info'],
                        code_spaces,
                        device_info,
                        user_config,
                        progress_callback=progress_callback
                    )
                    step_results['ft_circuit'] = ft_circuit
                    self.workflow_status[workflow_id]['steps'].append('ft_circuit_built')
                elif module == 'code_switcher':
                    if self.config.get('workflow_policy', {}).get('enable_code_switching', True):
                        self.workflow_status[workflow_id]['steps'].append('code_switching_skipped')
                elif module == 'executor':
                    if self.config.get('workflow_policy', {}).get('enable_execution', False):
                        self.workflow_status[workflow_id]['steps'].append('execution_skipped')
                else:
                    self.workflow_status[workflow_id]['steps'].append(f'unknown_module_{module}')
                self.logger.log_event('module_completed', {'workflow_id': workflow_id, 'module': module, 'step': idx}, level='INFO')
            self.workflow_status[workflow_id]['status'] = 'completed'
            if progress_callback:
                progress_callback("Workflow completed.", 1.0)
            self.logger.log_event('workflow_completed', {'workflow_id': workflow_id, 'steps': self.workflow_status[workflow_id]['steps']}, level='INFO')
            self.logger.store_result(workflow_id, {'status': 'completed', **step_results})
            return {
                'workflow_id': workflow_id,
                **step_results,
                'status': 'completed',
                'steps': self.workflow_status[workflow_id]['steps']
            }
        except Exception as e:
            self.workflow_status[workflow_id]['status'] = 'failed'
            self.workflow_status[workflow_id]['error'] = str(e)
            if progress_callback:
                progress_callback(f"Error: {str(e)}", 1.0)
            self.logger.log_event('workflow_failed', {'workflow_id': workflow_id, 'error': str(e)}, level='ERROR')
            self.logger.store_result(workflow_id, {'status': 'failed', 'error': str(e)})
            return {'workflow_id': workflow_id, 'status': 'failed', 'error': str(e)}

    def optimize_circuit(self, circuit: dict, device_info: dict, config_overrides: Optional[dict] = None, progress_callback=None) -> dict:
        if progress_callback:
            progress_callback("Running advanced circuit optimization...", 0.35)
        return self.optimizer_api.optimize_circuit(circuit, device_info, config_overrides)

    def get_optimization_report(self, original_circuit: dict, optimized_circuit: dict) -> dict:
        return self.optimizer_api.get_optimization_report(original_circuit, optimized_circuit)

    def generate_surface_code_layout(self, layout_type: str, code_distance: int, device: str, config_overrides: Optional[dict] = None, progress_callback=None) -> dict:
        if progress_callback:
            progress_callback("Generating surface code layout...", 0.20)
        return self.surface_code_api.generate_surface_code_layout(layout_type, code_distance, device)

    def map_circuit_to_surface_code(self, circuit: dict, device: str, layout_type: str, code_distance: int, provider: str = None, config_overrides: Optional[dict] = None, progress_callback=None, mapping_constraints: Optional[dict] = None) -> dict:
        if progress_callback:
            progress_callback("Mapping circuit to surface code...", 0.40)
        from scode.heuristic_layer.surface_code import SurfaceCode
        config = self.surface_code_api.config
        if config_overrides:
            config = deep_merge(config, config_overrides)
        device_info = self.device_config
        surface_code = SurfaceCode(config_overrides, device_info)
        if mapping_constraints is None:
            mapping_constraints = config.get('multi_patch', {'num_patches': 1, 'patch_shapes': ['rectangular']})
        mapping = surface_code.get_multi_patch_mapping(code_distance, layout_type, mapping_constraints)
        logical_to_physical = mapping.get('logical_to_physical', {})
        if not logical_to_physical:
            print("[WARNING] Orchestrator: Empty logical_to_physical mapping received")
        multi_patch_layout = mapping.get('multi_patch_layout', {})
        if multi_patch_layout:
            patch_count = len(multi_patch_layout)
            qubit_types = set()
            max_qubits = 0
            for patch_idx, patch_info in multi_patch_layout.items():
                patch_layout = patch_info.get('layout', {})
                max_qubits += len(patch_layout)
                for q, info in patch_layout.items():
                    if isinstance(info, dict) and 'type' in info:
                        qubit_types.add(info['type'])
            print(f"[DEBUG] Orchestrator: multi_patch_layout has {patch_count} patches with {max_qubits} qubits")
            print(f"[DEBUG] Orchestrator: Qubit types found: {qubit_types}")
        else:
            print("[WARNING] Orchestrator: Empty multi_patch_layout received")
        mapping_info = {
            'device': device,
            'layout_type': layout_type,
            'code_distance': code_distance,
            'provider': provider,
            'mapping_status': 'success',
            'multi_patch_mapping': mapping,
            'logical_to_physical': logical_to_physical
        }
        return mapping_info

    def assemble_fault_tolerant_circuit(self, logical_circuit: dict, mapping_info: dict, code_spaces: List[dict], device_info: dict, config_overrides: Optional[dict] = None, progress_callback=None) -> dict:
        if progress_callback:
            progress_callback("Assembling fault-tolerant circuit...", 0.60)
        try:
            return self.ft_builder.assemble_fault_tolerant_circuit(logical_circuit, mapping_info, code_spaces, device_info)
        except ValueError as e:
            # Catch code distance/physical qubit constraint errors and return a user-friendly error
            error_msg = f"[FT Workflow Error] {str(e)}"
            print(error_msg)
            if progress_callback:
                progress_callback(error_msg, 1.0)
            return {'status': 'failed', 'error': error_msg}

    def decide_surface_code(self, device_info: dict, circuit: dict, user_prefs: Optional[dict] = None) -> dict:
        """
        Decide which surface code (layout, distance) to use for the given device and circuit.
        Uses policy, device, and circuit info.
        """
        policy = self.current_policy.get('code_selection', {})
        allowed_layouts = policy.get('allowed_layouts', ['planar', 'rotated'])
        prefer_low_error = policy.get('prefer_low_error', True)
        prefer_short_depth = policy.get('prefer_short_depth', False)
        # Example: choose layout and distance based on device and circuit size
        layout = allowed_layouts[0] if allowed_layouts else 'planar'
        # Heuristic: code distance = min(5, device qubit count // 10)
        max_qubits = device_info.get('max_qubits', 5)
        distance = min(5, max(3, max_qubits // 10))
        if user_prefs:
            if 'layout' in user_prefs:
                layout = user_prefs['layout']
            if 'distance' in user_prefs:
                distance = user_prefs['distance']
        return {'layout': layout, 'distance': distance}

    def decide_code_switching(self, circuit: dict, code_info: dict, device_info: dict) -> List[dict]:
        """
        Decide if/where code switching is required and which protocols to use.
        Uses policy, code info, and device constraints.
        """
        policy = self.current_policy.get('code_switching', {})
        enable = policy.get('enable', True)
        preferred_protocols = policy.get('preferred_protocols', ['magic_state_injection', 'lattice_surgery'])
        if not enable:
            return []
        # Example: find all gates in circuit not supported by current code, and assign protocol
        unsupported_gates = []
        supported_gates = code_info.get('supported_gates', ['X', 'Z', 'CNOT'])
        for gate in circuit.get('gates', []):
            if gate['name'] not in supported_gates:
                unsupported_gates.append({'gate': gate['name'], 'location': gate.get('location', None), 'protocol': preferred_protocols[0]})
        return unsupported_gates

    def coordinate_modules(self, modules: List[str], data: dict) -> dict:
        """
        Coordinate the execution of a sequence of modules, passing data between them as needed.
        """
        result = data
        for module in modules:
            if module == 'optimizer':
                hardware_json_path = ConfigManager.config_registry.get('hardware', 'configs/hardware.json')
                device_info = DeviceAbstraction.load_selected_device(hardware_json_path)
                result = self.optimizer_api.optimize_circuit(result, device_info)
            elif module == 'surface_code':
                hardware_json_path = ConfigManager.config_registry.get('hardware', 'configs/hardware.json')
                device_info = DeviceAbstraction.load_selected_device(hardware_json_path)
                code_params = self.decide_surface_code(device_info, result)
                result = self.surface_code_api.generate_surface_code_layout(
                    layout_type=code_params['layout'],
                    code_distance=code_params['distance'],
                    device=device_info.get('name') or device_info.get('device_name')
                )
            # Add more modules as needed (code_switcher, execution, etc.)
        return result

    def get_workflow_status(self, workflow_id: str) -> dict:
        """
        Retrieve the status and progress of a running workflow.
        """
        return self.workflow_status.get(workflow_id, {'status': 'unknown'})

    def cancel_workflow(self, workflow_id: str) -> None:
        """
        Cancel a running workflow.
        """
        if workflow_id in self.workflow_status:
            self.workflow_status[workflow_id]['status'] = 'cancelled'

    def set_workflow_policy(self, policy: dict) -> None:
        """
        Set or update workflow policies (e.g., priorities, fallback strategies).
        """
        self.current_policy = policy
        self.config['workflow_policy'] = policy
        # Persist via ConfigManager to handle non-writable package paths
        try:
            ConfigManager.save_config('workflow_policy', config=self.config)
        except Exception as e:
            print(f"[WARN] Failed to save workflow_policy to default path: {e}")

    def get_workflow_policy(self) -> dict:
        """
        Retrieve the current workflow policy.
        """
        return self.current_policy

    def initialize_code(self, code_distance, layout_type, mapping_constraints):
        """
        Initialize a surface code and mapping for the given parameters.
        Returns (code, mapping) for compatibility with test workflows.
        """
        # Use device_config if provided, else fallback to hardware_info from surface_code_api
        device_info = self.device_config if self.device_config is not None else self.surface_code_api.hardware_info
        # Use the unified surface code interface
        from scode.heuristic_layer.surface_code import SurfaceCode
        # Initialize SurfaceCode with current config and device overrides
        surface_code = SurfaceCode(config_overrides=self.config, device_overrides=device_info)
        code = surface_code.get_codes(code_distance, layout_type, num_patches=mapping_constraints.get('num_patches', 1))
        mapping = surface_code.get_multi_patch_mapping(code_distance, layout_type, mapping_constraints)
        return code, mapping

# Alias for backward/test compatibility
Orchestrator = OrchestratorController

   