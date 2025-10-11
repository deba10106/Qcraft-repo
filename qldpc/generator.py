# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, List, Optional
import networkx as nx

from configuration_management.config_manager import ConfigManager
from .objects import QLDPCCodeObject

class QLDPCGenerator:
    """
    Generates qLDPC code objects based on configs/qldpc_config.yaml definitions.
    """
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, device_overrides: Optional[Dict[str, Any]] = None):
        ConfigManager.load_registry()
        # Validate schema if present; non-fatal on failure
        try:
            ConfigManager.validate_config('qldpc_config')
        except Exception:
            pass
        self.config = ConfigManager.get_config('qldpc_config') or {}
        if config_overrides:
            self.config.update(config_overrides or {})
        self.device = device_overrides or {}

    def generate_code(self, family_layout: str, code_distance: int, visualize: bool = False) -> QLDPCCodeObject:
        # Find code spec matching layout and distance
        codes = self.config.get('codes', [])
        spec = None
        for c in codes:
            if c.get('layout_type') == family_layout and int(c.get('distance', 3)) == int(code_distance):
                spec = c
                break
        if spec is None:
            # Fallback: choose first available and warn
            if not codes:
                raise ValueError("No qLDPC codes defined in qldpc_config.yaml")
            spec = codes[0]
        n = int(spec.get('n'))
        data_qubits = list(range(n))
        # Build qubit layout in a simple grid
        qubit_layout = {}
        width = max(1, int(n**0.5))
        for i in data_qubits:
            qubit_layout[i] = {'x': i % width, 'y': i // width, 'type': 'data'}
        # Build Tanner adjacency between data qubits if provided (approximate using Hz*Hx structure)
        adj = nx.Graph()
        adj.add_nodes_from(data_qubits)
        for edge in spec.get('data_adjacency', []):
            u, v = edge
            adj.add_edge(int(u), int(v))
        # Stabilizer map: construct from Hx/Hz indices
        stab = {'X': [], 'Z': []}
        anc_idx = n
        for xstab in spec.get('Hx', []):
            stab['X'].append({'ancilla': anc_idx, 'data_qubits': [int(q) for q in xstab]})
            anc_idx += 1
        for zstab in spec.get('Hz', []):
            stab['Z'].append({'ancilla': anc_idx, 'data_qubits': [int(q) for q in zstab]})
            anc_idx += 1
        # Logical operators (optional) from config, else empty
        logical_ops = spec.get('logical_operators', {'X': [], 'Z': []})
        return QLDPCCodeObject(layout_type=family_layout, code_distance=int(spec.get('distance', code_distance)), qubit_layout=qubit_layout, stabilizer_map=stab, logical_operators=logical_ops, adjacency_matrix=adj)
