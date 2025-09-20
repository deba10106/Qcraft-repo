from typing import Dict, Any, List, Tuple, Optional, Union
import networkx as nx
import numpy as np

class SurfaceCodeObject:
    """
    Object representation of a surface code.
    Stores the layout, stabilizer map, logical operators, supported logical gates, and can validate itself for correctness.
    """
    def __init__(self, qubit_layout: Dict[int, Dict[str, Any]], 
                stabilizer_map: Dict[str, List], 
                logical_operators: Dict[str, List[int]], 
                adjacency_matrix: nx.Graph,
        code_distance: int,
        layout_type: str,
        grid_connectivity: str = None,
        topology_type: str = None,
        supported_logical_gates: list = None):
        """
        Initialize the surface code object.
        
        Args:
            qubit_layout: Dictionary mapping qubit indices to their properties
            stabilizer_map: Dictionary mapping stabilizer types to lists of stabilizers
            logical_operators: Dictionary mapping logical operator types to lists of qubit indices
            adjacency_matrix: NetworkX graph representing qubit connectivity
            code_distance: Distance of the surface code
            layout_type: Type of surface code layout ('planar', 'rotated', 'color')
            grid_connectivity: Type of grid connectivity ('square', 'heavy-hex', etc.)
            topology_type: Device topology type (used as fallback for grid_connectivity)
        """
        self.qubit_layout = qubit_layout
        self.stabilizer_map = stabilizer_map
        self.logical_operators = logical_operators
        self.adjacency_matrix = adjacency_matrix
        self.code_distance = code_distance
        self.layout_type = layout_type
        # Prefer explicit grid_connectivity, else topology_type, else 'unknown'
        self.grid_connectivity = grid_connectivity if grid_connectivity is not None else (topology_type if topology_type is not None else 'unknown')
        self.supported_logical_gates = supported_logical_gates if supported_logical_gates is not None else []
        # Validate the surface code
        self.is_valid = self.validate(raise_error=False)

    def validate(self, raise_error: bool = True) -> bool:
        """
        Validate the surface code for correctness, including advanced color code support.
        Args:
            raise_error: Whether to raise an error if validation fails
        Returns:
            True if the surface code is valid, False otherwise
        """
        try:
            # Validate qubit layout
            if not self.qubit_layout:
                raise ValueError("Qubit layout is empty")
            # Check that each qubit has required properties
            for q, info in self.qubit_layout.items():
                if 'x' not in info or 'y' not in info:
                    raise ValueError(f"Qubit {q} is missing coordinate information")
                if 'type' not in info:
                    raise ValueError(f"Qubit {q} is missing type information")
            # Validate stabilizer map
            if not self.stabilizer_map:
                raise ValueError("Stabilizer map is empty")
            # Check that the stabilizer map has X and Z stabilizers (and for color code, check 3-colorability)
            if self.layout_type == 'color':
                if 'X' not in self.stabilizer_map or 'Z' not in self.stabilizer_map:
                    raise ValueError("Color code stabilizer map must have both X and Z stabilizers")
                # Advanced: check that each ancilla acts on 3 or 6 data qubits (triangle/hex)
                for stab_type in ['X', 'Z']:
                    for stab in self.stabilizer_map.get(stab_type, []):
                        dq = stab.get('data_qubits', [])
                        if len(dq) not in (3, 6):
                            raise ValueError(f"Color code {stab_type} stabilizer on ancilla {stab.get('ancilla')} has {len(dq)} data qubits (expected 3 or 6)")
            else:
                if 'X' not in self.stabilizer_map or 'Z' not in self.stabilizer_map:
                    raise ValueError("Stabilizer map must have both X and Z stabilizers")
            # Validate logical operators
            if not self.logical_operators:
                raise ValueError("Logical operators are empty")
            # Check that the logical operators have X and Z operators
            if 'X' not in self.logical_operators or 'Z' not in self.logical_operators:
                raise ValueError("Logical operators must have both X and Z operators")
            # Validate adjacency matrix
            if not self.adjacency_matrix or self.adjacency_matrix.number_of_nodes() == 0:
                raise ValueError("Adjacency matrix is empty")
            # Check that all qubits in the layout are in the adjacency matrix
            for q in self.qubit_layout:
                if q not in self.adjacency_matrix.nodes():
                    raise ValueError(f"Qubit {q} is in the layout but not in the adjacency matrix")
            # Validate code distance
            if self.code_distance < 3:
                raise ValueError(f"Code distance must be at least 3, got {self.code_distance}")
            # Validate layout type
            valid_layouts = ['planar', 'rotated', 'color']
            if self.layout_type not in valid_layouts:
                raise ValueError(f"Layout type must be one of {valid_layouts}, got {self.layout_type}")
            # Advanced: for color code, check 3-colorability of the adjacency matrix
            if self.layout_type == 'color':
                try:
                    import networkx as nx
                    coloring = nx.coloring.greedy_color(self.adjacency_matrix, strategy='largest_first')
                    if len(set(coloring.values())) < 3:
                        raise ValueError("Color code adjacency matrix is not 3-colorable (found less than 3 colors)")
                except Exception as e:
                    if raise_error:
                        raise ValueError(f"Failed 3-colorability check: {e}")
            return True
        except ValueError as e:
            if raise_error:
                raise
            print(f"Surface code validation failed: {str(e)}")
            return False

    def get_data_qubits(self) -> List[int]:
        """
        Get the indices of all data qubits.
        
        Returns:
            List of data qubit indices
        """
        return [q for q, info in self.qubit_layout.items() if info.get('type') == 'data']

    def get_ancilla_qubits(self, stab_type: Optional[str] = None) -> List[int]:
        """
        Get the indices of all ancilla qubits.
        
        Args:
            stab_type: Type of stabilizer ('X' or 'Z'). If None, returns all ancilla qubits.
            
        Returns:
            List of ancilla qubit indices
        """
        if stab_type is None:
            return [q for q, info in self.qubit_layout.items() if info.get('type', '').startswith('ancilla')]
        else:
            return [q for q, info in self.qubit_layout.items() if info.get('type') == f'ancilla_{stab_type}']

    def get_stabilizer_qubits(self, stab_type: str) -> Dict[int, List[int]]:
        """
        Get the mapping from stabilizer ancillas to their data qubits.
        
        Args:
            stab_type: Type of stabilizer ('X' or 'Z')
            
        Returns:
            Dictionary mapping ancilla indices to lists of data qubit indices
        """
        result = {}
        
        # Check if the stabilizer map has the new format (with data_qubits)
        stabilizers = self.stabilizer_map.get(stab_type, [])
        if stabilizers and isinstance(stabilizers[0], dict):
            # New format
            for stab in stabilizers:
                ancilla = stab.get('ancilla')
                data_qubits = stab.get('data_qubits', [])
                if ancilla is not None:
                    result[ancilla] = data_qubits
        else:
            # Old format - need to infer data qubits from adjacency
            for ancilla in stabilizers:
                # Get the type of the ancilla
                ancilla_type = self.qubit_layout.get(ancilla, {}).get('type', '')
                if ancilla_type == f'ancilla_{stab_type}':
                    # Find connected data qubits
                    data_qubits = []
                    for neighbor in self.adjacency_matrix.neighbors(ancilla):
                        if self.qubit_layout.get(neighbor, {}).get('type') == 'data':
                            data_qubits.append(neighbor)
                    result[ancilla] = data_qubits
        
        return result

    def visualize(self, show_stabilizers: bool = True):
        """
        Visualize the surface code layout.
        
        Args:
            show_stabilizers: Whether to show stabilizer connections
        """
        import matplotlib.pyplot as plt
        
        # Extract coordinates for different qubit types
        data_x, data_y = [], []
        ancilla_x_x, ancilla_x_y = [], []
        ancilla_z_x, ancilla_z_y = [], []
        
        for q, info in self.qubit_layout.items():
            x, y = info.get('x', 0), info.get('y', 0)
            qtype = info.get('type', '')
            
            if qtype == 'data':
                data_x.append(x)
                data_y.append(y)
            elif qtype == 'ancilla_X':
                ancilla_x_x.append(x)
                ancilla_x_y.append(y)
            elif qtype == 'ancilla_Z':
                ancilla_z_x.append(x)
                ancilla_z_y.append(y)
        
        # Create figure
        plt.figure(figsize=(10, 8))
        
        # Plot qubits
        plt.scatter(data_x, data_y, c='blue', marker='o', s=100, label='Data Qubits')
        plt.scatter(ancilla_x_x, ancilla_x_y, c='green', marker='x', s=80, label='X Stabilizers')
        plt.scatter(ancilla_z_x, ancilla_z_y, c='red', marker='s', s=80, label='Z Stabilizers')
        
        # Add qubit labels
        for q, info in self.qubit_layout.items():
            plt.text(info.get('x', 0), info.get('y', 0), str(q), fontsize=8, ha='center', va='center')
        
        # Draw stabilizer connections
        if show_stabilizers:
            # X stabilizers
            x_stabs = self.get_stabilizer_qubits('X')
            for ancilla, data_qubits in x_stabs.items():
                ax, ay = self.qubit_layout.get(ancilla, {}).get('x', 0), self.qubit_layout.get(ancilla, {}).get('y', 0)
                for data_q in data_qubits:
                    dx, dy = self.qubit_layout.get(data_q, {}).get('x', 0), self.qubit_layout.get(data_q, {}).get('y', 0)
                    plt.plot([ax, dx], [ay, dy], 'g-', alpha=0.5)
            
            # Z stabilizers
            z_stabs = self.get_stabilizer_qubits('Z')
            for ancilla, data_qubits in z_stabs.items():
                ax, ay = self.qubit_layout.get(ancilla, {}).get('x', 0), self.qubit_layout.get(ancilla, {}).get('y', 0)
                for data_q in data_qubits:
                    dx, dy = self.qubit_layout.get(data_q, {}).get('x', 0), self.qubit_layout.get(data_q, {}).get('y', 0)
                    plt.plot([ax, dx], [ay, dy], 'r-', alpha=0.5)
        
        # Highlight logical operators
        logical_x = self.logical_operators.get('X', [])
        logical_z = self.logical_operators.get('Z', [])
        
        x_coords = [(self.qubit_layout.get(q, {}).get('x', 0), self.qubit_layout.get(q, {}).get('y', 0)) for q in logical_x]
        z_coords = [(self.qubit_layout.get(q, {}).get('x', 0), self.qubit_layout.get(q, {}).get('y', 0)) for q in logical_z]
        
        if x_coords:
            x_x, x_y = zip(*x_coords)
            plt.scatter(x_x, x_y, c='green', marker='o', s=150, alpha=0.5, edgecolors='black', label='Logical X')
        
        if z_coords:
            z_x, z_y = zip(*z_coords)
            plt.scatter(z_x, z_y, c='red', marker='o', s=150, alpha=0.5, edgecolors='black', label='Logical Z')
        
        # Add title and labels
        plt.title(f"Surface Code: {self.layout_type}, d={self.code_distance}")
        plt.xlabel('x')
        plt.ylabel('y')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.axis('equal')
        plt.tight_layout()
        plt.show()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the surface code object to a dictionary.
        
        Returns:
            Dictionary representation of the surface code
        """
        # Convert adjacency matrix to edge list
        edges = list(self.adjacency_matrix.edges())
        
        return {
            'qubit_layout': self.qubit_layout,
            'stabilizer_map': self.stabilizer_map,
            'logical_operators': self.logical_operators,
            'edges': edges,
            'code_distance': self.code_distance,
            'layout_type': self.layout_type,
            'grid_connectivity': self.grid_connectivity,
            'supported_logical_gates': self.supported_logical_gates
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        Create a surface code object from a dictionary.
        
        Args:
            data: Dictionary representation of the surface code
            
        Returns:
            SurfaceCodeObject instance
        """
        # Reconstruct adjacency matrix
        adjacency_matrix = nx.Graph()
        for q, info in data.get('qubit_layout', {}).items():
            adjacency_matrix.add_node(q, **info)
        
        for u, v in data.get('edges', []):
            adjacency_matrix.add_edge(u, v)
        
        return cls(
            qubit_layout=data.get('qubit_layout', {}),
            stabilizer_map=data.get('stabilizer_map', {'X': [], 'Z': []}),
            logical_operators=data.get('logical_operators', {'X': [], 'Z': []}),
            adjacency_matrix=adjacency_matrix,
            code_distance=data.get('code_distance', 3),
            layout_type=data.get('layout_type', 'planar'),
            grid_connectivity=data.get('grid_connectivity', 'unknown'),
            topology_type=data.get('topology_type'),
            supported_logical_gates=data.get('supported_logical_gates', [])
        )

    def to_stim_circuit(self, mapping, noise_model):
        """
        Build a stim.Circuit for this surface code object, using the logical-to-physical mapping and noise model.
        Args:
            mapping: logical_to_physical mapping dict
            noise_model: dict describing noise (e.g., {'p': 0.001})
        Returns:
            stim.Circuit instance
        """
        import stim
        p = noise_model.get('p', 0.001) if noise_model else 0.001
        circuit = stim.Circuit()
        # Map logical to physical qubits
        qubit_map = mapping if mapping else {q: q for q in self.qubit_layout}
        # Add noise to all physical qubits
        for q in qubit_map.values():
            circuit.append_operation("DEPOLARIZE1", [q], p)
        # For each stabilizer round, measure all stabilizers
        for stab_type in ['X', 'Z']:
            for stab in self.stabilizer_map.get(stab_type, []):
                anc = qubit_map[stab['ancilla']]
                data = [qubit_map[q] for q in stab['data_qubits']]
                # Prepare ancilla in |+> or |0> depending on X or Z
                if stab_type == 'X':
                    circuit.append_operation("H", [anc])
                # CNOTs: data -> ancilla (X: CNOT, Z: CNOT with H)
                for dq in data:
                    if stab_type == 'X':
                        circuit.append_operation("CNOT", [dq, anc])
                    else:
                        circuit.append_operation("CNOT", [anc, dq])
                # Measure ancilla
                circuit.append_operation("M", [anc])
                # Reset ancilla (optional, for repeated rounds)
                circuit.append_operation("R", [anc])
        # Measure all data qubits at the end (for logical operator detection)
        data_qubits = [qubit_map[q] for q in self.get_data_qubits()]
        circuit.append_operation("M", data_qubits)
        return circuit 