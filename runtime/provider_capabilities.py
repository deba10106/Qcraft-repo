from __future__ import annotations
from typing import Dict, Any

class ProviderCapabilities:
    def __init__(self, capabilities: Dict[str, Any]):
        self.capabilities = capabilities or {}

    @property
    def mid_circuit_measure(self) -> bool:
        return bool(self.capabilities.get('mid_circuit_measure', False))

    @property
    def conditional(self) -> bool:
        return bool(self.capabilities.get('conditional', False))

    @property
    def dynamic_circuits(self) -> bool:
        return bool(self.capabilities.get('dynamic_circuits', False))

    def as_dict(self) -> Dict[str, Any]:
        return {
            'mid_circuit_measure': self.mid_circuit_measure,
            'conditional': self.conditional,
            'dynamic_circuits': self.dynamic_circuits,
        }

def detect_capabilities(device_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect backend capabilities from device_info (config-driven). Fallbacks are conservative.
    """
    caps = device_info.get('capabilities', {}) if isinstance(device_info, dict) else {}
    # Heuristics: IBM devices tend to support conditional and mid-circuit measurement on many backends.
    provider = (device_info.get('provider_name') or '').lower() if isinstance(device_info, dict) else ''
    if provider == 'ibm':
        caps.setdefault('mid_circuit_measure', True)
        caps.setdefault('conditional', True)
        caps.setdefault('dynamic_circuits', True)
    return ProviderCapabilities(caps).as_dict()
