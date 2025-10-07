from typing import Dict, Any, Optional
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from scode.multi_patch_mapper.multi_patch_mapper import MultiPatchMapper
from scode.utils.decoder_interface import DecoderInterface
import math
import logging

logger = logging.getLogger(__name__)

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

class SurfaceCode:
    def __init__(self, config_overrides: dict = None, device_overrides: dict = None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('multi_patch_rl_agent')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device_config = deep_merge(base_device, device_overrides or {})
        self.h_layer = HeuristicInitializationLayer(self.config, self.device_config)
        self.mapper = MultiPatchMapper(self.config, self.device_config)
        self.current_codes = None
        self.current_mapping = None

    def get_codes(self, code_distance: int, layout_type: str, num_patches: int = 1):
        """
        Generate one or more surface code layouts.
        Args:
            code_distance: Distance of the surface code
            layout_type: Type of surface code layout
            num_patches: Number of code patches to generate (default: 1)
        Returns:
            List of SurfaceCodeObject instances
        """
        config = self.device_config if hasattr(self, 'device_config') else {}
        surface_code_cfg = config.get('multi_patch_rl_agent', {}).get('environment', {})
        min_d = surface_code_cfg.get('min_code_distance', 3)
        if code_distance is None:
            # Auto-selection is handled in get_multi_patch_mapping(), which evaluates LER across distances.
            # Keep get_codes() simple and deterministic: require an explicit code_distance.
            raise ValueError("code_distance is required for get_codes(); use get_multi_patch_mapping(...) for auto-selection.")
        # All patch shapes, code distances, and constraints are config-driven
        patch_shapes = surface_code_cfg.get('patch_shapes', ['rectangular'] * num_patches)
        if len(patch_shapes) < num_patches:
            patch_shapes = patch_shapes + [patch_shapes[-1]] * (num_patches - len(patch_shapes))
        self.current_codes = [self.h_layer.generate_surface_code(code_distance, layout_type) for _ in range(num_patches)]
        # Debug: log size and content of each patch's qubit_layout
        for idx, code in enumerate(self.current_codes):
            if not hasattr(code, 'qubit_layout'):
                logger.debug("Patch %s for d=%s has no qubit_layout attribute!", idx, code_distance)
            elif not code.qubit_layout:
                logger.debug("Patch %s for d=%s has EMPTY qubit_layout!", idx, code_distance)
            else:
                logger.debug("Patch %s for d=%s qubit_layout size: %s", idx, code_distance, len(code.qubit_layout))
        # Robustness: check for empty or invalid layouts
        for idx, code in enumerate(self.current_codes):
            if not hasattr(code, 'qubit_layout') or not code.qubit_layout:
                raise ValueError(f"Generated patch {idx} for code distance {code_distance} is empty or invalid.")
        return self.current_codes

    def get_multi_patch_mapping(self, code_distance: int, layout_type: str, mapping_constraints: Dict[str, Any]):
        """
        Returns a mapping dict that always includes 'logical_to_physical' for GUI overlays.
        This is the unified entry point for all mapping requests (single or multi-patch).
        Args:
            code_distance: Distance of the surface code (if None, will be auto-selected)
            layout_type: Type of surface code layout
            mapping_constraints: Dict of mapping constraints (must include 'num_patches' for multi-patch)
        Returns:
            Mapping dictionary
        """
        # l is the number of logical qubits in the circuit
        l = mapping_constraints.get('num_logical_qubits', 1)
        # Only add +1 if code switching is required
        if mapping_constraints.get('require_code_switching', False):
            num_patches = l + 1
        else:
            num_patches = l
        n = self.device_config.get('max_qubits')
        if n is None:
            qc = self.device_config.get('qubit_connectivity')
            if qc:
                n = len(qc)
        if n is None:
            raise ValueError("Device qubit count could not be determined from config.")
        import math
        # --- If code_distance is None, auto-select the best d based on LER ---
        if code_distance is None:
            min_d = 3
            if layout_type in ('planar', 'rotated'):
                max_d = int(math.sqrt(((n/num_patches)+1)/2))
            elif layout_type == 'color':
                max_d = int(math.sqrt(((2*n/num_patches)-1)/3))
            else:
                max_d = int(math.sqrt(n/num_patches))
            best_ler = float('inf')
            best_d = None
            best_mapping = None
            for d in range(min_d, max_d+1, 2):  # Only odd distances
                try:
                    logger.debug("Trying code distance %s for %s patches...", d, num_patches)
                    codes = self.get_codes(d, layout_type, num_patches)
                    if any(not hasattr(code, 'qubit_layout') or not code.qubit_layout for code in codes):
                        logger.debug("At least one patch for d=%s is empty or invalid!", d)
                        raise ValueError(f"Generated patch for code distance {d} is empty or invalid.")
                    mapping = self.mapper.map_patches(codes, mapping_constraints)
                    # Estimate logical error rate (LER) for this mapping using DecoderInterface
                    ler = None
                    try:
                        layout = codes[0] if len(codes) == 1 else codes
                        noise_model = self.device_config.get('noise_model', {'p': 0.001})
                        ler = DecoderInterface.estimate_logical_error_rate(layout, mapping, noise_model)
                    except Exception as e:
                        logger.error("LER estimation error: %s", e)
                        ler = None
                    if ler is not None and ler < best_ler:
                        best_ler = ler
                        best_d = d
                        best_mapping = mapping
                except Exception as e:
                    logger.warning("Skipping code distance %s: %s", d, e)
                    continue  # Skip invalid d
            if best_mapping is None:
                logger.debug("No valid code distance found for %s patches on this device after trying all distances.", num_patches)
                raise ValueError(f"No valid code distance found for {num_patches} patches on this device.")
            logger.info("Selected code type: %s, code distance: %s, LER: %.3e", layout_type, best_d, best_ler)
            best_mapping['selected_code_distance'] = best_d
            best_mapping['selected_code_type'] = layout_type
            best_mapping['selected_ler'] = best_ler
            self.current_mapping = best_mapping
            return best_mapping
        # --- If code_distance is provided, use as before ---
        code_distance = int(code_distance)
        if layout_type in ('planar', 'rotated'):
            max_d = int(math.sqrt(((n/num_patches)+1)/2))
            required_qubits = num_patches*(2*code_distance*code_distance-1)
            if required_qubits > n:
                logger.debug("Not enough physical qubits for %s planar/rotated patches of distance %s. Required: %s, available: %s", num_patches, code_distance, required_qubits, n)
                raise ValueError(f"Not enough physical qubits for {num_patches} planar/rotated patches of distance {code_distance}. Max allowed distance: {max_d}, available qubits: {n}")
        elif layout_type == 'color':
            max_d = int(math.sqrt(((2*n/num_patches)-1)/3))
            required_qubits = num_patches*((3*code_distance*code_distance+1)//2)
            if required_qubits > n:
                raise ValueError(f"Not enough physical qubits for {num_patches} color code patches of distance {code_distance}. Max allowed distance: {max_d}, available qubits: {n}")
        else:
            max_d = int(math.sqrt(n/num_patches))
            required_qubits = num_patches*code_distance*code_distance
            if required_qubits > n:
                logger.debug("Not enough physical qubits for %s patches of distance %s. Required: %s, available: %s", num_patches, code_distance, required_qubits, n)
                raise ValueError(f"Not enough physical qubits for {num_patches} patches of distance {code_distance}. Max allowed distance: {max_d}, available qubits: {n}")
        if code_distance > max_d:
            logger.debug("Code distance %s too large for %s patches on this device. Max allowed: %s", code_distance, num_patches, max_d)
            raise ValueError(f"Code distance {code_distance} too large for {num_patches} patches on this device. Max allowed: {max_d}")
        codes = self.get_codes(code_distance, layout_type, num_patches)
        if any(not hasattr(code, 'qubit_layout') or not code.qubit_layout for code in codes):
            logger.debug("At least one patch for d=%s is empty or invalid!", code_distance)
            raise ValueError(f"Generated patch for code distance {code_distance} is empty or invalid.")
        mapping = self.mapper.map_patches(codes, mapping_constraints)
        self.current_mapping = mapping
        logger.debug("get_multi_patch_mapping: mapping_constraints=%s", mapping_constraints)
        logger.debug("get_multi_patch_mapping: num_patches=%s", num_patches)
        patch_shapes = mapping_constraints.get('patch_shapes', None)
        if not patch_shapes or len(patch_shapes) < num_patches:
            default_shape = 'rectangular'
            patch_shapes = (patch_shapes or []) + [default_shape] * (num_patches - len(patch_shapes or []))
        if len(patch_shapes) != num_patches:
            logger.warning("get_multi_patch_mapping: patch_shapes length %s does not match num_patches %s", len(patch_shapes), num_patches)
            logger.warning("patch_shapes: %s", patch_shapes)
            patch_shapes = patch_shapes[:num_patches]
        mapping_constraints['patch_shapes'] = patch_shapes
        logger.debug("get_multi_patch_mapping: final patch_shapes=%s", patch_shapes)
        return mapping 

    def get_single_patch_mapping(self, code_distance: int, layout_type: str, mapping_constraints: Optional[Dict[str, Any]] = None):
        """Compatibility wrapper that enforces a single logical patch mapping.

        This routes through get_multi_patch_mapping to keep a consistent return shape.
        """
        constraints = (mapping_constraints or {}).copy()
        # Ensure single logical qubit without code switching
        constraints['num_logical_qubits'] = 1
        if constraints.get('require_code_switching', False):
            constraints['require_code_switching'] = False
        return self.get_multi_patch_mapping(code_distance, layout_type, constraints)