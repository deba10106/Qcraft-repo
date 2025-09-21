from __future__ import annotations
from typing import Dict, Any

"""
Policy for selecting implementation of non-transversal gates.
Returns a protocol name compatible with CodeSwitcher protocols:
  - 'magic_state_injection'
  - 'lattice_surgery'
  - 'teleportation'

Decision factors
- Device capabilities (conditional, mid_circuit_measure, dynamic_circuits)
- FT builder config preferences (weights)
- Gate class (Clifford vs non-Clifford)
"""

NON_CLIFFORD = {"T", "Tdg", "CCX", "CS", "CSdg"}
CLIFFORD = {"H", "S", "Sdg", "CNOT", "CX", "CZ", "X", "Y", "Z"}


def select_non_transversal_policy(gate_name: str, device_info: Dict[str, Any], ft_config: Dict[str, Any]) -> str:
    g = (gate_name or "").upper()
    caps = device_info.get("capabilities", {}) if isinstance(device_info, dict) else {}
    conditional = bool(caps.get("conditional", False))
    dynamic = bool(caps.get("dynamic_circuits", False))
    # Preferences from config
    prefs = (ft_config or {}).get("non_transversal_preferences", {})
    # Per-gate override from YAML if provided
    per_gate = {k.upper(): v for k, v in (prefs.get("per_gate", {}) or {}).items()} if isinstance(prefs.get("per_gate", {}), dict) else {}
    if g in per_gate:
        return per_gate[g]
    prefer = prefs.get("prefer", "magic_state_injection")
    # Heuristics
    if g in NON_CLIFFORD:
        # If dynamic circuits/conditional exist, lattice surgery is often better than teleportation for structural conversions
        if dynamic or conditional:
            if prefer in ("lattice_surgery", "magic_state_injection"):
                return prefer
            return "lattice_surgery"
        # If device lacks dynamic/conditional support, prefer magic state injection (precomputed ancilla)
        return "magic_state_injection"
    # For other unsupported gates, attempt teleportation as neutral default
    return "teleportation"
