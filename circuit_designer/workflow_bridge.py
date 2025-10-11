# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import os
import json
import uuid
import time
import yaml
import subprocess
import threading
from typing import Dict, Any, Optional, List
from circuit_optimization.strategies.rl_based import RLBasedOptimizer
from orchestration_controller.orchestrator import OrchestratorController
from circuit_optimization.api import CircuitOptimizationAPI
from scode.api import SurfaceCodeAPI, deep_merge
from code_switcher.code_switcher import CodeSwitcherAPI
from execution_simulation.execution_simulator import ExecutionSimulatorAPI
from logging_results.logging_results_manager import LoggingResultsManager
from fault_tolerant_circuit_builder.ft_circuit_builder import FaultTolerantCircuitBuilder
from evaluation.evaluation_framework import EvaluationFramework
from hardware_abstraction.device_abstraction import DeviceAbstraction
from configuration_management.config_manager import ConfigManager
import importlib.resources
from stable_baselines3.common.vec_env import SubprocVecEnv
from scode.utils.decoder_interface import DecoderInterface
from utils.credential_manager import CredentialManager

# Ensure config registry is loaded before any config access
ConfigManager.load_registry()

def get_provider_and_device(config_dir):
    import importlib.resources
    import os
    try:
        with importlib.resources.open_text('configs', 'hardware.json') as f:
            hw = json.load(f)
    except (FileNotFoundError, ModuleNotFoundError):
        hardware_json_path = os.path.join('configs', 'hardware.json')
        with open(hardware_json_path, 'r') as f:
            hw = json.load(f)
    return hw['provider_name'], hw['device_name']

