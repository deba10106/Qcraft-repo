from __future__ import annotations
from typing import Dict, Any, List, Optional
import networkx as nx


def greedy_map_code_spaces(code_spaces: List[Dict[str, Any]], device: Dict[str, Any], constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Simple greedy mapper for qLDPC code spaces to hardware qubits.
    - Maps data qubits to available hardware qubits sorted by lowest error rate
    - Does not overlap across patches
    - Returns structure similar to MultiPatchMapper output
    """
    constraints = constraints or {}
    hw_connectivity = device.get('qubit_connectivity', {})
    qubit_errors = device.get('qubit_properties', {})
    def get_error(q):
        return qubit_errors.get(int(q), {}).get('readout_error', 0.0)
    exclude = set(constraints.get('exclude_qubits', []))
    available_hw = [int(q) for q in hw_connectivity.keys() if int(q) not in exclude]
    available_hw.sort(key=get_error)
    logical_to_physical = {}
    used_hw = set()
    # Build multi_patch_layout in the format expected downstream
    multi_patch_layout = {}
    for i, cs in enumerate(code_spaces):
        layout = cs.get('qubit_layout', {})
        patch_map = {}
        for lq in layout.keys():
            # select first available hw not used yet
            hw = next((q for q in available_hw if q not in used_hw), None)
            if hw is None:
                break
            patch_map[int(lq)] = hw
            used_hw.add(hw)
        logical_to_physical[i] = patch_map
        # Export a basic layout view
        export_layout = {}
        for lq, pos in layout.items():
            export_layout[int(lq)] = {
                'x': float(pos.get('x', 0)),
                'y': float(pos.get('y', 0)),
                'type': pos.get('type', 'data')
            }
        multi_patch_layout[i] = {'layout': export_layout, 'shape': cs.get('layout_type', 'tanner')}
    return {
        'multi_patch_layout': multi_patch_layout,
        'logical_to_physical': logical_to_physical,
        'optimization_metrics': {},
        'has_overlap': False
    }
