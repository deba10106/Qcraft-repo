# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, List, Optional

from configuration_management.config_manager import ConfigManager

class CodePatchRegistry:
    """
    Registry/factory for code patch families. Families and their configs are defined in configs/code_families.yaml.
    Provides a common interface to obtain a family-specific API instance implementing:
      - list_layout_types()
      - list_code_distances(device, layout_type)
      - generate_multi_patch_layout(num_patches, patch_distances, patch_shapes, visualize, device)
      - list_supported_logical_gates(layout_type, code_distance, logical_operators)
      - get_multi_patch_mapping(...) (optional; if not present, orchestrator will rely on family-specific mapper)
    """
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, device_overrides: Optional[Dict[str, Any]] = None):
        ConfigManager.load_registry()
        # Validate schema if available; non-fatal on failure to avoid breaking runtime
        try:
            ConfigManager.validate_config('code_families')
        except Exception:
            pass
        families_cfg = ConfigManager.get_config('code_families')
        self.families = families_cfg.get('families', []) if families_cfg else []
        self.config_overrides = config_overrides
        self.device_overrides = device_overrides

    def list_families(self) -> List[str]:
        return [f.get('name') for f in self.families if f.get('enabled', True)]

    def get_family_api(self, family: str):
        fam = next((f for f in self.families if f.get('name') == family and f.get('enabled', True)), None)
        if fam is None:
            raise KeyError(f"Unknown or disabled code family: {family}")
        api_spec = fam.get('api')
        if not api_spec or 'module' not in api_spec or 'class' not in api_spec:
            raise ValueError(f"Invalid API spec for family {family}: {api_spec}")
        module_name = api_spec['module']
        class_name = api_spec['class']
        # Dynamic import
        mod = __import__(module_name, fromlist=[class_name])
        cls = getattr(mod, class_name)
        return cls(self.config_overrides, self.device_overrides)
