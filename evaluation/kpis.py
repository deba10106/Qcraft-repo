# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from typing import Dict, Any

def compute_mapping_kpis(mapping_info: Dict[str, Any]) -> Dict[str, Any]:
    """Compute simple, family-agnostic KPIs from mapping_info.
    Safe with partial data and used for logging/ dashboards.
    """
    kpis = {
        'patch_count': None,
        'physical_qubits': None,
        'mapping_present': False,
        'has_overlap': False,
    }
    mp = (mapping_info or {}).get('multi_patch_mapping', {})
    mpl = (mp or {}).get('multi_patch_layout', {})
    if isinstance(mpl, dict) and mpl:
        kpis['patch_count'] = len(mpl)
        try:
            kpis['physical_qubits'] = sum(len(p.get('layout', {}) or {}) for p in mpl.values())
        except Exception:
            kpis['physical_qubits'] = None
    l2p = (mapping_info or {}).get('logical_to_physical', {})
    if isinstance(l2p, dict) and l2p:
        kpis['mapping_present'] = True
        vals = list(l2p.values())
        kpis['has_overlap'] = (len(set(vals)) < len(vals))
    return kpis
