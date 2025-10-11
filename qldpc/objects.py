# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any, List
import networkx as nx

class QLDPCCodeObject:
    """
    Minimal qLDPC code object compatible with mapping and FT builder expectations.
    Fields:
      - qubit_layout: {data_qubit_index: {x,y,type}}
      - stabilizer_map: {'X':[...], 'Z':[...]} list of dicts with ancilla and data_qubits
      - logical_operators: {'X':[...], 'Z':[...]} indices of data qubits
      - adjacency_matrix: nx.Graph of data qubit interactions
      - layout_type: string describing layout class
      - code_distance: int
    """
    def __init__(self, layout_type: str, code_distance: int, qubit_layout: Dict[int, Dict[str, int]], stabilizer_map: Dict[str, List[Any]], logical_operators: Dict[str, List[int]], adjacency_matrix: nx.Graph):
        self.layout_type = layout_type
        self.code_distance = code_distance
        self.qubit_layout = qubit_layout
        self.stabilizer_map = stabilizer_map
        self.logical_operators = logical_operators
        self.adjacency_matrix = adjacency_matrix

    def validate(self, raise_error: bool = True) -> bool:
        try:
            assert isinstance(self.qubit_layout, dict)
            assert isinstance(self.stabilizer_map, dict)
            assert isinstance(self.logical_operators, dict)
            assert isinstance(self.adjacency_matrix, nx.Graph)
            return True
        except Exception as e:
            if raise_error:
                raise
            return False