class QuantumWorkflowBridge:
    """
    Main integration bridge for quantum workflow: RL training, circuit optimization, device/config management.
    Only exposes methods used by the GUI and orchestrator. All legacy and unused methods removed.
    """
    def __init__(self, config_dir=None):
        self.config_dir = config_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), '../configs'))
        self.provider, self.device = get_provider_and_device(self.config_dir)
        self.orchestrator = OrchestratorController()
        self.optimizer = CircuitOptimizationAPI()
        self.surface_code_api = SurfaceCodeAPI()
        self.code_switcher = CodeSwitcherAPI()
        self.executor = ExecutionSimulatorAPI()
        self.logger = LoggingResultsManager()
        self.ft_builder = FaultTolerantCircuitBuilder()
        self.evaluator = None  # Created per config as needed
        self.agent_config = {}  # Store agent config (including device info) from GUI

    def set_agent_config(self, agent_config: dict):
        """
        Store agent config (including device info) for use in RL training and optimization.
        """
        self.agent_config = agent_config

    def optimize_circuit(self, circuit: Dict, device_info: Dict, config_overrides: Optional[Dict] = None, progress_callback=None) -> Dict:
        """
        Optimize the input circuit for the given device using orchestrator and fixed optimizer API.
        Always provide full device_info (including qubit_connectivity, qubit_positions, connectivity) if available.
        """
        info = dict(device_info) if device_info else {}
        # Try to fill all possible connectivity keys from full_device_info
        if hasattr(self, 'full_device_info') and self.full_device_info:
            # Always fill all variants for connectivity and positions
            # --- PATCH: Always set both 'connectivity' and 'qubit_connectivity' as aliases ---
            conn = None
            if 'qubit_connectivity' in self.full_device_info:
                conn = self.full_device_info['qubit_connectivity']
            elif 'connectivity' in self.full_device_info:
                conn = self.full_device_info['connectivity']
            if conn is not None:
                info['qubit_connectivity'] = conn
                info['connectivity'] = conn
            if 'qubit_positions' in self.full_device_info:
                if 'qubit_positions' not in info:
                    info['qubit_positions'] = self.full_device_info['qubit_positions']

        return self.orchestrator.optimize_circuit(circuit, info, config_overrides, progress_callback=progress_callback)

    def run_workflow(self, circuit: Dict, user_config: Optional[Dict] = None, progress_callback=None) -> Dict:
        """
        Execute the full orchestrator workflow and return enriched outputs for GUI consumption.
        Includes: analysis, error_profile, strategy, patches, mapping_hints, code_layout_combined,
        mapping_info, ft_circuit, schedule, decoder_plan, validation, capabilities, job_package, provenance.
        """
        result = self.orchestrator.run_workflow(circuit, user_config, progress_callback=progress_callback)
        # Log a compact summary to assist GUI dashboards
        try:
            summary = {
                'workflow_id': result.get('workflow_id'),
                'status': result.get('status'),
                'strategy': result.get('strategy', {}).get('selected'),
                'code_family': result.get('code_family'),
                'layout': result.get('surface_code', {}).get('layout'),
                'distance': result.get('surface_code', {}).get('distance'),
                'has_ft_circuit': 'ft_circuit' in result,
                'has_mapping': 'mapping_info' in result,
                'has_schedule': 'schedule' in result,
                'has_validation': 'validation' in result,
                'has_job_package': 'job_package' in result,
            }
            self.logger.log_event('workflow_summary', summary, level='INFO')
        except Exception:
            pass
        return result

    def map_circuit_to_surface_code(self, circuit: Dict, device: str, layout_type: str, code_distance: int, provider: str = None, config_overrides: Optional[Dict] = None, progress_callback=None, mapping_constraints: Optional[Dict] = None, sweep_code_distance: bool = False) -> Dict:
        """
        Map a circuit to a surface code. If sweep_code_distance is False (default), only try the minimum valid code distance (usually d=3). If True, sweep all valid code distances up to the requested value.
        For multi-logical-qubit circuits, always use the multi-patch RL agent for mapping.
        """
        # Extract logical qubit count from circuit or config
        logical_qubits = None
        if circuit and 'qubits' in circuit:
            logical_qubits = len(circuit['qubits'])
            self.surface_code_api.update_logical_qubit_count(logical_qubits)
            self.logger.log_event('surface_code_mapping', {'logical_qubits': logical_qubits}, level='INFO')
        elif config_overrides and 'circuit' in config_overrides and 'logical_qubits' in config_overrides['circuit']:
            logical_qubits = config_overrides['circuit']['logical_qubits']
            self.logger.log_event('surface_code_mapping', {'logical_qubits': logical_qubits}, level='INFO')
        else:
            # Fallback: try config or default to 1
            base_config = ConfigManager.get_config('multi_patch_rl_agent')
            logical_qubits = base_config.get('circuit', {}).get('logical_qubits', 1)
            self.logger.log_event('surface_code_mapping', {'logical_qubits': logical_qubits}, level='WARNING')
        # Ensure mapping_constraints is set and num_logical_qubits is correct
        if mapping_constraints is None:
            mapping_constraints = {}
        mapping_constraints['num_logical_qubits'] = logical_qubits
        # Debug logging for mapping parameters
        self.logger.log_event('surface_code_mapping', {'logical_qubits': logical_qubits, 'code_distance': code_distance, 'layout_type': layout_type, 'mapping_constraints': mapping_constraints, 'sweep_code_distance': sweep_code_distance}, level='DEBUG')
        # Device qubit count for debug
        self.logger.log_event('surface_code_mapping', {'provider': provider, 'device': device}, level='DEBUG')
        # Ensure provider is set
        if not provider:
            try:
                provider_from_hw, _ = get_provider_and_device(self.config_dir)
                provider = provider_from_hw
                self.logger.log_event('surface_code_mapping', {'provider': provider}, level='DEBUG')
            except Exception as e:
                self.logger.log_event('surface_code_mapping', {'error': str(e)}, level='ERROR')
        # Ensure 'd' is defined for non-sweep path
        if not sweep_code_distance:
            d = code_distance
        try:
            device_info = DeviceAbstraction.get_device_info(provider, device) if provider and device else None
            self.logger.log_event('surface_code_mapping', {'device_info': device_info}, level='DEBUG')
            device_qubits = device_info.get('max_qubits', 0) if device_info else 0
            # Calculate required_qubits before using it
            num_patches = mapping_constraints.get('num_logical_qubits', logical_qubits)
            required_qubits = (code_distance or 3) ** 2 * num_patches  # Adjust as needed for your code logic
            self.logger.log_event('surface_code_mapping', {'device_qubits': device_qubits, 'required_qubits': required_qubits}, level='DEBUG')
            if device_qubits < required_qubits:
                self.logger.log_event('surface_code_mapping', {'error': f"Insufficient qubits. Requires {required_qubits} but device has {device_qubits}."}, level='WARNING')
                return {'status': 'failed', 'error': f"Insufficient qubits. Requires {required_qubits} but device has {device_qubits}."}
            self.logger.log_event('surface_code_mapping', {'code_distance': d}, level='INFO')
            # --- Use multi-patch RL agent for multi-logical-qubit circuits ---
            if mapping_constraints.get('num_logical_qubits', 1) > 1:
                self.logger.log_event('surface_code_mapping', {'multi_patch_rl_agent': True}, level='INFO')
                # Defensive: ensure num_patches and patch_shapes are set correctly
                num_logical_qubits = mapping_constraints.get('num_logical_qubits', logical_qubits)
                if 'num_patches' not in mapping_constraints or mapping_constraints['num_patches'] != num_logical_qubits:
                    self.logger.log_event('surface_code_mapping', {'num_patches': num_logical_qubits}, level='WARNING')
                    mapping_constraints['num_patches'] = num_logical_qubits
                patch_shapes = mapping_constraints.get('patch_shapes', None)
                # Fix: Replace unsupported patch shapes with the current layout_type
                supported_layouts = ['planar', 'rotated', 'color']
                if not patch_shapes or len(patch_shapes) < num_logical_qubits:
                    patch_shapes = (patch_shapes or []) + [layout_type] * (num_logical_qubits - len(patch_shapes or []))
                # Replace any unsupported patch shapes
                patch_shapes = [shape if shape in supported_layouts else layout_type for shape in patch_shapes]
                mapping_constraints['patch_shapes'] = patch_shapes
                if len(mapping_constraints['patch_shapes']) != num_logical_qubits:
                    self.logger.log_event('surface_code_mapping', {'patch_shapes': mapping_constraints['patch_shapes']}, level='WARNING')
                    mapping_constraints['patch_shapes'] = mapping_constraints['patch_shapes'][:num_logical_qubits]
                self.logger.log_event('surface_code_mapping', {'mapping_constraints': mapping_constraints}, level='DEBUG')
            # --- DEBUG PATCH CONSTRUCTION ---
            patch_distances = [d]*mapping_constraints.get('num_patches', 1)
            patch_shapes = mapping_constraints.get('patch_shapes', None)
            # Print device config grid connectivity
            if hasattr(self.surface_code_api, 'hardware_info'):
                hw_info = self.surface_code_api.hardware_info
                grid_conn = hw_info.get('grid_connectivity') or hw_info.get('topology_type') or 'unknown'
                self.logger.log_event('surface_code_mapping', {'grid_connectivity': grid_conn}, level='DEBUG')
            codes = self.surface_code_api.generate_multi_patch_surface_code_layout(
                num_patches=mapping_constraints.get('num_patches', 1),
                patch_distances=[d]*mapping_constraints.get('num_patches', 1),
                patch_shapes=patch_shapes,
                visualize=False
            )
            # Print debug info for each patch
            if 'patch_info' in codes:
                for patch in codes['patch_info']:
                    self.logger.log_event('surface_code_mapping', {'patch_index': patch['index'], 'code_distance': patch['code_distance'], 'layout_type': patch['layout_type']}, level='DEBUG')
                    qubit_map = patch['qubit_map']
                    self.logger.log_event('surface_code_mapping', {'qubit_map': qubit_map}, level='DEBUG')
                    # Print qubit types
                    for q, info in codes['qubit_layout'].items():
                        if q in qubit_map.values():
                            self.logger.log_event('surface_code_mapping', {'qubit': q, 'info': info}, level='DEBUG')
                self.logger.log_event('surface_code_mapping', {'stabilizer_map': codes.get('stabilizer_map', {}), 'logical_operators': codes.get('logical_operators', {})}, level='DEBUG')
                # --- END DEBUG PATCH CONSTRUCTION ---
                mapping = self.surface_code_api.get_multi_patch_mapping(
                    code_distance=d,
                    layout_type=layout_type,
                    mapping_constraints=mapping_constraints,
                    device=device,
                    use_rl_agent=True,
                    rl_policy_path=None
                )
                # Ensure provider/device strings propagate for downstream UIs
                mapping['device'] = device or (device_info.get('device_name') if device_info else None) or 'unknown'
                mapping['provider'] = provider or (device_info.get('provider_name') if device_info else None) or 'unknown'
                # Attach any discovered strategy/patches/capabilities from orchestrator if available later in the pipeline
                return {
                    'mapping_info': mapping,
                    'selected_code_distance': d,
                    'selected_code_type': layout_type,
                    'selected_ler': mapping.get('optimization_metrics', {}).get('logical_error_rate', None)
                }
            # --- Fallback: single-patch mapping logic ---
            self.logger.log_event('surface_code_mapping', {'single_patch_rl_agent': True}, level='INFO')
            return self.orchestrator.map_circuit_to_surface_code(circuit, device, layout_type, d, provider, config_overrides, progress_callback=progress_callback, mapping_constraints=mapping_constraints)
        except Exception as e:
            code_distance_str = str(d) if 'd' in locals() else str(code_distance) if 'code_distance' in locals() else 'unknown'
            self.logger.log_event('surface_code_mapping', {'error': str(e), 'code_distance': code_distance_str}, level='WARNING')
            return {'status': 'failed', 'error': str(e)}

    # --- Code Switching ---
    def identify_switching_points(self, circuit: Dict, code_info: Dict) -> List[Dict]:
        # Only pass natively supported gates, never SWAP
        natively_supported = [g for g in code_info.get('supported_gates', []) if g != 'SWAP']
        code_info = dict(code_info)
        code_info['supported_gates'] = natively_supported
        return self.code_switcher.identify_switching_points(circuit, code_info)

    def select_switching_protocol(self, gate: str, available_protocols: List[str], config: Dict = None) -> str:
        # Always include 'teleportation' for SWAP
        if gate.upper() == 'SWAP' and 'teleportation' not in available_protocols:
            available_protocols = available_protocols + ['teleportation']
        self.logger.log_event('code_switching', {'gate': gate, 'available_protocols': available_protocols}, level='DEBUG')
        return self.code_switcher.select_switching_protocol(gate, available_protocols, config)

    def apply_code_switching(self, circuit: Dict, switching_points: List[Dict], protocols: List[Dict], device_info: Dict) -> Dict:
        return self.code_switcher.apply_code_switching(circuit, switching_points, protocols, device_info)

    # --- Execution/Simulation ---
    def list_backends(self) -> List[str]:
        return self.executor.list_backends()

    def run_circuit(self, circuit: Dict, run_config: Dict = None) -> str:
        return self.executor.run_circuit(circuit, run_config)

    def get_job_status(self, job_id: str) -> Dict:
        return self.executor.get_job_status(job_id)

    def get_job_result(self, job_id: str) -> Dict:
        return self.executor.get_job_result(job_id)

    # --- Logging & Results ---
    def log_event(self, event: str, details: Dict = None, level: str = 'INFO') -> None:
        self.logger.log_event(event, details, level)

    def log_metric(self, metric_name: str, value: float, step: int = None, run_id: str = None) -> None:
        self.logger.log_metric(metric_name, value, step, run_id)

    def store_result(self, run_id: str, result: Dict) -> None:
        self.logger.store_result(run_id, result)

    def get_result(self, run_id: str) -> Dict:
        return self.logger.get_result(run_id)

    # --- Fault-Tolerant Circuit Builder ---
    def assemble_fault_tolerant_circuit(self, logical_circuit: Dict, mapping_info: Dict, code_spaces: List[Dict], device_info: Dict, config_overrides: Optional[Dict] = None, progress_callback=None) -> Dict:
        return self.orchestrator.assemble_fault_tolerant_circuit(logical_circuit, mapping_info, code_spaces, device_info, config_overrides, progress_callback=progress_callback)

    def validate_fault_tolerant_circuit(self, circuit: Dict, device_info: Dict) -> bool:
        return self.ft_builder.validate_fault_tolerant_circuit(circuit, device_info)

    # --- Evaluation ---
    def evaluate_logical_error_rate(self, layout: Dict, hardware: Dict, noise_model: Dict) -> float:
        if self.evaluator is None:
            self.evaluator = EvaluationFramework(self.surface_code_api._load_config())
        return self.evaluator.evaluate_logical_error_rate(layout, hardware, noise_model)

    def evaluate_resource_efficiency(self, layout: Dict) -> Dict:
        if self.evaluator is None:
            self.evaluator = EvaluationFramework(self.surface_code_api._load_config())
        return self.evaluator.evaluate_resource_efficiency(layout)

    def evaluate_learning_efficiency(self, training_log: Any) -> Dict:
        if self.evaluator is None:
            self.evaluator = EvaluationFramework(self.surface_code_api._load_config())
        return self.evaluator.evaluate_learning_efficiency(training_log)

    def evaluate_hardware_adaptability(self, results: Any) -> Dict:
        if self.evaluator is None:
            self.evaluator = EvaluationFramework(self.surface_code_api._load_config())
        return self.evaluator.evaluate_hardware_adaptability(results)

    # --- Device Abstraction ---
    def get_device_info(self, provider_name: str, device_name: str) -> Dict:
        return DeviceAbstraction.get_device_info(provider_name, device_name)

    def list_devices(self, provider_name: str) -> List[str]:
        return DeviceAbstraction.list_devices(provider_name)

    # --- Config Management ---
    def get_config(self, module_name: str) -> Dict:
        return ConfigManager.get_config(module_name)

    def update_config(self, module_name: str, updates: Dict) -> None:
        ConfigManager.update_config(module_name, updates)

    # --- Config Management (Extended) ---
    def list_configs(self) -> list:
        return ConfigManager.list_configs()

    def get_schema(self, module_name: str) -> dict:
        return ConfigManager.get_schema(module_name)

    def save_config(self, module_name: str, config: dict) -> None:
        ConfigManager.save_config(module_name, config=config)

    # --- Training APIs ---
    def train_surface_code_agent(self, provider: str, device: str, layout_type: str, code_distance: int, config_overrides: dict = None, log_callback=None, run_id=None) -> dict:
        return self.surface_code_api.train_surface_code_agent(provider, device, layout_type, code_distance, config_overrides, log_callback=log_callback, run_id=run_id)

    def get_surface_code_training_status(self, agent_path: str) -> dict:
        return self.surface_code_api.get_training_status(agent_path)

    # --- Optimizer Training (Advanced RL/ML Implementation) ---
    def train_optimizer_agent(self, circuit: dict, device_info: dict, config_overrides: dict = None, log_callback=None, run_id=None, circuits: Optional[List[dict]] = None, procedural: Optional[dict] = None) -> str:
        """
        Train an RL/ML-based circuit optimizer agent. Returns the path to the trained agent artifact.
        Uses RLBasedOptimizer (stable-baselines3 PPO) and logs progress/results via LoggingResultsManager.
        All config is YAML/JSON-driven and API overrides take priority.
        """
        if run_id is None:
            run_id = str(uuid.uuid4())
        # Load config using ConfigManager
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('optimization')
        config = deep_merge(base_config, config_overrides or {})
        # Load device info using DeviceAbstraction
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        device = deep_merge(base_device, device_info or {})
        logger = LoggingResultsManager()
        logger.log_event('optimizer_training_started', {'run_id': run_id, 'device': device.get('name'), 'config': config}, level='INFO')
        start_time = time.time()
        optimizer = RLBasedOptimizer(config)
        # Prepare RL environment and model
        # Use RLBasedOptimizer and new CircuitOptimizationEnvironment for RL circuit optimization
        from circuit_optimization.rl_env import CircuitOptimizationEnvironment
        from stable_baselines3 import PPO
        rl_env_conf = config.get('rl_config', {})
        reward_weights = rl_env_conf.get('reward_weights', None)
        normalize_reward = rl_env_conf.get('normalize_reward', False)
        curriculum = rl_env_conf.get('curriculum', None)
        curriculum_cfg = curriculum if curriculum and curriculum.get('enabled', False) else None
        n_envs = rl_env_conf.get('n_envs', 1)
        # Closure captures circuit and device from outer scope (train_optimizer_agent arguments)
        from stable_baselines3.common.monitor import Monitor
        from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

        def make_env():
            env = CircuitOptimizationEnvironment(
                circuit=circuit,
                device_info=device,
                action_space_size=rl_env_conf.get('action_space_size', 8),
                reward_weights=reward_weights,
                normalize_reward=normalize_reward,
                curriculum=curriculum_cfg,
                circuits=circuits,
                procedural=procedural
            )
            env = Monitor(env)
            # Extend here: e.g., VecNormalize, TimeLimit, custom wrappers
            return env

        vec_strategy = rl_env_conf.get('vec_strategy', 'subproc')  # 'subproc', 'dummy', or 'none'
        n_envs = rl_env_conf.get('n_envs', 4)  # Default to 4 for production

        if vec_strategy == 'subproc' and n_envs > 1:
            env = SubprocVecEnv([make_env for _ in range(n_envs)])
        elif vec_strategy == 'dummy' and n_envs > 1:
            env = DummyVecEnv([make_env for _ in range(n_envs)])
        elif n_envs == 1 or vec_strategy == 'none':
            env = make_env()
        else:
            raise ValueError(f"Unsupported vectorization strategy: {vec_strategy} with n_envs={n_envs}")
        total_timesteps = rl_env_conf.get('num_episodes', 10000) * 200
        model = PPO('MlpPolicy', env, verbose=1, batch_size=rl_env_conf.get('batch_size', 64), n_steps=2048, device='auto')
        # Progress callback for logging
        class ProgressCallback:
            def __init__(self, total, logger, run_id, start_time, log_callback):
                self.total = total
                self.last = 0
                self.logger = logger
                self.run_id = run_id
                self.start_time = start_time
                self.log_callback = log_callback
                self.last_reward = None
            def __call__(self, locals_, globals_):
                n = locals_['self'].num_timesteps
                progress = n / self.total
                elapsed = time.time() - self.start_time
                # Log metrics
                self.logger.log_metric('optimizer_progress', progress, step=n, run_id=self.run_id)
                rewards = locals_.get('rewards', [])
                if rewards is not None and len(rewards) > 0:
                    self.last_reward = sum(rewards) / len(rewards)
                    self.logger.log_metric('optimizer_reward', self.last_reward, step=n, run_id=self.run_id)
                if self.log_callback:
                    msg = f"Progress: {n}/{self.total}, Reward: {self.last_reward}, Elapsed: {elapsed:.1f}s"
                    self.log_callback(msg, progress)
                if n - self.last >= 200:
                    self.last = n
                return True
        model.learn(total_timesteps=total_timesteps, callback=ProgressCallback(total_timesteps, logger, run_id, start_time, log_callback))
        artifacts_dir = config.get('system', {}).get('output_dir', './outputs')
        artifacts_dir = os.path.abspath(os.path.join(artifacts_dir, 'training_artifacts'))
        os.makedirs(artifacts_dir, exist_ok=True)
        policy_path = os.path.join(artifacts_dir, f"optimizer_{device.get('name', 'unknown')}_sb3_ppo.zip")
        model.save(policy_path)
        elapsed = time.time() - start_time
        logger.log_event('optimizer_training_ended', {'run_id': run_id, 'policy_path': policy_path, 'elapsed': elapsed}, level='INFO')
        logger.store_result(run_id, {'policy_path': policy_path, 'device': device.get('name'), 'elapsed': elapsed})
        if log_callback:
            log_callback(f"[INFO] Optimizer training complete. Policy saved to {policy_path}", 1.0)
        return policy_path

    def get_optimizer_training_status(self, agent_path: str) -> dict:
        """
        Return training progress, metrics, and status for a given optimizer agent artifact.
        Enhanced: robust metadata search, error handling, human-readable timestamps, artifact hash, in-progress/corrupt detection, and logging.
        """
        import datetime
        import hashlib
        logger = LoggingResultsManager()
        status = {'status': 'not_found', 'path': agent_path}
        if not os.path.exists(agent_path):
            logger.log_event('optimizer_status_checked', status, level='DEBUG')
            return status
        # Check for .lock file (in-progress)
        if os.path.exists(agent_path + '.lock'):
            status['status'] = 'in_progress'
        else:
            status['status'] = 'completed'
        # Try to find a metadata/log file with the same base name
        base, _ = os.path.splitext(agent_path)
        meta_files = [base + ext for ext in ['.json', '.yaml', '.yml']]
        meta = None
        meta_error = None
        for meta_file in meta_files:
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, 'r') as f:
                        if meta_file.endswith('.json'):
                            meta = json.load(f)
                        else:
                            meta = yaml.safe_load(f)
                    break
                except Exception as e:
                    meta_error = str(e)
                    status['meta_error'] = meta_error
        if meta:
            status.update(meta)
        # Always add artifact file stats
        try:
            stat = os.stat(agent_path)
            status['artifact_size'] = stat.st_size
            status['last_modified'] = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
            status['created'] = datetime.datetime.fromtimestamp(stat.st_ctime).isoformat()
            # Hash for integrity
            with open(agent_path, 'rb') as f:
                sha256 = hashlib.sha256()
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    sha256.update(data)
                status['artifact_sha256'] = sha256.hexdigest()
            if stat.st_size == 0:
                status['status'] = 'corrupt'
        except Exception as e:
            status['stat_error'] = str(e)
        logger.log_event('optimizer_status_checked', status, level='DEBUG')
        return status
        return status

    # --- API Key Management ---
    def get_api_key(self, provider_name: str) -> str:
        """Retrieve provider API key securely via CredentialManager."""
        service = 'ibm_quantum' if 'ibm' in provider_name.lower() else (
            'ionq' if 'ionq' in provider_name.lower() else (
            'rigetti' if 'rigetti' in provider_name.lower() else provider_name.lower()))
        try:
            cred_mgr = CredentialManager()
            return cred_mgr.get_credential(service)
        except Exception:
            # Fallback to any legacy config-based retrieval
            return ConfigManager.get_api_key(provider_name)

    def set_api_key(self, provider_name: str, api_key: str) -> None:
        """Securely store the provider API key via CredentialManager."""
        service = 'ibm_quantum' if 'ibm' in provider_name.lower() else (
            'ionq' if 'ionq' in provider_name.lower() else (
            'rigetti' if 'rigetti' in provider_name.lower() else provider_name.lower()))
        cred_mgr = CredentialManager()
        cred_mgr.store_credential(service, api_key)
        if hasattr(self, 'logger'):
            self.logger.log_event('api_key_set_secure', {'provider': provider_name, 'service': service}, level='INFO')

    def train_multi_patch_rl_agent(self, config_path=None, log_callback=None, config_overrides=None):
        """
        Launch multi-patch RL agent training with curriculum and continuous learning.
        Streams logs to the GUI via log_callback. Runs in-process for direct integration.
        """
        return self._run_multi_patch_rl_training(config_path=config_path, log_callback=log_callback, config_overrides=config_overrides)

    def _run_multi_patch_rl_training(self, config_path=None, log_callback=None, config_overrides=None):
        try:
            import yaml, time, os
            from scode.rl_agent.environment import SurfaceCodeEnvironment
            from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
            from stable_baselines3 import PPO
            from scode.rl_agent.progress import ProgressBarCallback
            from scode.rl_agent.reward_engine import MultiPatchRewardEngine
            from configuration_management.config_manager import ConfigManager
            import json
            if config_path is None:
                config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../configs/multi_patch_rl_agent.yaml'))
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            # Non-fatal schema validation to catch errors early
            try:
                from configuration_management.config_manager import ConfigManager
                ConfigManager.validate_config('multi_patch_rl_agent')
            except Exception:
                pass
            if log_callback:
                log_callback(f"[INFO] Loaded config from {config_path}", None)
            # Merge config_overrides from GUI, if provided
            if config_overrides:
                from scode.multi_patch_mapper.multi_patch_mapper import merge_configs
                config = merge_configs(config, config_overrides)
            env_cfg = config['multi_patch_rl_agent']['environment']
            agent_cfg = config['multi_patch_rl_agent']['agent']
            curriculum_cfg = config['multi_patch_rl_agent']['curriculum_learning']
            artifact_dir = config['multi_patch_rl_agent']['training_artifacts']['output_dir']
            os.makedirs(artifact_dir, exist_ok=True)
            stages = curriculum_cfg['stages'] if curriculum_cfg['enabled'] else [{'patch_count': env_cfg['patch_count']}]
            # Use device info from GUI if available
            hardware_graph = getattr(self, 'agent_config', {}).get('device', None)
            if hardware_graph is None:
                # Fallback to hardware.json
                with open(os.path.join(os.path.dirname(__file__), '../configs/hardware.json'), 'r') as f:
                    hardware_graph = json.load(f)
            surface_code_generator = HeuristicInitializationLayer(config['multi_patch_rl_agent'], hardware_graph)
            if log_callback:
                log_callback("[INFO] Environment setup complete", None)
            for stage_idx, stage in enumerate(stages):
                if log_callback:
                    log_callback(f"[INFO] Curriculum stage {stage_idx+1}/{len(stages)}: {stage}", None)
                env_cfg_stage = env_cfg.copy()
                env_cfg_stage['patch_count'] = stage['patch_count']
                config['multi_patch_rl_agent']['environment'] = env_cfg_stage
                # Choose environment by code family (default: surface)
                env_family = (config.get('multi_patch_rl_agent', {})
                                   .get('environment', {})
                                   .get('code_family', 'surface'))
                if str(env_family).lower() == 'qldpc':
                    from scode.rl_agent.qldpc_environment import QLDPCEnvironment
                    env = QLDPCEnvironment(
                        config,
                        hardware_graph,
                        qldpc_generator=None,
                        reward_engine=MultiPatchRewardEngine(config)
                    )
                else:
                    env = SurfaceCodeEnvironment(
                        config,
                        hardware_graph,
                        surface_code_generator=surface_code_generator,
                        reward_engine=MultiPatchRewardEngine(config)
                    )
                env.current_phase = stage_idx  # Ensure correct curriculum stage is used
                policy = 'MultiInputPolicy'
                model = PPO(policy, env, **{k: v for k, v in agent_cfg.items() if k not in ['algorithm', 'policy', 'resume_from_checkpoint', 'save_interval', 'total_timesteps']})
                if log_callback:
                    log_callback("[INFO] Agent setup complete", None)
                total_timesteps = stage.get('total_timesteps', agent_cfg['total_timesteps'])
                reporter = ProgressBarCallback(total_timesteps, mode='terminal')
                reporter._on_training_start()
                def progress_callback(locals_, globals_):
                    n = locals_['self'].num_timesteps
                    rewards = locals_.get('rewards', [])
                    infos = locals_.get('infos', [])
                    avg_reward = sum(rewards) / len(rewards) if rewards else None
                    lers = [info.get('ler', None) or info.get('logical_error_rate', None) for info in infos if isinstance(info, dict)]
                    lers = [ler for ler in lers if ler is not None]
                    avg_ler = sum(lers) / len(lers) if lers else None
                    reporter.update(n, reward=avg_reward, ler=avg_ler)
                    if log_callback:
                        msg = f"Step: {n}/{total_timesteps} | Reward: {avg_reward} | LER: {avg_ler}"
                        log_callback(msg, n/total_timesteps)
                    return True
                if log_callback:
                    log_callback(f"[INFO] Starting training for stage {stage_idx+1}", None)
                model.learn(total_timesteps=total_timesteps, callback=progress_callback)
                reporter.finish()
                if log_callback:
                    log_callback(f"[INFO] Finished training for stage {stage_idx+1}", None)
                # --- Save artifact using config-driven naming ---
                training_artifacts_cfg = config['multi_patch_rl_agent'].get('training_artifacts', {})
                artifact_dir = training_artifacts_cfg.get('output_dir', './outputs/training_artifacts')
                artifact_naming = training_artifacts_cfg.get('artifact_naming', '{provider}_{device}_{layout_type}_d{code_distance}_patches{patch_count}_stage{curriculum_stage}_sb3_ppo_surface_code_{timestamp}.zip')
                env_cfg_final = config['multi_patch_rl_agent']['environment']
                # Use the current local time from the user context
                timestamp = '20250610_153447'  # 2025-06-10T15:34:47+08:00
                artifact_name = artifact_naming.format(
                    provider=env_cfg_final.get('provider', 'provider'),
                    device=env_cfg_final.get('device', 'device'),
                    layout_type=env_cfg_final.get('layout_type', 'rotated'),
                    code_distance=env_cfg_final.get('code_distance', 3),
                    patch_count=env_cfg_final.get('patch_count', 1),
                    curriculum_stage=stage_idx+1,
                    timestamp=timestamp,
                    code_family=env_cfg_final.get('code_family', 'surface')
                )
                artifact_path = os.path.join(artifact_dir, artifact_name)
                if log_callback:
                    log_callback(f"[INFO] Saving checkpoint: {artifact_path}", None)
                model.save(artifact_path)
                if log_callback:
                    log_callback(f"[INFO] Saved checkpoint: {artifact_path}", None)
            if log_callback:
                log_callback("[INFO] Training complete.", 1.0)
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"[ERROR] {str(e)}", None)
            raise