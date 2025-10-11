# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, Optional

from configuration_management.config_manager import ConfigManager
from scode.api import SurfaceCodeAPI


def get_multi_patch_mapping(code_distance: int,
                            layout_type: str,
                            mapping_constraints: Optional[Dict[str, Any]] = None,
                            device: Optional[str] = None,
                            use_rl_agent: bool = True,
                            rl_policy_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Compatibility wrapper that proxies to the existing SurfaceCodeAPI multi-patch
    mapper (RL-enabled). This allows Adaptive QEC flows to import a stable
    function without duplicating mapper logic.
    """
    ConfigManager.load_registry()
    api = SurfaceCodeAPI()
    return api.get_multi_patch_mapping(
        code_distance=code_distance,
        layout_type=layout_type,
        mapping_constraints=mapping_constraints or {},
        device=device,
        use_rl_agent=use_rl_agent,
        rl_policy_path=rl_policy_path
    )
