from typing import Dict, Any, List, Tuple, Optional
import networkx as nx
import numpy as np
from scode.heuristic_layer.surface_code_object import SurfaceCodeObject

class ConnectivityAwareGraphTransformer:
    """
    Advanced implementation of the Connectivity-Aware Graph Transformer.
    Maps logical surface code qubits to physical device qubits, respecting hardware connectivity.
    """
    def __init__(self, config: Dict[str, Any], hardware_graph: Dict[str, Any], native_gates: list, 
                 gate_error_rates: Dict[str, float], qubit_error_rates: Dict[int, float]):
        self.config = config
        self.hardware_graph = hardware_graph
        self.native_gates = native_gates
        self.gate_error_rates = gate_error_rates
        self.qubit_error_rates = qubit_error_rates
        
        # Extract configuration settings
        self.mapping_strategy = config.get('mapping_heuristic', 'greedy')
        self.advanced_constraints = config.get('advanced_constraints', {})
        self.excluded_qubits = self.advanced_constraints.get('exclude_qubits', [])
        self.max_error_rate = self.advanced_constraints.get('max_error_rate', 1.0)
        
        # Hardware-specific settings
        self.topology_type = hardware_graph.get('topology_type', 'unknown')
        
        # Logging
        self.verbose = config.get('system', {}).get('log_level', 'INFO') == 'DEBUG'

    def transform(self, surface_code_object: SurfaceCodeObject) -> Dict[str, Any]:
        """
        Transform an ideal surface code layout into a hardware-aware mapping.
        
        Args:
            surface_code_object: SurfaceCodeObject containing the ideal surface code layout
            
        Returns:
            Dictionary containing the transformed layout and related information
        """
        # Validate the surface code object
        self._validate_surface_code(surface_code_object)
        
        # Parse hardware coupling map
        hw_graph = self._parse_hardware_graph()
        
        # Map logical qubits to physical qubits using the selected strategy
        mapping = self._select_mapping_strategy(surface_code_object, hw_graph)
        
        # If mapping failed completely, raise an error
        if not mapping:
            raise RuntimeError("Failed to map surface code to hardware graph - no valid mapping found")
        
        # Remap stabilizers and logical ops
        hardware_stabilizer_map = self._remap_stabilizers(surface_code_object.stabilizer_map, mapping)
        logical_operators = self._remap_logical_operators(surface_code_object.logical_operators, mapping)
        
        # Calculate connectivity overhead (SWAPs, delays, cost)
        connectivity_overhead_info = self._compute_connectivity_overhead(hw_graph, mapping, surface_code_object)
        
        # Create an annotated graph with performance metrics
        annotated_graph = self._create_annotated_graph(hw_graph, mapping, surface_code_object)
        
        return {
            'surface_code': surface_code_object,
            'transformed_layout': mapping,
            'hardware_stabilizer_map': hardware_stabilizer_map,
            'logical_operators': logical_operators,
            'connectivity_overhead_info': connectivity_overhead_info,
            'annotated_graph': annotated_graph,
            'hardware_info': {
                'topology_type': self.topology_type,
                'native_gates': self.native_gates,
                'gate_error_rates': self.gate_error_rates
            }
        }

    def _validate_surface_code(self, surface_code_object: SurfaceCodeObject) -> None:
        """Validate the surface code object before transformation."""
        try:
            surface_code_object.validate()
        except Exception as e:
            raise ValueError(f"SurfaceCodeObject validation failed before graph transformation: {str(e)}")
        
        # Check hardware compatibility
        max_qubits = len(surface_code_object.qubit_layout)
        device_max_qubits = self.hardware_graph.get('device_limits', {}).get('max_qubits', float('inf'))
        
        if max_qubits > device_max_qubits:
            raise ValueError(f"Surface code requires {max_qubits} qubits, but device only supports {device_max_qubits}")

    def _parse_hardware_graph(self) -> nx.Graph:
        """Parse the hardware connectivity into a NetworkX graph."""
        G = nx.Graph()
        
        # Add nodes with error rates
        for q_str, properties in self.hardware_graph.get('qubit_properties', {}).items():
            q = int(q_str)
            if q not in self.excluded_qubits:
                error_rate = properties.get('readout_error', 0.0)
                if error_rate <= self.max_error_rate:
                    G.add_node(q, error_rate=error_rate)
        
        # Add edges
        connectivity = self.hardware_graph.get('qubit_connectivity', {})
        for q1_str, neighbors in connectivity.items():
            q1 = int(q1_str)
            if q1 in G:
                for q2_str in neighbors:
                    q2 = int(q2_str)
                    if q2 in G:
                        # Add edge weight based on gate error rates
                        gate_error = self.gate_error_rates.get('cx', 0.01)
                        G.add_edge(q1, q2, weight=gate_error)
        
        return G

    def _select_mapping_strategy(self, surface_code: SurfaceCodeObject, hw_graph: nx.Graph) -> Dict[int, int]:
        """Select and apply the appropriate mapping strategy based on configuration."""
        if self.mapping_strategy == 'greedy':
            return self._greedy_mapping(surface_code, hw_graph)
        elif self.mapping_strategy == 'noise_aware':
            return self._noise_aware_mapping(surface_code, hw_graph)
        else:
            # Default to simple mapping
            return self._simple_mapping(surface_code, hw_graph)

    def _simple_mapping(self, surface_code: SurfaceCodeObject, hw_graph: nx.Graph) -> Dict[int, int]:
        """Simple identity mapping (for testing or small devices)."""
        mapping = {}
        sc_qubits = list(surface_code.qubit_layout.keys())
        hw_qubits = list(hw_graph.nodes())
        
        # Map as many qubits as possible
        for i, sc_q in enumerate(sc_qubits):
            if i < len(hw_qubits):
                mapping[sc_q] = hw_qubits[i]
            else:
                break
                
        return mapping

    def _greedy_mapping(self, surface_code: SurfaceCodeObject, hw_graph: nx.Graph) -> Dict[int, int]:
        """
        Greedy mapping algorithm that prioritizes high-connectivity qubits and
        tries to preserve adjacency relationships from the surface code.
        """
        # Create graph from surface code
        sc_graph = surface_code.adjacency_matrix if isinstance(surface_code.adjacency_matrix, nx.Graph) else nx.Graph()
        
        # If adjacency matrix is empty, create one from qubit layout
        if not sc_graph.edges():
            sc_graph = self._create_surface_code_graph(surface_code)
        
        # Sort both graphs' nodes by degree (connectivity)
        sc_nodes = sorted(sc_graph.nodes(), key=lambda n: sc_graph.degree(n), reverse=True)
        hw_nodes = sorted(hw_graph.nodes(), key=lambda n: hw_graph.degree(n), reverse=True)
        
        # Initial mapping for highest-degree nodes
        mapping = {}
        mapped_hw_nodes = set()
        
        # First pass: map highest-degree nodes to highest-degree hardware nodes
        for sc_node in sc_nodes:
            for hw_node in hw_nodes:
                if hw_node not in mapped_hw_nodes:
                    # Check if error rate is acceptable
                    error_rate = hw_graph.nodes[hw_node].get('error_rate', 0.0)
                    if error_rate <= self.max_error_rate and hw_node not in self.excluded_qubits:
                        mapping[sc_node] = hw_node
                        mapped_hw_nodes.add(hw_node)
                        break
        
        # Second pass: try to preserve adjacency
        return self._optimize_adjacency(sc_graph, hw_graph, mapping)

    def _noise_aware_mapping(self, surface_code: SurfaceCodeObject, hw_graph: nx.Graph) -> Dict[int, int]:
        """
        Noise-aware mapping that considers qubit and gate error rates.
        Prioritizes mapping data qubits to low-error hardware qubits.
        """
        # Identify data and ancilla qubits
        data_qubits = [q for q, info in surface_code.qubit_layout.items() 
                      if info.get('type') == 'data']
        ancilla_qubits = [q for q, info in surface_code.qubit_layout.items() 
                         if info.get('type', '').startswith('ancilla')]
        
        # Sort hardware qubits by error rate
        hw_qubits = sorted(hw_graph.nodes(), 
                          key=lambda n: hw_graph.nodes[n].get('error_rate', 1.0))
        
        # Remove excluded qubits and high-error qubits
        hw_qubits = [q for q in hw_qubits if q not in self.excluded_qubits and 
                    hw_graph.nodes[q].get('error_rate', 1.0) <= self.max_error_rate]
        
        # Initialize mapping
        mapping = {}
        
        # First map data qubits to lowest-error hardware qubits
        for i, q in enumerate(data_qubits):
            if i < len(hw_qubits):
                mapping[q] = hw_qubits[i]
        
        # Then map ancilla qubits to remaining hardware qubits
        hw_qubits = [q for q in hw_qubits if q not in mapping.values()]
        for i, q in enumerate(ancilla_qubits):
            if i < len(hw_qubits):
                mapping[q] = hw_qubits[i]
        
        # Now optimize for connectivity
        sc_graph = self._create_surface_code_graph(surface_code)
        return self._optimize_adjacency(sc_graph, hw_graph, mapping)

    def _create_surface_code_graph(self, surface_code: SurfaceCodeObject) -> nx.Graph:
        """Create a NetworkX graph from the surface code object."""
        G = nx.Graph()
        
        # Add all qubits as nodes
        for q, info in surface_code.qubit_layout.items():
            G.add_node(q, **info)
        
        # Connect data qubits to their associated stabilizer ancillas
        for stab_type, stabilizers in surface_code.stabilizer_map.items():
            if isinstance(stabilizers, list):
                # Handle both formats of stabilizer maps
                if stabilizers and isinstance(stabilizers[0], dict):
                    # New format with dict entries
                    for stab in stabilizers:
                        ancilla = stab.get('ancilla')
                        data_qubits = stab.get('data_qubits', [])
                        if ancilla is not None and data_qubits:
                            for data_q in data_qubits:
                                G.add_edge(ancilla, data_q)
                else:
                    # Old format with just ancilla indices
                    for ancilla in stabilizers:
                        # Find nearby data qubits based on coordinates
                        ancilla_info = surface_code.qubit_layout.get(ancilla, {})
                        if ancilla_info and 'x' in ancilla_info and 'y' in ancilla_info:
                            ax, ay = ancilla_info['x'], ancilla_info['y']
                            # Connect to data qubits within a radius
                            for q, info in surface_code.qubit_layout.items():
                                if info.get('type') == 'data' and 'x' in info and 'y' in info:
                                    dx, dy = info['x'], info['y']
                                    dist = ((ax - dx) ** 2 + (ay - dy) ** 2) ** 0.5
                                    if dist < 1.0:  # Threshold distance
                                        G.add_edge(ancilla, q)
        
        return G

    def _optimize_adjacency(self, sc_graph: nx.Graph, hw_graph: nx.Graph, 
                           initial_mapping: Dict[int, int]) -> Dict[int, int]:
        """
        Optimize the mapping to better preserve adjacency relationships.
        Uses a simple local search algorithm to reduce the number of broken edges.
        """
        mapping = initial_mapping.copy()
        mapped_hw_nodes = set(mapping.values())
        available_hw_nodes = set(hw_graph.nodes()) - mapped_hw_nodes
        
        # Remove excluded and high-error qubits from available nodes
        available_hw_nodes = {n for n in available_hw_nodes if n not in self.excluded_qubits and 
                            hw_graph.nodes[n].get('error_rate', 1.0) <= self.max_error_rate}
        
        # Calculate initial broken edges count
        broken_edges = self._count_broken_edges(sc_graph, hw_graph, mapping)
        
        # Local search iterations (limited to ensure we don't get stuck)
        max_iterations = 20
        iterations = 0
        improved = True
        
        while improved and iterations < max_iterations:
            improved = False
            iterations += 1
            
            # Try swapping each pair of qubits
            for sc_node1 in mapping:
                best_swap = None
                best_improvement = 0
                
                # Try swapping with another mapped node
                for sc_node2 in mapping:
                    if sc_node1 != sc_node2:
                        # Swap mapping temporarily
                        mapping[sc_node1], mapping[sc_node2] = mapping[sc_node2], mapping[sc_node1]
                        new_broken = self._count_broken_edges(sc_graph, hw_graph, mapping)
                        improvement = broken_edges - new_broken
                        
                        if improvement > best_improvement:
                            best_improvement = improvement
                            best_swap = ('mapped', sc_node2)
                        
                        # Revert swap
                        mapping[sc_node1], mapping[sc_node2] = mapping[sc_node2], mapping[sc_node1]
                
                # Apply the best swap if it improves the mapping
                if best_swap and best_improvement > 0:
                    sc_node2 = best_swap[1]
                    mapping[sc_node1], mapping[sc_node2] = mapping[sc_node2], mapping[sc_node1]
                    broken_edges -= best_improvement
                    improved = True
        
        return mapping

    def _count_broken_edges(self, sc_graph: nx.Graph, hw_graph: nx.Graph, 
                           mapping: Dict[int, int]) -> int:
        """Count the number of edges in the surface code that aren't preserved in hardware."""
        broken = 0
        for sc_u, sc_v in sc_graph.edges():
            if sc_u in mapping and sc_v in mapping:
                hw_u, hw_v = mapping[sc_u], mapping[sc_v]
                if not hw_graph.has_edge(hw_u, hw_v):
                    broken += 1
        return broken

    def _remap_stabilizers(self, stabilizer_map: Dict[str, Any], 
                          mapping: Dict[int, int]) -> Dict[str, Any]:
        """Remap stabilizers from logical to physical qubits."""
        remapped = {'X': [], 'Z': []}
        
        for stab_type, stabilizers in stabilizer_map.items():
            if isinstance(stabilizers, list):
                # Handle both formats of stabilizer maps
                if stabilizers and isinstance(stabilizers[0], dict):
                    # New format with dict entries
                    for stab in stabilizers:
                        ancilla = stab.get('ancilla')
                        data_qubits = stab.get('data_qubits', [])
                        
                        if ancilla in mapping:
                            remapped_stab = {
                                'ancilla': mapping[ancilla],
                                'data_qubits': [mapping[q] for q in data_qubits if q in mapping],
                                'weight': len([q for q in data_qubits if q in mapping]),
                            }
                            if 'coordinates' in stab:
                                remapped_stab['coordinates'] = stab['coordinates']
                            
                            # Only add if we have mapped data qubits
                            if remapped_stab['data_qubits']:
                                remapped[stab_type].append(remapped_stab)
                else:
                    # Old format with just ancilla indices
                    for ancilla in stabilizers:
                        if ancilla in mapping:
                            remapped[stab_type].append(mapping[ancilla])
        
        return remapped

    def _remap_logical_operators(self, logical_operators: Dict[str, List[int]], 
                               mapping: Dict[int, int]) -> Dict[str, List[int]]:
        """Remap logical operators from logical to physical qubits."""
        remapped = {}
        for op_type, qubits in logical_operators.items():
            remapped[op_type] = [mapping[q] for q in qubits if q in mapping]
        return remapped

    def _compute_connectivity_overhead(self, hw_graph: nx.Graph, mapping: Dict[int, int], 
                                     surface_code: SurfaceCodeObject) -> Dict[str, Any]:
        """
        Compute the connectivity overhead of the mapping.
        
        This includes:
        - The number of SWAPs required
        - Circuit depth increase
        - Gate error impact
        """
        # Create a graph from the surface code
        sc_graph = self._create_surface_code_graph(surface_code)
        
        # Count broken edges (each broken edge requires a SWAP)
        broken_edges = self._count_broken_edges(sc_graph, hw_graph, mapping)
        
        # Estimate SWAP overhead based on device topology
        swap_overhead = {
            'heavy-hex': 2.5,  # IBM heavy-hex requires more SWAPs on average
            'all-to-all': 0,   # No SWAPs needed for all-to-all
            'square': 1.5      # Square grid is in between
        }.get(self.topology_type, 2.0)  # Default overhead
        
        # Total SWAPs required
        swaps = int(broken_edges * swap_overhead)
        
        # Estimate depth increase (each SWAP adds ~3 depth)
        depth_increase = swaps * 3
        
        # Estimate error rate impact (each SWAP adds gate errors)
        swap_error = 3 * self.gate_error_rates.get('cx', 0.01)  # SWAP = 3 CX gates
        error_increase = swaps * swap_error
        
        return {
            'SWAPs': swaps,
            'depth_increase': depth_increase,
            'error_increase': error_increase,
            'broken_edges': broken_edges,
            'swap_overhead_factor': swap_overhead
        }

    def _create_annotated_graph(self, hw_graph: nx.Graph, mapping: Dict[int, int], 
                              surface_code: SurfaceCodeObject) -> nx.Graph:
        """
        Create an annotated graph with mapping and performance information.
        
        This can be used for visualization and further analysis.
        """
        # Create a copy of the hardware graph
        G = hw_graph.copy()
        
        # Add surface code qubit type information to nodes
        for sc_q, hw_q in mapping.items():
            if hw_q in G.nodes:
                sc_info = surface_code.qubit_layout.get(sc_q, {})
                G.nodes[hw_q]['sc_qubit'] = sc_q
                G.nodes[hw_q]['qubit_type'] = sc_info.get('type', 'unknown')
                G.nodes[hw_q]['original_x'] = sc_info.get('x', 0)
                G.nodes[hw_q]['original_y'] = sc_info.get('y', 0)
        
        # Add edge properties
        for u, v in G.edges():
            # Mark edges used by surface code
            used = False
            for sc_u, hw_u in mapping.items():
                if hw_u == u:
                    for sc_v, hw_v in mapping.items():
                        if hw_v == v:
                            # Check if these qubits are connected in the surface code
                            sc_graph = self._create_surface_code_graph(surface_code)
                            if sc_graph.has_edge(sc_u, sc_v):
                                used = True
                                break
            G.edges[u, v]['used'] = used
            G.edges[u, v]['gate_error'] = self.gate_error_rates.get('cx', 0.01)
        
        return G 