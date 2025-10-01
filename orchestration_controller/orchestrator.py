import os
import yaml
import json
import uuid
from typing import Dict, Any, List, Optional
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from circuit_optimization.api import CircuitOptimizationAPI
from scode.api import SurfaceCodeAPI
# from code_switcher.api import CodeSwitcherAPI  # Available via code_switcher module
# from execution_simulation.api import ExecutionSimulatorAPI  # Available via execution_simulation
from fault_tolerant_circuit_builder.ft_circuit_builder import FaultTolerantCircuitBuilder
from logging_results.logging_results_manager import LoggingResultsManager
from compiler.cost_model import DualPathCostModel
from adaptive_qec.discoverer.patch_discoverer import PatchDiscoverer
from runtime.provider_capabilities import detect_capabilities
from runtime.job_packager import JobPackager
from privacy.export_policy import apply_export_policy
from provenance.manifest import generate_provenance_manifest
from decoder_runtime.decoder import LocalDecoder
from code_patches.registry import CodePatchRegistry
from evaluation.kpis import compute_mapping_kpis

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
        # Validate key configs early; non-fatal on validation error
        for cfg_name in ('workflow_policy', 'analysis', 'profiler'):
            try:
                ConfigManager.validate_config(cfg_name)
            except Exception:
                pass
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
            # --- Strategy selection (Dual-Path Cost Model) ---
            try:
                cm = DualPathCostModel(device_info)
                pathA = cm.estimate_path_A(circuit)
                pathB = cm.estimate_path_B(circuit)
                strategy = 'A' if pathA['expected_error'] <= pathB['expected_error'] else 'B'
                self.logger.log_event('strategy_selected', {'workflow_id': workflow_id, 'pathA': pathA, 'pathB': pathB, 'selected': strategy}, level='INFO')
            except Exception as e:
                self.logger.log_event('strategy_error', {'workflow_id': workflow_id, 'error': str(e)}, level='WARNING')
                pathA = pathB = {}
                strategy = 'auto'
            # --- Patch Discoverer (hints for mapping) ---
            try:
                pd = PatchDiscoverer(device_profile=device_info)
                patches, mapping_hints = pd.discover(circuit)
                self.logger.log_event('patch_discovery', {'workflow_id': workflow_id, 'patches': patches, 'mapping_hints': mapping_hints}, level='INFO')
            except Exception as e:
                self.logger.log_event('patch_discovery_error', {'workflow_id': workflow_id, 'error': str(e)}, level='WARNING')
                patches, mapping_hints = [], {}
            module_sequence = self.config.get('workflow_policy', {}).get('module_sequence', [
                'analysis', 'profiler', 'surface_code', 'ft_builder', 'mapper', 'co_optimize', 'optimizer', 'scheduler', 'decoder_placement', 'validation', 'code_switcher', 'executor'])
            step_results = {
                'circuit': circuit,
                'device_info': device_info,
                'strategy': {'selected': strategy, 'pathA': pathA, 'pathB': pathB},
                'patches': patches,
                'mapping_hints': mapping_hints,
            }
            for idx, module in enumerate(module_sequence):
                if progress_callback:
                    progress_callback(f"Running module: {module}", 0.1 + 0.8 * idx / len(module_sequence))
                self.logger.log_event('module_started', {'workflow_id': workflow_id, 'module': module, 'step': idx}, level='INFO')
                if module == 'analysis':
                    # Static analysis of the logical circuit
                    analysis = self.static_analyze_circuit(circuit)
                    step_results['analysis'] = analysis
                    self.workflow_status[workflow_id]['steps'].append('analyzed')
                elif module == 'profiler':
                    # Build uncertainty-aware error profile
                    error_profile = self.build_error_profile(device_info)
                    step_results['error_profile'] = error_profile
                    self.workflow_status[workflow_id]['steps'].append('profiled')
                elif module == 'surface_code':
                    # Family-aware selection: prefer PatchDiscoverer top candidate
                    selected_patch = (step_results.get('patches') or [{}])[0]
                    family = selected_patch.get('family', 'surface')
                    layout_sel = selected_patch.get('layout_type', None)
                    dist_sel = selected_patch.get('distance', None)
                    if not layout_sel or not dist_sel:
                        fallback = self.decide_surface_code(device_info, circuit, user_config)
                        layout_sel = layout_sel or fallback['layout']
                        dist_sel = dist_sel or fallback['distance']
                    # Build mapping constraints (merge hints)
                    mapping_constraints = user_config.get('multi_patch', {'num_patches': 1, 'patch_shapes': [layout_sel]}) if user_config else {'num_patches': 1, 'patch_shapes': [layout_sel]}
                    if step_results.get('mapping_hints'):
                        mapping_constraints = deep_merge(mapping_constraints, step_results['mapping_hints'])
                    # Generate family-specific combined layout (includes code_spaces)
                    registry = CodePatchRegistry(config_overrides=None, device_overrides=device_info)
                    fam_api = registry.get_family_api(family)
                    num_patches = mapping_constraints.get('num_patches') or mapping_constraints.get('num_logical_qubits') or max(1, len(circuit.get('qubits', [])) or 1)
                    patch_shapes = mapping_constraints.get('patch_shapes') or [layout_sel] * int(num_patches)
                    patch_distances = [int(dist_sel)] * int(num_patches)
                    combined_layout = fam_api.generate_multi_patch_layout(
                        num_patches=int(num_patches),
                        patch_distances=patch_distances,
                        patch_shapes=patch_shapes,
                        visualize=False,
                        device=device_info.get('name') or device_info.get('device_name')
                    )
                    # For backward compatibility keep surface_code fields
                    step_results['surface_code'] = {'layout': layout_sel, 'distance': int(dist_sel), 'family': family}
                    step_results['surface_code_layout'] = combined_layout  # store for UI/reference
                    step_results['code_family'] = family
                    step_results['code_layout_combined'] = combined_layout
                    self.workflow_status[workflow_id]['steps'].append({'code_family': family, 'layout': layout_sel, 'distance': int(dist_sel)})
                elif module == 'co_optimize':
                    # Iterative co-optimization between patch discovery and mapping
                    iters = int(self.current_policy.get('co_optimization', {}).get('iterations', 0))
                    if iters > 0:
                        best = self.co_optimize_mapping(step_results, iterations=iters)
                        if best:
                            step_results.update(best)
                    self.workflow_status[workflow_id]['steps'].append('co_optimized')
                elif module == 'optimizer':
                    # Optimize the FT circuit if available, else fallback to logical
                    circuit_to_optimize = step_results.get('ft_circuit', step_results.get('optimized_circuit', step_results['circuit']))
                    optimized_circuit = self.optimize_circuit(circuit_to_optimize, device_info, user_config, progress_callback=progress_callback)
                    step_results['optimized_circuit'] = optimized_circuit
                    self.workflow_status[workflow_id]['steps'].append('circuit_optimized')
                elif module == 'mapper':
                    mapping_constraints = user_config.get('multi_patch', {'num_patches': 1, 'patch_shapes': ['rectangular']}) if user_config else {'num_patches': 1, 'patch_shapes': ['rectangular']}
                    # Merge mapping hints from PatchDiscoverer
                    if step_results.get('mapping_hints'):
                        mapping_constraints = deep_merge(mapping_constraints, step_results['mapping_hints'])
                    # Route to family-specific mapper when not surface
                    family = step_results.get('code_family', 'surface')
                    layout_sel = step_results.get('surface_code', {}).get('layout')
                    dist_sel = step_results.get('surface_code', {}).get('distance')
                    if family != 'surface':
                        registry = CodePatchRegistry(config_overrides=None, device_overrides=device_info)
                        fam_api = registry.get_family_api(family)
                        fam_mapping = fam_api.get_multi_patch_mapping(
                            code_distance=int(dist_sel),
                            layout_type=layout_sel,
                            mapping_constraints=mapping_constraints,
                            device=device_info.get('name') or device_info.get('device_name'),
                            use_rl_agent=False,
                            rl_policy_path=None
                        )
                        mapping_info = {'multi_patch_mapping': fam_mapping}
                    else:
                        mapping_info = self.map_circuit_to_surface_code(
                            step_results.get('optimized_circuit', step_results['circuit']),
                            device_info.get('name') or device_info.get('device_name'),
                            layout_sel,
                            dist_sel,
                            None, user_config, progress_callback=progress_callback, mapping_constraints=mapping_constraints
                        )
                    step_results['mapping_info'] = mapping_info
                    # Compute family-agnostic KPIs for dashboards/QA
                    try:
                        kpis = compute_mapping_kpis(mapping_info)
                        step_results['mapping_kpis'] = kpis
                        self.logger.log_event('mapping_kpis', {'workflow_id': workflow_id, 'kpis': kpis}, level='INFO')
                    except Exception as e:
                        self.logger.log_event('mapping_kpis_error', {'workflow_id': workflow_id, 'error': str(e)}, level='WARNING')
                    self.workflow_status[workflow_id]['steps'].append('circuit_mapped')
                elif module == 'ft_builder':
                    # Prefer code_spaces from combined layout (family APIs include supported_logical_gates)
                    code_spaces = step_results.get('code_layout_combined', {}).get('code_spaces', [])
                    if not code_spaces and 'mapping_info' in step_results and 'multi_patch_mapping' in step_results['mapping_info']:
                        mp = step_results['mapping_info']['multi_patch_mapping']
                        if 'multi_patch_layout' in mp:
                            # Build enriched code_spaces per patch with family and supported gates
                            family = step_results.get('code_family', 'surface')
                            layout_sel = step_results.get('surface_code', {}).get('layout')
                            dist_sel = step_results.get('surface_code', {}).get('distance')
                            try:
                                registry = CodePatchRegistry(config_overrides=None, device_overrides=device_info)
                                fam_api = registry.get_family_api(family)
                                supported = fam_api.list_supported_logical_gates(layout_sel, dist_sel, None)
                            except Exception:
                                supported = ['X', 'Z', 'CNOT', 'H', 'S']
                            code_spaces = []
                            for pid, patch in mp['multi_patch_layout'].items():
                                layout = patch.get('layout', {})
                                cs = {
                                    'name': f'code_space_{pid}',
                                    'family': family,
                                    'code_distance': dist_sel,
                                    'layout_type': layout_sel,
                                    'qubit_layout': layout,
                                    'supported_logical_gates': supported,
                                }
                                code_spaces.append(cs)
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
                elif module == 'scheduler':
                    # Resource scheduling & optimization based on FT circuit and analysis
                    ft_circuit = step_results.get('ft_circuit')
                    if ft_circuit:
                        schedule = self.schedule_resources(ft_circuit, step_results.get('analysis', {}), device_info)
                        step_results['schedule'] = schedule
                    self.workflow_status[workflow_id]['steps'].append('scheduled')
                elif module == 'decoder_placement':
                    # Decide local vs cloud decoding based on capabilities and schedule
                    caps = step_results.get('capabilities') or detect_capabilities(device_info)
                    plan = self.plan_decoder_placement(step_results.get('schedule', {}), caps)
                    step_results['decoder_plan'] = plan
                    self.workflow_status[workflow_id]['steps'].append('decoder_placed')
                elif module == 'validation':
                    # Validate & estimate fidelity using available models
                    ft_circuit = step_results.get('ft_circuit') or step_results.get('optimized_circuit') or step_results['circuit']
                    validation = self.validate_circuit(ft_circuit, device_info, step_results.get('error_profile', {}))
                    step_results['validation'] = validation
                    self.workflow_status[workflow_id]['steps'].append('validated')
                elif module == 'executor':
                    # Always prepare a provider-ready job package with privacy policy and provenance
                    caps = detect_capabilities(device_info)
                    ft_circuit = step_results.get('ft_circuit', None) or step_results.get('optimized_circuit', None) or step_results['circuit']
                    packager = JobPackager(device_info, caps)
                    job_package = packager.package(ft_circuit)
                    export_policy = self.config.get('privacy', {}).get('export_policy', 'obfuscate')
                    try:
                        job_package = apply_export_policy(job_package, policy=export_policy)
                    except PermissionError as pe:
                        # strict-local: record and continue without exposing job
                        self.logger.log_event('export_blocked', {'workflow_id': workflow_id, 'policy': export_policy, 'error': str(pe)}, level='WARNING')
                        job_package = {'status': 'blocked', 'policy': export_policy}
                    prov_meta = {
                        'device': device_info.get('device_name') or device_info.get('name'),
                        'provider': device_info.get('provider_name'),
                        'strategy': strategy,
                        'selected_layout': step_results.get('surface_code', {}).get('layout'),
                        'code_distance': step_results.get('surface_code', {}).get('distance'),
                    }
                    provenance = generate_provenance_manifest(prov_meta)
                    step_results['capabilities'] = caps
                    step_results['job_package'] = job_package
                    step_results['provenance'] = provenance
                    self.workflow_status[workflow_id]['steps'].append('packaged')
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
            self.logger.log_event('mapping_warning', {'message': 'Empty logical_to_physical mapping received'}, level='WARNING')
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
            self.logger.log_event('mapping_debug', {'patch_count': patch_count, 'max_qubits': max_qubits}, level='DEBUG')
            self.logger.log_event('mapping_debug', {'qubit_types': list(qubit_types)}, level='DEBUG')
        else:
            self.logger.log_event('mapping_warning', {'message': 'Empty multi_patch_layout received'}, level='WARNING')
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
            self.logger.log_event('ft_builder_error', {'error': str(e)}, level='ERROR')
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

    # --- Analysis / Profiler / Co-optimization / Scheduler / Decoder / Validation ---
    def static_analyze_circuit(self, circuit: dict) -> dict:
        """
        Compute static metrics: T-count, T-depth (approx), non-Clifford set, entangling graph,
        depth proxy, parallelism score, and a locality score.
        """
        # Load analysis config
        try:
            analysis_cfg = ConfigManager.get_config('analysis') or {}
        except Exception:
            analysis_cfg = {}
        report_cfg = (analysis_cfg.get('analysis') or {}).get('report', {})
        thresholds = (analysis_cfg.get('analysis') or {}).get('thresholds', {})
        gates = circuit.get('gates', [])
        qubits = circuit.get('qubits', [])
        n = len(qubits)
        twoq_edges = {}
        t_count = 0
        # T-depth approximation: per-qubit T layer count
        t_layers = [0] * n
        used_in_layer = [False] * n
        non_clifford = set()
        depth_proxy = 0
        current_layer_busy = set()
        for g in gates:
            name = (g.get('name') or '').upper()
            q = g.get('qubits', [])
            # Count depth proxy by naive layering: increment when overlapping qubits used
            if any(x in current_layer_busy for x in q):
                depth_proxy += 1
                current_layer_busy = set()
            current_layer_busy.update(q)
            # Non-Clifford identification
            if name in {'T','TDG','CCX','CS','CSdg','RZ'}:
                non_clifford.add(name)
            # T metrics
            if name in {'T','TDG'} and q:
                t_count += 1
                for qid in q:
                    t_layers[qid] += 1
            # Entangling graph
            if len(q) == 2 and name in {'CNOT','CX','CZ','SWAP'}:
                a,b = int(q[0]), int(q[1])
                key = tuple(sorted((a,b)))
                twoq_edges[key] = twoq_edges.get(key, 0) + 1
        t_depth = max(t_layers) if t_layers else 0
        # Locality score: average inverse distance between qubit indices for two-qubit ops
        if twoq_edges:
            inv_d = []
            for (a,b), cnt in twoq_edges.items():
                d = abs(a-b)
                inv_d.append(cnt / max(1, d))
            locality_score = sum(inv_d) / len(inv_d)
        else:
            locality_score = 0.0
        # Parallelism score: fraction of gates that do not overlap with previous gate set
        parallel_gates = 0
        current_layer_busy = set()
        for g in gates:
            q = g.get('qubits', [])
            if not any(x in current_layer_busy for x in q):
                parallel_gates += 1
                current_layer_busy.update(q)
            else:
                current_layer_busy = set(q)
        parallelism = parallel_gates / max(1, len(gates))
        result = {}
        # Only include fields enabled in report config (defaults to True)
        if report_cfg.get('t_count', True):
            result['t_count'] = t_count
        if report_cfg.get('t_depth', True):
            result['t_depth'] = t_depth
        if report_cfg.get('non_clifford', True):
            result['non_clifford'] = sorted(list(non_clifford))
        if report_cfg.get('entangling_graph', True):
            result['twoq_edges'] = {f"{a}-{b}": c for (a,b), c in twoq_edges.items()}
        if report_cfg.get('depth_layers', True):
            result['depth_proxy'] = depth_proxy
        if report_cfg.get('locality_score', True):
            result['locality_score'] = locality_score
        if report_cfg.get('parallelism_score', True):
            result['parallelism'] = parallelism
        # Threshold-based alerts
        alerts = []
        if thresholds:
            if t_count >= thresholds.get('high_t_count', 1e9):
                alerts.append('high_t_count')
            if t_depth >= thresholds.get('high_t_depth', 1e9):
                alerts.append('high_t_depth')
            # Approximate two-qubit density: edges count / total gates
            total_g = len(gates)
            twoq_density = (sum(twoq_edges.values())/max(1,total_g)) if total_g else 0.0
            if twoq_density >= thresholds.get('high_twoq_density', 1.0):
                alerts.append('high_twoq_density')
        if alerts:
            result['alerts'] = alerts
        return result

    def build_error_profile(self, device_info: dict) -> dict:
        """Build an uncertainty-aware error profile combining device data with defaults and profiler config."""
        try:
            profiler_cfg = ConfigManager.get_config('profiler') or {}
        except Exception:
            profiler_cfg = {}
        unc_cfg = (profiler_cfg.get('profiler') or {}).get('uncertainty', {})
        var_thresh = float(unc_cfg.get('variance_threshold', 1.0e-4))
        high_unc_if_no_cal = bool(unc_cfg.get('high_uncertainty_if_no_calibration', True))
        gate_err = device_info.get('gate_error_rates', {}) or {}
        qubits = device_info.get('qubit_properties', {}) or {}
        # Aggregate readout error mean/var
        readout_vals = [float(v.get('readout_error', 0.0)) for v in qubits.values() if isinstance(v, dict)]
        ro_mean = sum(readout_vals)/len(readout_vals) if readout_vals else None
        ro_var = None
        if readout_vals:
            mu = ro_mean
            ro_var = sum((x-mu)**2 for x in readout_vals)/len(readout_vals)
        profile = {
            'gate_error_rates': gate_err,
            'readout_error_mean': ro_mean,
            'readout_error_var': ro_var,
            'has_calibrations': bool(gate_err or readout_vals),
        }
        # Uncertainty flag if little/no data
        if not profile['has_calibrations']:
            profile['uncertainty'] = 'high' if high_unc_if_no_cal else 'medium'
        else:
            profile['uncertainty'] = 'medium' if (ro_var is not None and ro_var > var_thresh) else 'low'
        return profile

    def co_optimize_mapping(self, step_results: dict, iterations: int = 1) -> Optional[dict]:
        """
        Iterate between patch discovery and mapping, selecting the best mapping by expected error.
        """
        circuit = step_results.get('optimized_circuit', step_results['circuit'])
        device_info = step_results['device_info']
        best = None
        best_err = None
        cm = DualPathCostModel(device_info)
        family = step_results.get('code_family', 'surface')
        layout_sel = step_results.get('surface_code', {}).get('layout')
        dist_sel = step_results.get('surface_code', {}).get('distance')
        registry = CodePatchRegistry(config_overrides=None, device_overrides=device_info)
        fam_api = registry.get_family_api(family)
        mapping_constraints = step_results.get('mapping_hints', {})
        for _ in range(max(1, iterations)):
            # Re-generate layout/mapping with current hints
            combined_layout = fam_api.generate_multi_patch_layout(
                num_patches=mapping_constraints.get('num_patches', 1),
                patch_distances=mapping_constraints.get('patch_distances', [dist_sel] * mapping_constraints.get('num_patches', 1)),
                patch_shapes=mapping_constraints.get('patch_shapes', [layout_sel] * mapping_constraints.get('num_patches', 1)),
                visualize=False,
                device=device_info.get('name') or device_info.get('device_name')
            )
            fam_mapping = fam_api.get_multi_patch_mapping(
                code_distance=int(dist_sel),
                layout_type=layout_sel,
                mapping_constraints=mapping_constraints,
                device=device_info.get('name') or device_info.get('device_name'),
                use_rl_agent=False,
                rl_policy_path=None
            )
            mapping_info = {'multi_patch_mapping': fam_mapping}
            # Estimate error on current logical circuit as a proxy
            est = cm.estimate_path_A(circuit)
            err = est.get('expected_error', 1.0)
            record = {
                'code_layout_combined': combined_layout,
                'mapping_info': mapping_info,
            }
            if best is None or err < best_err:
                best = record
                best_err = err
        return best

    def schedule_resources(self, ft_circuit: dict, analysis: dict, device_info: dict) -> dict:
        """Create a resource schedule: syndrome cadence, ancilla allocation, and decoding cadence."""
        d = analysis.get('t_depth', 0) or 0
        # Syndrome cadence heuristic: scale with t_depth and code distance proxy (if present)
        cadence = max(1, min(10, d // 4 + 1))
        max_qubits = device_info.get('max_qubits', 0)
        # Ancilla allocation heuristic: fraction of total qubits reserved
        ancilla_fraction = 0.2 if max_qubits >= 50 else 0.1
        return {
            'syndrome_cadence_cycles': cadence,
            'ancilla_reserved_fraction': ancilla_fraction,
            'decoder_batch_size': max(8, d * 2),
        }

    def plan_decoder_placement(self, schedule: dict, capabilities: dict) -> dict:
        """Decide which decoding tasks to run locally based on capabilities and cadence."""
        conditional = bool(capabilities.get('conditional'))
        dynamic = bool(capabilities.get('dynamic_circuits'))
        local = conditional or dynamic
        return {
            'local_decoder': local,
            'placement': 'local' if local else 'remote',
            'batch_size': schedule.get('decoder_batch_size', 16)
        }

    def validate_circuit(self, circuit: dict, device_info: dict, error_profile: dict) -> dict:
        """Validate and estimate fidelity using config-driven choice: simulator-in-the-loop or fast cost-model proxy."""
        use_sim = bool(self.current_policy.get('validation', {}).get('use_simulator', False))
        if use_sim:
            try:
                from evaluation.evaluation_framework import EvaluationFramework
                eval_api = EvaluationFramework(self.surface_code_api._load_config())
                # Build a minimal layout/noise model dicts; if unavailable, fallback to CM
                layout = step_layout = step_mapping = None  # In a full implementation, derive from code_layout_combined/mapping_info
                noise_model = {
                    'gate_error_rates': device_info.get('gate_error_rates', {}),
                    'readout_error_mean': error_profile.get('readout_error_mean')
                }
                est_fid = eval_api.evaluate_logical_error_rate(layout or {}, device_info, noise_model)
                return {'method': 'simulator', 'estimated_logical_error_rate': est_fid}
            except Exception:
                # Fallback to cost model
                pass
        cm = DualPathCostModel(device_info)
        estA = cm.estimate_path_A(circuit)
        estB = cm.estimate_path_B(circuit)
        sel = 'A' if estA['expected_error'] <= estB['expected_error'] else 'B'
        exp = estA if sel == 'A' else estB
        return {
            'method': 'cost_model',
            'selected_model': sel,
            'expected_error': exp['expected_error'],
            'latency_ns': exp['latency_ns']
        }

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
            self.logger.log_event('policy_save_warning', {'error': str(e)}, level='WARNING')

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

   