# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, List, Optional

from scode.api import SurfaceCodeAPI

class SurfaceFamilyAPI:
    """
    Family adapter that wraps SurfaceCodeAPI under a common code-family interface.
    """
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, device_overrides: Optional[Dict[str, Any]] = None):
        self.api = SurfaceCodeAPI(config_overrides, device_overrides)

    def list_layout_types(self) -> List[str]:
        return self.api.list_layout_types()

    def list_code_distances(self, device: str = None, layout_type: str = None) -> List[int]:
        return self.api.list_code_distances(device, layout_type)

    def generate_multi_patch_layout(self, num_patches: int = 1, patch_distances: Optional[List[int]] = None, patch_shapes: Optional[List[str]] = None, visualize: bool = False, device: str = None) -> Dict[str, Any]:
        combined = self.api.generate_multi_patch_surface_code_layout(num_patches, patch_distances, patch_shapes, visualize, device)
        combined['family'] = 'surface'
        # Ensure each code_space tags family
        for cs in combined.get('code_spaces', []):
            cs['family'] = 'surface'
            # Enrich with supported_logical_gates for FT builder compatibility
            try:
                layout_type = cs.get('layout_type') or combined.get('layout_type')
                code_distance = cs.get('code_distance') or combined.get('code_distance')
                logical_ops = cs.get('logical_operators')
                cs['supported_logical_gates'] = self.api.list_supported_logical_gates(layout_type, code_distance, logical_ops)
            except Exception:
                # Fallback to a safe default set
                cs['supported_logical_gates'] = ['X', 'Z', 'CNOT', 'H', 'S']
        return combined

    def list_supported_logical_gates(self, layout_type: str = None, code_distance: int = None, logical_operators: dict = None) -> List[str]:
        return self.api.list_supported_logical_gates(layout_type, code_distance, logical_operators)
