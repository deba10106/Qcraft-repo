from __future__ import annotations
from typing import Dict, Any
import copy

VALID_POLICIES = {"none", "obfuscate", "strict-local"}

def apply_export_policy(job_package: Dict[str, Any], policy: str = "obfuscate") -> Dict[str, Any]:
    """
    Apply export policy to a job_package before sending to a provider or saving externally.

    Policies:
    - none: no changes.
    - obfuscate: remove QCraft-specific circuit details, redacts metadata fields.
    - strict-local: deny export by raising an error.
    """
    if policy not in VALID_POLICIES:
        raise ValueError(f"Unknown export policy '{policy}'. Valid: {sorted(list(VALID_POLICIES))}")
    if policy == "strict-local":
        raise PermissionError("Export blocked by policy 'strict-local'")
    if policy == "none":
        return job_package
    # obfuscate
    pkg = copy.deepcopy(job_package)
    native_job = pkg.get('native_job', {})
    # Remove embedded qcraft source circuit
    if 'qcraft_circuit' in native_job:
        native_job.pop('qcraft_circuit', None)
    # Redact sensitive metadata values
    meta = pkg.get('metadata', {})
    if 'comments' in meta:
        meta['comments'] = '<redacted>'
    pkg['metadata'] = meta
    pkg['native_job'] = native_job
    return pkg
