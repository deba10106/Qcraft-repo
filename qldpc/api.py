# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, List, Optional
import networkx as nx

from configuration_management.config_manager import ConfigManager
from .generator import QLDPCGenerator
from .mapper import greedy_map_code_spaces


class QLDPCAPI:
    """
    Family adapter that exposes qLDPC generation and mapping under the common code-family interface.
    Implements the methods expected by CodePatchRegistry consumers.
    """
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, device_overrides: Optional[Dict[str, Any]] = None):
        ConfigManager.load_registry()
        self.config = ConfigManager.get_config('qldpc_config') or {}
        if config_overrides:
            # non-destructive merge
            c = dict(self.config)
            c.update(config_overrides or {})
            self.config = c
        self.device = device_overrides or {}
        self.generator = QLDPCGenerator(config_overrides=self.config, device_overrides=self.device)

    # ---- Discovery helpers ----
    def list_layout_types(self) -> List[str]:
        return list(self.config.get('layouts', []) or ['tanner'])

    def list_code_distances(self, device: str = None, layout_type: str = None) -> List[int]:
        dists = []
        for c in self.config.get('codes', []):
            if layout_type is None or c.get('layout_type') == layout_type:
                try:
                    d = int(c.get('distance', 3))
                    if d not in dists:
                        dists.append(d)
                except Exception:
                    continue
        return sorted(dists)

    # ---- Generation ----
    def generate_multi_patch_layout(self, num_patches: int = 1, patch_distances: Optional[List[int]] = None, patch_shapes: Optional[List[str]] = None, visualize: bool = False, device: str = None) -> Dict[str, Any]:
        num = max(1, int(num_patches or 1))
        patch_distances = (patch_distances or [3] * num)[:num]
        patch_shapes = (patch_shapes or ['tanner'] * num)[:num]
        # Generate individual patches
        patches = []
        combined_qubit_layout: Dict[int, Dict[str, Any]] = {}
        combined_stabilizer_map = {'X': [], 'Z': []}
        combined_logical_operators = {'X': [], 'Z': []}
        idx_offset = 0
        patch_info = []
        for i in range(num):
            layout = patch_shapes[i] if i < len(patch_shapes) else 'tanner'
            dist = int(patch_distances[i] if i < len(patch_distances) else 3)
            code_obj = self.generator.generate_code(layout, dist, visualize=False)
            # Remap qubit indices to be globally unique across patches
            local_map = {}
            for lq, pos in code_obj.qubit_layout.items():
                gq = idx_offset + int(lq)
                local_map[int(lq)] = gq
                combined_qubit_layout[gq] = dict(pos)
            # Stabilizers with remapped data qubits
            for xstab in code_obj.stabilizer_map.get('X', []):
                combined_stabilizer_map['X'].append({
                    'ancilla': xstab['ancilla'] + idx_offset,  # simple offset for ancilla too
                    'data_qubits': [local_map[int(q)] for q in xstab['data_qubits']]
                })
            for zstab in code_obj.stabilizer_map.get('Z', []):
                combined_stabilizer_map['Z'].append({
                    'ancilla': zstab['ancilla'] + idx_offset,
                    'data_qubits': [local_map[int(q)] for q in zstab['data_qubits']]
                })
            # Logical operators
            for k in ('X', 'Z'):
                combined_logical_operators[k].extend([local_map[int(q)] for q in code_obj.logical_operators.get(k, [])])
            # Patch info
            patch_info.append({
                'index': i,
                'layout_type': code_obj.layout_type,
                'code_distance': code_obj.code_distance,
                'qubit_map': local_map
            })
            # Advance offset: data qubits + ancilla approximation
            data_qubit_count = len(code_obj.qubit_layout)
            anc_count = len(code_obj.stabilizer_map.get('X', [])) + len(code_obj.stabilizer_map.get('Z', []))
            idx_offset += data_qubit_count + anc_count
            patches.append(code_obj)
        # Build simple adjacency across all global qubits
        g = nx.Graph()
        for i, p in enumerate(patches):
            # lift local adjacency into global using patch_info qubit_map
            l2g = patch_info[i]['qubit_map']
            for (u, v) in p.adjacency_matrix.edges():
                g.add_edge(l2g[int(u)], l2g[int(v)])
        # Prepare code_spaces with supported gates
        supported = self.config.get('supported_logical_gates', ['X', 'Z', 'CNOT', 'H', 'S'])
        code_spaces = []
        for i, p in enumerate(patches):
            cs = {
                'name': f'code_space_{i}',
                'family': 'qldpc',
                'code_distance': p.code_distance,
                'layout_type': p.layout_type,
                'qubit_layout': p.qubit_layout,
                'stabilizer_map': p.stabilizer_map,
                'logical_operators': p.logical_operators,
                'adjacency_matrix': p.adjacency_matrix,
                'supported_logical_gates': list(supported),
            }
            code_spaces.append(cs)
        combined = {
            'qubit_layout': combined_qubit_layout,
            'stabilizer_map': combined_stabilizer_map,
            'logical_operators': combined_logical_operators,
            'adjacency_matrix': g,
            'patch_info': patch_info,
            'num_patches': len(patches),
            'code_distance': patches[0].code_distance if patches else None,
            'layout_type': patches[0].layout_type if patches else None,
            'code_spaces': code_spaces,
            'family': 'qldpc'
        }
        return combined

    def list_supported_logical_gates(self, layout_type: str = None, code_distance: int = None, logical_operators: dict = None) -> List[str]:
        # For now, supported gates are global per family in config; could be refined per layout/distance
        return list(self.config.get('supported_logical_gates', ['X', 'Z', 'CNOT', 'H', 'S']))

    # ---- Mapping ----
    def get_multi_patch_mapping(self, code_distance: int, layout_type: str, mapping_constraints: Optional[Dict[str, Any]] = None, device: str = None, use_rl_agent: bool = False, rl_policy_path: Optional[str] = None) -> Dict[str, Any]:
        mapping_constraints = mapping_constraints or {}
        num_patches = int(mapping_constraints.get('num_patches', mapping_constraints.get('num_logical_qubits', 1)))
        patch_shapes = mapping_constraints.get('patch_shapes', [layout_type] * num_patches)
        patch_distances = mapping_constraints.get('patch_distances', [code_distance] * num_patches)
        # Generate code_spaces to map
        combined = self.generate_multi_patch_layout(num_patches=num_patches, patch_distances=patch_distances, patch_shapes=patch_shapes, visualize=False)
        code_spaces = combined.get('code_spaces', [])
        # Map greedily to hardware using device overrides if provided
        device_info = self.device if isinstance(self.device, dict) else {}
        mapping = greedy_map_code_spaces(code_spaces, device_info, constraints=mapping_constraints)
        # Build a minimal resource_allocation to help FT builder associate patches
        # We assume logical qubits are numbered 0..N-1; assign round-robin to patches
        resource_allocation = {}
        total_lq = sum(len(cs.get('qubit_layout', {})) for cs in code_spaces)
        N = max(mapping_constraints.get('num_logical_qubits', 1), total_lq)
        for q in range(N):
            pid = q % max(1, num_patches)
            resource_allocation[(pid, q)] = pid
        mapping['resource_allocation'] = resource_allocation
        return mapping
