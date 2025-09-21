from __future__ import annotations
from typing import Dict, Any
import time

class JobPackager:
    """
    Converts a QCraft FT circuit into a provider-ready job package, embedding
    capability hints and provenance metadata. Does not expose logical IR; only
    code-space/FT circuit and derived native instructions if available.
    """
    def __init__(self, device_info: Dict[str, Any], capabilities: Dict[str, Any]):
        self.device_info = device_info or {}
        self.capabilities = capabilities or {}

    def package(self, ft_circuit: Dict[str, Any]) -> Dict[str, Any]:
        # For now, store circuit in a qcraft-specific field to allow local execution.
        # Native instruction lowering should be handled by optimization/export passes.
        native_job = {
            'instructions': ft_circuit.get('gates', []),
            'qcraft_circuit': ft_circuit,
        }
        meta = {
            'device': self.device_info.get('device_name') or self.device_info.get('name'),
            'provider': self.device_info.get('provider_name'),
            'timestamp': time.time(),
        }
        return {
            'provider': self.device_info.get('provider_name'),
            'device': self.device_info.get('device_name') or self.device_info.get('name'),
            'capabilities': self.capabilities,
            'native_job': native_job,
            'metadata': meta,
        }
