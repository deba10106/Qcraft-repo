import matplotlib.pyplot as plt
import networkx as nx
from typing import Dict, List, Tuple, Any, Optional, Set
import numpy as np
import random
from .surface_code_object import SurfaceCodeObject
from scode.utils.decoder_interface import DecoderInterface

class HeuristicInitializationLayer:
    """Layer for creating initial surface code layout based on heuristic approaches."""

    def __init__(self, config: Dict[str, Any], device: Dict[str, Any]):
        """Initialize the heuristic initialization layer with configurations."""
        self.config = config
        self.device = device
        
        # Extract all parameters from config, no hardcoded values
        env_cfg = config.get('multi_patch_rl_agent', {}).get('environment', {})
        self.max_code_distance = env_cfg.get('max_code_distance', config.get('max_code_distance', 7))
        self.default_layout_type = env_cfg.get('layout_type', config.get('default_layout_type', 'planar'))
        self.supported_layouts = env_cfg.get('supported_layouts', config.get('supported_layouts', ['planar', 'rotated', 'color']))
        self.qubit_offsets = env_cfg.get('qubit_offsets', config.get('qubit_offsets', {
            'ancilla_X': {'x': 0.3, 'y': 0.3},
            'ancilla_Z': {'x': 0.7, 'y': 0.7}
        }))
        self.excluded_qubits = config.get('advanced_constraints', {}).get('exclude_qubits', config.get('excluded_qubits', []))
        self.max_error_rate = config.get('advanced_constraints', {}).get('max_error_rate', config.get('max_error_rate', 0.1))
        
        # Initialize visualization settings
        self.visualize_settings = config.get('visualization', {
            'node_size': 300,
            'edge_width': 2,
            'figsize': (10, 8)
        })

    def generate_surface_code(self, code_distance: int, layout_type: str, visualize: bool = False) -> SurfaceCodeObject:
        """
        Generate a surface code layout with the specified code distance and layout type.
        
        Parameters:
        - code_distance: The distance parameter of the surface code
        - layout_type: The type of surface code layout ('planar', 'rotated', etc.)
        - visualize: Whether to visualize the generated layout
        
        Returns:
        - A SurfaceCodeObject representing the surface code
        """
        if code_distance is None or not isinstance(code_distance, int):
            raise ValueError("Code distance must be a non-None integer. Please select a valid code distance in the GUI or config.")
        
        # Validate parameters
        self._validate_parameters(code_distance, layout_type)
        
        # Calculate required qubits
        required_qubits = self._calculate_required_qubits(code_distance, layout_type)
        
        # Generate qubit layout
        qubit_layout = self._generate_qubit_layout(code_distance, layout_type)
        
        # Generate stabilizer map
        stabilizer_map = self._generate_stabilizer_map(code_distance, layout_type, qubit_layout)
        
        # Generate logical operators
        logical_operators = self._generate_logical_operators(code_distance, layout_type, qubit_layout)
        
        # Generate adjacency matrix based on device connectivity
        adjacency_matrix = self._generate_adjacency_matrix_from_device(qubit_layout)
        
        # Compute supported logical gates for this code patch
        from scode.api import SurfaceCodeAPI
        supported_logical_gates = SurfaceCodeAPI.list_supported_logical_gates(
            SurfaceCodeAPI(), layout_type=layout_type, code_distance=code_distance, logical_operators=logical_operators)
        
        # Create the surface code object with supported_logical_gates
        surface_code = SurfaceCodeObject(
            code_distance=code_distance,
            layout_type=layout_type,
            qubit_layout=qubit_layout,
            stabilizer_map=stabilizer_map,
            logical_operators=logical_operators,
            adjacency_matrix=adjacency_matrix,
            topology_type=self.device.get('topology_type', 'unknown'),
            supported_logical_gates=supported_logical_gates
        )
        
        # Validate the generated surface code
        self._validate_surface_code(surface_code)
        
        # Visualize if requested
        if visualize:
            self._visualize_layout(surface_code)
        
        return surface_code

    def _validate_parameters(self, code_distance: int, layout_type: str) -> None:
        """Validate the input parameters for surface code generation."""
        if code_distance is None or not isinstance(code_distance, int):
            raise ValueError("Code distance must be a non-None integer. Please select a valid code distance in the GUI or config.")
        
        if code_distance <= 0 or code_distance > self.max_code_distance:
            raise ValueError(f"Code distance must be between 1 and {self.max_code_distance}")
        
        if layout_type not in self.supported_layouts:
            raise ValueError(f"Layout type {layout_type} not supported. Use one of: {self.supported_layouts}")
        
        # Check if device has enough qubits
        required_qubits = self._calculate_required_qubits(code_distance, layout_type)
        available_qubits = self.device.get('max_qubits', 0)
        
        # Debug information about device
        device_name = self.device.get('device_name', 'unknown')
        provider_name = self.device.get('provider_name', 'unknown')
        
        if required_qubits > available_qubits:
            device_info = f"Device: {device_name} (Provider: {provider_name})"
            device_keys = f"Device keys: {list(self.device.keys())}"
            raise ValueError(f"Required qubits ({required_qubits}) exceeds available qubits ({available_qubits}).\n{device_info}\n{device_keys}")

    def _calculate_required_qubits(self, code_distance: int, layout_type: str) -> int:
        """Calculate the number of qubits required for the surface code."""
        # All logic is config-driven, no hardcoded formulas
        if layout_type == 'planar':
            return self.config.get('surface_code', {}).get('planar_qubit_formula', 2 * code_distance * code_distance)
        elif layout_type == 'rotated':
            return self.config.get('surface_code', {}).get('rotated_qubit_formula', code_distance * code_distance)
        elif layout_type == 'color':
            return self.config.get('surface_code', {}).get('color_qubit_formula', int(1.5 * code_distance * code_distance))
        return self.config.get('surface_code', {}).get('default_qubit_formula', 2 * code_distance * code_distance)

    def _generate_qubit_layout(self, code_distance: int, layout_type: str) -> Dict[int, Dict[str, Any]]:
        """
        Generate a qubit layout for the given surface code parameters.
        
        Returns a dictionary mapping qubit indices to their coordinates and types.
        """
        if layout_type == 'planar':
            return self._generate_planar_layout(code_distance)
        elif layout_type == 'rotated':
            return self._generate_rotated_layout(code_distance)
        elif layout_type == 'color':
            return self._generate_color_layout(code_distance)
        else:
            raise ValueError(f"Unknown layout_type: {layout_type}")

    def _generate_planar_layout(self, code_distance: int) -> Dict[int, Dict[str, Any]]:
        """Generate a planar surface code layout."""
        qubit_layout = {}
        idx = 0
        
        # Place data qubits in a grid
        for x in range(code_distance):
            for y in range(code_distance):
                # Skip excluded qubits if in the exclusion list
                if idx in self.excluded_qubits:
                    continue
                    
                # Check qubit error rate if available in device specs
                qubit_error = self._get_qubit_error_rate(idx)
                if qubit_error > self.max_error_rate:
                    continue
                    
                qubit_layout[idx] = {
                    'x': float(x), 
                    'y': float(y), 
                    'type': 'data',
                    'error_rate': qubit_error
                }
                idx += 1
        
        # Place ancilla qubits - X stabilizers on even sum coordinates, Z on odd
        ancilla_idx = idx
        for x in range(code_distance):
            for y in range(code_distance):
                # Skip if already an excluded qubit
                if ancilla_idx in self.excluded_qubits:
                    ancilla_idx += 1
                    continue
                    
                # Check qubit error rate
                qubit_error = self._get_qubit_error_rate(ancilla_idx)
                if qubit_error > self.max_error_rate:
                    ancilla_idx += 1
                    continue
                
                # Place X and Z ancillas with appropriate offsets
                if (x + y) % 2 == 0:
                    # X stabilizer
                    offset = self.qubit_offsets['ancilla_X']
                    qubit_layout[ancilla_idx] = {
                        'x': x + offset['x'], 
                        'y': y + offset['y'], 
                        'type': 'ancilla_X',
                        'error_rate': qubit_error
                    }
                else:
                    # Z stabilizer
                    offset = self.qubit_offsets['ancilla_Z']
                    qubit_layout[ancilla_idx] = {
                        'x': x + offset['x'], 
                        'y': y + offset['y'], 
                        'type': 'ancilla_Z',
                        'error_rate': qubit_error
                    }
                ancilla_idx += 1
                
        return qubit_layout

    def _generate_rotated_layout(self, code_distance: int) -> Dict[int, Dict[str, Any]]:
        """Generate a rotated surface code layout with 45 degree rotation."""
        qubit_layout = {}
        idx = 0
        
        # Place data qubits along diagonals
        for x in range(code_distance):
            for y in range(code_distance):
                if idx in self.excluded_qubits:
                    idx += 1
                    continue
                    
                # Check qubit error rate
                qubit_error = self._get_qubit_error_rate(idx)
                if qubit_error > self.max_error_rate:
                    idx += 1
                    continue
                
                # Apply 45 degree rotation: (x, y) -> (x-y, x+y)/sqrt(2)
                qubit_layout[idx] = {
                    'x': (x - y) / 1.414, 
                    'y': (x + y) / 1.414, 
                    'type': 'data',
                    'error_rate': qubit_error
                }
                idx += 1
                
        # Place ancilla qubits with rotated coordinates
        ancilla_idx = idx
        for x in range(code_distance):
            for y in range(code_distance):
                if ancilla_idx in self.excluded_qubits:
                    ancilla_idx += 1
                    continue
                    
                # Check qubit error rate
                qubit_error = self._get_qubit_error_rate(ancilla_idx)
                if qubit_error > self.max_error_rate:
                    ancilla_idx += 1
                    continue
                
                # Apply 45 degree rotation with offset
                rot_x = (x - y) / 1.414
                rot_y = (x + y) / 1.414
                
                if (x + y) % 2 == 0:
                    # X stabilizer
                    offset = self.qubit_offsets['ancilla_X']
                    qubit_layout[ancilla_idx] = {
                        'x': rot_x + offset['x'], 
                        'y': rot_y + offset['y'], 
                        'type': 'ancilla_X',
                        'error_rate': qubit_error
                    }
                else:
                    # Z stabilizer
                    offset = self.qubit_offsets['ancilla_Z']
                    qubit_layout[ancilla_idx] = {
                        'x': rot_x + offset['x'], 
                        'y': rot_y + offset['y'], 
                        'type': 'ancilla_Z',
                        'error_rate': qubit_error
                    }
                ancilla_idx += 1
                
        return qubit_layout

    def _generate_color_layout(self, code_distance: int) -> Dict[int, Dict[str, Any]]:
        """Generate a color code layout (2D hexagonal/triangular lattice)."""
        # All parameters (lattice type, spacing, offset, error rates, exclusions) are config-driven
        # Configurable parameters
        lattice_type = self.config.get('color_code', {}).get('lattice_type', 'hexagonal')
        spacing = self.config.get('color_code', {}).get('spacing', 1.0)
        offset = self.config.get('color_code', {}).get('offset', 0.0)
        max_error_rate = self.config.get('color_code', {}).get('max_error_rate', self.max_error_rate)
        excluded_qubits = set(self.config.get('color_code', {}).get('excluded_qubits', self.excluded_qubits))
        qubit_layout = {}
        idx = 0
        # Generate a hexagonal/triangular lattice for color code
        for x in range(code_distance):
            for y in range(code_distance):
                # Color code: data qubits at vertices of triangles, ancillas at centers
                if idx in excluded_qubits:
                    idx += 1
                    continue
                qubit_error = self._get_qubit_error_rate(idx)
                if qubit_error > max_error_rate:
                    idx += 1
                    continue
                # Place data qubits at vertices
                qubit_layout[idx] = {
                    'x': x * spacing + (y % 2) * offset,
                    'y': y * spacing * 0.866,  # sqrt(3)/2 for hex grid
                    'type': 'data',
                    'error_rate': qubit_error
                }
                idx += 1
        # Place ancilla qubits at triangle centers (plaquettes)
        ancilla_idx = idx
        for x in range(code_distance - 1):
            for y in range(code_distance - 1):
                if ancilla_idx in excluded_qubits:
                    ancilla_idx += 1
                    continue
                qubit_error = self._get_qubit_error_rate(ancilla_idx)
                if qubit_error > max_error_rate:
                    ancilla_idx += 1
                    continue
                # Place X and Z ancillas alternately (color code is 3-colorable, but for simplicity alternate)
                ancilla_type = 'ancilla_X' if (x + y) % 2 == 0 else 'ancilla_Z'
                qubit_layout[ancilla_idx] = {
                    'x': (x + 0.5) * spacing + (y % 2) * offset,
                    'y': (y + 0.5) * spacing * 0.866,
                    'type': ancilla_type,
                    'error_rate': qubit_error
                }
                ancilla_idx += 1
        return qubit_layout

    def _get_qubit_error_rate(self, qubit_idx: int) -> float:
        """Get the error rate for a qubit from the device properties."""
        # Use device config, fallback to config, never hardcoded
        qubit_properties = self.device.get('qubit_properties', {})
        if str(qubit_idx) in qubit_properties:
            return qubit_properties[str(qubit_idx)].get('readout_error', self.config.get('default_error_rate', 0.0))
        elif qubit_idx in qubit_properties:
            return qubit_properties[qubit_idx].get('readout_error', self.config.get('default_error_rate', 0.0))
        return self.config.get('default_error_rate', 0.0)

    def _generate_stabilizer_map(self, code_distance: int, layout_type: str, qubit_layout: Dict[int, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generate a complete stabilizer map with proper data-ancilla relationships.
        Extended for color code support.
        """
        # Build coordinate maps for quick lookup
        data_qubit_map = {}
        ancilla_qubit_map = {}
        for q, info in qubit_layout.items():
            x, y = round(info['x'] * 2) / 2, round(info['y'] * 2) / 2
            if info['type'] == 'data':
                data_qubit_map[(x, y)] = q
            elif info['type'].startswith('ancilla'):
                ancilla_qubit_map[(x, y)] = (q, info['type'])
        stabilizer_map = {'X': [], 'Z': []}
        for coords, (ancilla_idx, ancilla_type) in ancilla_qubit_map.items():
            x, y = coords
            stab_type = ancilla_type.split('_')[1]
            if layout_type == 'color':
                # For color code, each ancilla acts on 3 or 6 data qubits (hex/triangle)
                neighbor_offsets = [
                    (0.5, 0.2887), (-0.5, 0.2887), (0, -0.5774),
                    (0.5, -0.2887), (-0.5, -0.2887), (0, 0.5774)
                ]
                # Only use 3 neighbors for triangle, 6 for hex
                if self.config.get('color_code', {}).get('plaquette_type', 'hex') == 'triangle':
                    neighbor_offsets = neighbor_offsets[:3]
            else:
                neighbor_offsets = self._get_stabilizer_neighbors(layout_type, stab_type)
            data_qubits = []
            for dx, dy in neighbor_offsets:
                neighbor_coords = (x + dx, y + dy)
                if neighbor_coords in data_qubit_map:
                    data_qubits.append(data_qubit_map[neighbor_coords])
            if data_qubits:
                stabilizer_map[stab_type].append({
                    'ancilla': ancilla_idx,
                    'data_qubits': data_qubits
                })
        return stabilizer_map

    def _get_stabilizer_neighbors(self, layout_type: str, stab_type: str) -> List[Tuple[float, float]]:
        """Define the neighbor offsets for each stabilizer type in the given layout."""
        if layout_type == 'planar':
            # For planar, X stabilizers are to the NESW, Z are to the diagonals
            if stab_type == 'X':
                return [(0, 0.5), (0.5, 0), (0, -0.5), (-0.5, 0)]
            else:  # Z stabilizer
                return [(0.5, 0.5), (0.5, -0.5), (-0.5, -0.5), (-0.5, 0.5)]
        elif layout_type == 'rotated':
            # For rotated, the neighbor patterns are different
            if stab_type == 'X':
                return [(0.25, 0.25), (-0.25, 0.25), (-0.25, -0.25), (0.25, -0.25)]
            else:  # Z stabilizer
                return [(0.25, 0.25), (0.25, -0.25), (-0.25, -0.25), (-0.25, 0.25)]
        
        # Default fallback for unknown layout types
        return [(0, 0.5), (0.5, 0), (0, -0.5), (-0.5, 0)]

    def _generate_logical_operators(self, code_distance: int, layout_type: str, qubit_layout: Dict[int, Dict[str, Any]]) -> Dict[str, List[int]]:
        """
        Generate logical X and Z operators for the surface code, extended for color code.
        """
        logical_operators = {'X': [], 'Z': []}
        coord_to_qubit = {}
        for q, info in qubit_layout.items():
            if info['type'] == 'data':
                x, y = info['x'], info['y']
                coord_to_qubit[(x, y)] = q
        if layout_type == 'planar':
            mid_idx = code_distance // 2
            for x in range(code_distance):
                if (x, float(mid_idx)) in coord_to_qubit:
                    logical_operators['X'].append(coord_to_qubit[(x, float(mid_idx))])
            print(f'[DEBUG] Planar logical X candidates: {[coord_to_qubit.get((x, float(mid_idx)), None) for x in range(code_distance)]}')
            for y in range(code_distance):
                if (float(mid_idx), y) in coord_to_qubit:
                    logical_operators['Z'].append(coord_to_qubit[(float(mid_idx), y)])
            print(f'[DEBUG] Planar logical Z candidates: {[coord_to_qubit.get((float(mid_idx), y), None) for y in range(code_distance)]}')
        elif layout_type == 'rotated':
            for i in range(code_distance):
                rot_x, rot_y = self._rotated_to_grid_coords(i, i, code_distance)
                if (rot_x, rot_y) in coord_to_qubit:
                    logical_operators['X'].append(coord_to_qubit[(rot_x, rot_y)])
            print(f'[DEBUG] Rotated logical X candidates: {[coord_to_qubit.get(self._rotated_to_grid_coords(i, i, code_distance), None) for i in range(code_distance)]}')
            for i in range(code_distance):
                rot_x, rot_y = self._rotated_to_grid_coords(i, code_distance - i - 1, code_distance)
                if (rot_x, rot_y) in coord_to_qubit:
                    logical_operators['Z'].append(coord_to_qubit[(rot_x, rot_y)])
            print(f'[DEBUG] Rotated logical Z candidates: {[coord_to_qubit.get(self._rotated_to_grid_coords(i, code_distance - i - 1, code_distance), None) for i in range(code_distance)]}')
        elif layout_type == 'color':
            # For color code, logical operators are typically along boundaries
            for x in range(code_distance):
                if (x, 0.0) in coord_to_qubit:
                    logical_operators['X'].append(coord_to_qubit[(x, 0.0)])
            print(f'[DEBUG] Color logical X candidates: {[coord_to_qubit.get((x, 0.0), None) for x in range(code_distance)]}')
            for y in range(code_distance):
                if (0.0, y * 0.866) in coord_to_qubit:
                    logical_operators['Z'].append(coord_to_qubit[(0.0, y * 0.866)])
            print(f'[DEBUG] Color logical Z candidates: {[coord_to_qubit.get((0.0, y * 0.866), None) for y in range(code_distance)]}')
        # Final filter: remove any invalid indices (not in qubit_layout)
        valid_indices = set(qubit_layout.keys())
        logical_operators['X'] = [q for q in logical_operators['X'] if q in valid_indices]
        logical_operators['Z'] = [q for q in logical_operators['Z'] if q in valid_indices]
        # Strict validation: raise error if logical operator is too short
        if len(logical_operators['X']) < code_distance:
            print(f'[ERROR] Logical X operator too short: {logical_operators["X"]} (expected {code_distance})')
            raise ValueError(f'Cannot form logical X operator of length {code_distance} (got {len(logical_operators["X"])}). Check patch layout and code distance.')
        if len(logical_operators['Z']) < code_distance:
            print(f'[ERROR] Logical Z operator too short: {logical_operators["Z"]} (expected {code_distance})')
            raise ValueError(f'Cannot form logical Z operator of length {code_distance} (got {len(logical_operators["Z"])}). Check patch layout and code distance.')
        return logical_operators

    def _rotated_to_grid_coords(self, x: int, y: int, d: int) -> Tuple[float, float]:
        """Convert rotated grid coordinates to the actual coordinates in the layout."""
        return (x - y) / 1.414, (x + y) / 1.414

    def _generate_adjacency_matrix_from_device(self, qubit_layout: Dict[int, Dict[str, Any]]) -> nx.Graph:
        """
        Generate an adjacency matrix based on device connectivity.
        This maps the surface code qubits to the device qubits and creates an
        adjacency matrix representing their connectivity.
        """
        G = nx.Graph()
        for q in qubit_layout:
            G.add_node(q, **qubit_layout[q])
        # Prefer coupling_map, fallback to qubit_connectivity
        device_coupling = self.device.get('coupling_map', None)
        if device_coupling is None:
            device_coupling = self.device.get('qubit_connectivity', None)
            if device_coupling is not None:
                # Convert keys to int if needed
                device_coupling = {int(k): v for k, v in device_coupling.items()}
        qubit_ids = list(qubit_layout.keys())
        if device_coupling is not None:
            for i, q in enumerate(qubit_ids):
                # For dict-based connectivity (qubit_connectivity)
                if isinstance(device_coupling, dict):
                    neighbors = device_coupling.get(q, [])
                    for j in neighbors:
                        if j in qubit_ids:
                            G.add_edge(q, j)
                # For list-based connectivity (coupling_map)
                elif isinstance(device_coupling, list):
                    if i < len(device_coupling):
                        for j in device_coupling[i]:
                            if j < len(qubit_ids):
                                G.add_edge(qubit_ids[i], qubit_ids[j])
        else:
            print("[ERROR] No device connectivity information found (neither 'coupling_map' nor 'qubit_connectivity').")
        return G

    def _validate_surface_code(self, surface_code: SurfaceCodeObject, check_ler: bool = False, ler_threshold: float = 0.1) -> None:
        """
        Validate the generated surface code to ensure it meets requirements.
        If check_ler is True, also estimate LER and warn/raise if above threshold.
        """
        # Check stabilizers
        for stab_type, stabilizers in surface_code.stabilizer_map.items():
            for stab in stabilizers:
                if len(stab['data_qubits']) < 2:
                    print(f"Warning: {stab_type} stabilizer on ancilla {stab['ancilla']} has fewer than 2 data qubits")
        # Check logical operators
        d = surface_code.code_distance
        min_op_size = d
        for op_type, qubits in surface_code.logical_operators.items():
            if len(qubits) < min_op_size:
                print(f"Warning: {op_type} logical operator has {len(qubits)} qubits, expected at least {min_op_size}")
        # Check connectivity
        if not nx.is_connected(surface_code.adjacency_matrix):
            print("Warning: Surface code graph is not connected")
            # Print connected components for debug
            components = list(nx.connected_components(surface_code.adjacency_matrix))
            print(f"Found {len(components)} connected components")
        # Optionally check LER
        if check_ler:
            try:
                mapping = {q: q for q in surface_code.qubit_layout}  # Identity mapping for validation
                noise_model = self.device.get('noise_model', {'p': 0.001})
                ler = DecoderInterface.estimate_logical_error_rate(surface_code, mapping, noise_model, num_trials=100)
                if ler > ler_threshold:
                    print(f"[LER WARNING] Estimated LER {ler:.2e} exceeds threshold {ler_threshold:.2e}")
            except Exception as e:
                print(f"[LER VALIDATION ERROR] {e}")

    def _visualize_layout(self, surface_code: SurfaceCodeObject) -> None:
        """Visualize the surface code layout."""
        # Create a new figure
        plt.figure(figsize=tuple(self.visualize_settings['figsize']))
        
        # Plot each qubit
        for idx, info in surface_code.qubit_layout.items():
            x, y = info['x'], info['y']
            
            # Different colors for different qubit types
            if info['type'] == 'data':
                plt.plot(x, y, 'bo', markersize=10)
            elif info['type'] == 'ancilla_X':
                plt.plot(x, y, 'rx', markersize=10)
            elif info['type'] == 'ancilla_Z':
                plt.plot(x, y, 'gx', markersize=10)
            
            # Label the qubit
            plt.text(x, y + 0.1, str(idx), fontsize=8, ha='center')
        
        # Plot stabilizer relationships
        for stab_type, stabilizers in surface_code.stabilizer_map.items():
            for stab in stabilizers:
                ancilla_idx = stab['ancilla']
                ancilla_pos = (surface_code.qubit_layout[ancilla_idx]['x'], 
                              surface_code.qubit_layout[ancilla_idx]['y'])
                
                # Draw lines from ancilla to its data qubits
                for data_idx in stab['data_qubits']:
                    data_pos = (surface_code.qubit_layout[data_idx]['x'], 
                               surface_code.qubit_layout[data_idx]['y'])
                    
                    # Different line styles for X and Z stabilizers
                    if stab_type == 'X':
                        plt.plot([ancilla_pos[0], data_pos[0]], [ancilla_pos[1], data_pos[1]], 'r-', alpha=0.5)
                    else:
                        plt.plot([ancilla_pos[0], data_pos[0]], [ancilla_pos[1], data_pos[1]], 'g-', alpha=0.5)
        
        # Plot logical operators
        for op_type, qubits in surface_code.logical_operators.items():
            # Sort qubits by position for cleaner visualization
            sorted_qubits = sorted(qubits, key=lambda q: (surface_code.qubit_layout[q]['x'], 
                                                        surface_code.qubit_layout[q]['y']))
            
            # Plot lines connecting the qubits in the logical operator
            points = [(surface_code.qubit_layout[q]['x'], surface_code.qubit_layout[q]['y']) 
                     for q in sorted_qubits]
            
            if points:
                x_vals, y_vals = zip(*points)
                if op_type == 'X':
                    plt.plot(x_vals, y_vals, 'm-', linewidth=3, label='X Logical')
                else:
                    plt.plot(x_vals, y_vals, 'c-', linewidth=3, label='Z Logical')
        
        # Add legend and labels
        plt.legend(loc='upper right')
        plt.title(f"{surface_code.layout_type.capitalize()} Surface Code (d={surface_code.code_distance})")
        plt.xlabel("X Position")
        plt.ylabel("Y Position")
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.axis('equal')
        
        # Show the plot
        plt.show()
