# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from compiler.cost_model import DualPathCostModel
from code_patches.registry import CodePatchRegistry

class PatchDiscoverer:
    """
    Patch Discoverer (enterprise-grade) that recommends code patch parameters
    (family/layout, distance, count) given a circuit IR, device profile, and optional error profile.

    This integrates with existing SCODE modules (heuristic layer + API) and the dual-path
    cost model to rank candidate patch configurations without any external services.
    """
    def __init__(self, device_profile: Optional[Dict[str, Any]] = None):
        ConfigManager.load_registry()
        base_hw = DeviceAbstraction.load_selected_device(ConfigManager.config_registry['hardware'])
        self.device = {**base_hw, **(device_profile or {})}
        self.registry = CodePatchRegistry(config_overrides=None, device_overrides=self.device)
        self.cost_model = DualPathCostModel(self.device)

    def _family_candidates(self) -> List[dict]:
        cands = []
        for fam in self.registry.list_families():
            api = self.registry.get_family_api(fam)
            for layout in api.list_layout_types():
                for d in api.list_code_distances(self.device.get('device_name'), layout):
                    cands.append({'family': fam, 'layout': layout, 'distance': d, 'api': api})
        return cands

    def _score_candidate(self, circuit: Dict[str, Any], family: str, layout: str, distance: int, logical_qubits: int) -> float:
        # Generate a quickly combined layout for this family
        api = self.registry.get_family_api(family)
        codes = api.generate_multi_patch_layout(
            num_patches=max(1, logical_qubits),
            patch_distances=[distance]*max(1, logical_qubits),
            patch_shapes=[layout]*max(1, logical_qubits),
            visualize=False
        )
        # Use dual-path estimates; choose best
        a = self.cost_model.estimate_path_A(circuit)
        b = self.cost_model.estimate_path_B(circuit)
        best_err = min(a['expected_error'], b['expected_error'])
        # Penalize larger distance (resource) and many patches lightly
        resource_penalty = 0.001 * distance * max(1, logical_qubits)
        return best_err + resource_penalty

    def discover(self, ir: Dict[str, Any], error_profile: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Return a ranked list of candidate patches and mapping hints.
        patches: [{family, distance, layout_type, resources}]
        mapping_hints: {num_patches, patch_shapes, min_distance_between_patches}
        """
        logical_qubits = len(ir.get('qubits', [])) if isinstance(ir.get('qubits'), list) else int(ir.get('qubits', 1) or 1)
        fam_cands = self._family_candidates()
        candidates: List[Tuple[float, Dict[str, Any]]] = []
        for fc in fam_cands:
            fam = fc['family']
            layout = fc['layout']
            d = fc['distance']
            score = self._score_candidate(ir, fam, layout, d, logical_qubits)
            api = fc['api']
            try:
                supported = api.list_supported_logical_gates(layout_type=layout, code_distance=d)
            except Exception:
                supported = []
            candidates.append((score, {
                'family': fam,
                'distance': d,
                'layout_type': layout,
                'supported_logical': supported,
                'resources': {
                    'phys_qubits': None,
                    'ancilla': None
                }
            }))
        # Rank ascending by score
        candidates.sort(key=lambda x: x[0])
        patches = [c[1] for c in candidates[: min(5, len(candidates))]]
        # Mapping hints prefer chosen best layout
        best = candidates[0][1] if candidates else {'layout_type': 'planar', 'distance': 3, 'family': 'surface'}
        mapping_hints = {
            'num_patches': max(1, logical_qubits),
            'patch_shapes': [best['layout_type']]*max(1, logical_qubits),
            'min_distance_between_patches': 1
        }
        return patches, mapping_hints
