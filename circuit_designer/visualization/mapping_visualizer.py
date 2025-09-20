"""
Mapping visualization with layered drawing and performance optimization.
"""

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import matplotlib.patheffects as path_effects
from matplotlib.patches import Circle, Rectangle, Polygon
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection, CircleCollection
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from typing import Dict, Any, List, Tuple

from .color_schemes import ColorScheme
from .device_grid_visualizer import DeviceGridVisualizer


class MappingVisualizer:
    def __init__(self, color_scheme: ColorScheme = None):
        """Initialize the mapping visualizer.
        
        Args:
            color_scheme: Optional color scheme to use. If None, uses default.
        """
        self.color_scheme = color_scheme or ColorScheme()
        self.device_visualizer = DeviceGridVisualizer(self.color_scheme)
    
    def draw_mapping(self, layout_result: Dict[str, Any], mapping_info: Dict[str, Any], device_info: Dict[str, Any]):
        """Draw the mapping visualization and return a FigureCanvas for embedding in Qt dialogs (PySide6)."""
        print(f"[DEBUG][MappingVisualizer] draw_mapping called")
        print(f"[DEBUG][MappingVisualizer] mapping_info keys: {list(mapping_info.keys())}")
        print(f"[DEBUG][MappingVisualizer] device_info keys: {list(device_info.keys())}")
        print(f"[DEBUG][MappingVisualizer] mapping_info logical_to_physical: {mapping_info.get('logical_to_physical', {})}")
        # Generate qubit positions on the fly if missing
        if 'qubit_positions' not in device_info or not device_info['qubit_positions']:
            device_info['qubit_positions'] = self._generate_qubit_positions(device_info)
        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        # Draw logical patches (left subplot)
        self._draw_logical_patches(layout_result, ax1)
        
        # Draw physical device mapping (right subplot)
        self._draw_device_grid_with_mapping(mapping_info, device_info, ax2)
        
        # Add titles
        ax1.set_title("Logical Patches")
        ax2.set_title("Physical Device Mapping")
        
        plt.tight_layout()
        # Do NOT call plt.show() here
        canvas = FigureCanvas(fig)
        return canvas
    
    def _draw_logical_patches(self, layout_result: Dict[str, Any], ax: plt.Axes):
        """Draw logical patches with their qubit layout."""
        if 'multi_patch_layout' not in layout_result:
            print("[WARNING] No multi_patch_layout found in layout_result")
            return
            
        # Use blue for Patch 0 and red for Patch 1, fallback to tab10 for others
        def get_patch_color(idx):
            if int(idx) == 0:
                return 'tab:blue'
            elif int(idx) == 1:
                return 'tab:red'
            else:
                return plt.cm.tab10(int(idx) % 10)
        
        patch_colors = [get_patch_color(idx) for idx in layout_result['multi_patch_layout']]
        
        # First determine the grid dimensions
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')
        
        for patch_data in layout_result['multi_patch_layout'].values():
            patch_layout = patch_data.get('layout', {})
            for pos_data in patch_layout.values():
                x, y = pos_data['x'], pos_data['y']
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
        
        # Add some padding
        grid_padding = 0.5
        min_x -= grid_padding
        max_x += grid_padding
        min_y -= grid_padding
        max_y += grid_padding
        
        # Draw grid lines
        x_grid = np.arange(min_x, max_x + 1)
        y_grid = np.arange(min_y, max_y + 1)
        
        for x in x_grid:
            ax.axvline(x=x, color='gray', alpha=0.2, linestyle=':')
        for y in y_grid:
            ax.axhline(y=y, color='gray', alpha=0.2, linestyle=':')
        
        # Draw patches
        for patch_idx, patch_data in layout_result['multi_patch_layout'].items():
            patch_layout = patch_data.get('layout', {})
            color = get_patch_color(patch_idx)
            
            # Draw patch boundary
            boundary_coords = self._get_patch_boundary(patch_layout)
            ax.plot(boundary_coords[:, 0], boundary_coords[:, 1], '--', 
                   color=color, alpha=0.5, linewidth=2)
            
            # Draw qubits
            for qubit_idx, pos_data in patch_layout.items():
                x, y = pos_data['x'], pos_data['y']
                qtype = pos_data.get('type', '')
                error_rate = pos_data.get('error_rate', None)
                
                # Determine marker based on qubit type
                marker = 'o'  # default
                if 'data' in qtype:
                    marker = 's'  # square for data qubits
                elif qtype == 'ancilla_X':
                    marker = '^'  # triangle up for X ancillas
                elif qtype == 'ancilla_Z':
                    marker = 'v'  # triangle down for Z ancillas
                
                ax.scatter(x, y, c=[color], s=300, alpha=0.8,
                          marker=marker, edgecolors='black', linewidth=1.5,
                          label=f'Patch {patch_idx}' if qubit_idx == '0' else "")
                
                # Add label with qubit index and error rate
                label = f"{patch_idx}:{qubit_idx}"
                if error_rate is not None:
                    label += f"\n{error_rate:.3f}"
                ax.text(x, y, label, fontsize=8,
                       ha='center', va='center', color='white',
                       fontweight='bold',
                       path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])
            
            # Draw stabilizer connections
            if 'stabilizers' in patch_data:
                for stabilizer in patch_data['stabilizers']:
                    coords = []
                    for qubit_idx in stabilizer:
                        if str(qubit_idx) in patch_layout:
                            qubit_data = patch_layout[str(qubit_idx)]
                            coords.append([qubit_data['x'], qubit_data['y']])
                    if coords:
                        coords = np.array(coords)
                        ax.plot(coords[:, 0], coords[:, 1], '-',
                               color=color, alpha=0.3, linewidth=1)
        
        # Set axis limits with padding
        ax.set_xlim(min_x, max_x)
        ax.set_ylim(min_y, max_y)
        ax.set_aspect('equal')
        ax.set_title('Logical Patches', fontsize=14)
    
    def _get_patch_boundary(self, patch_layout: Dict[str, Any]) -> np.ndarray:
        """Calculate the boundary coordinates for a patch."""
        points = np.array([[data['x'], data['y']] for data in patch_layout.values()])
        hull = self._compute_convex_hull(points)
        return hull
    
    def _compute_convex_hull(self, points: np.ndarray) -> np.ndarray:
        """Compute the convex hull of a set of points."""
        # Simple implementation - in practice, use scipy.spatial.ConvexHull
        # This is a placeholder that returns a rectangle boundary
        min_x, min_y = np.min(points, axis=0)
        max_x, max_y = np.max(points, axis=0)
        
        return np.array([
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y],
            [min_x, min_y]
        ])
    
    def _draw_device_grid_with_mapping(self, mapping_info: Dict[str, Any], 
                                     device_info: Dict[str, Any], 
                                     ax: plt.Axes):
        """Draw the device grid with mapped qubits and connections."""
        def get_patch_color(idx):
            if int(idx) == 0:
                return 'tab:blue'
            elif int(idx) == 1:
                return 'tab:red'
            else:
                return plt.cm.tab10(int(idx) % 10)
        print(f"[DEBUG][MappingVisualizer] _draw_device_grid_with_mapping called")
        print(f"[DEBUG][MappingVisualizer] mapping_info logical_to_physical: {mapping_info.get('logical_to_physical', {})}")
        print(f"[DEBUG][MappingVisualizer] device_info qubit_positions: {device_info.get('qubit_positions', {})}")
        # Defensive check for qubit_positions
        if 'qubit_positions' not in device_info:
            print("[ERROR] device_info is missing 'qubit_positions'. Cannot plot device grid.")
            return
        
        # Debug logging
        print(f"[DEBUG] Number of patches to map: {len(mapping_info['logical_to_physical'])}")
        print(f"[DEBUG] Patches: {list(mapping_info['logical_to_physical'].keys())}")
        
        # Create graph for device layout
        G = self._create_device_graph(device_info)
        pos = self.device_visualizer.optimize_layout(G, device_info)
        
        # Validate all physical qubits are in position map
        all_physical_qubits = set()
        for patch_map in mapping_info['logical_to_physical'].values():
            all_physical_qubits.update(patch_map.values())
        
        missing_positions = all_physical_qubits - set(pos.keys())
        if missing_positions:
            print(f"[WARNING] Missing positions for physical qubits: {missing_positions}")
        
        # First draw all physical connections
        for (u, v) in G.edges():
            ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]], 
                   color='lightgray', linestyle='-', alpha=0.3, zorder=1)
        
        # Track which physical qubits are used
        used_qubits = set()
        for patch_idx, patch_map in mapping_info['logical_to_physical'].items():
            print(f"[DEBUG] Processing patch {patch_idx} with {len(patch_map)} qubits")
            used_qubits.update(patch_map.values())
        
        # Draw unused physical qubits
        unused_qubits = set(pos.keys()) - used_qubits
        if unused_qubits:
            print(f"[DEBUG] Found {len(unused_qubits)} unused qubits")
            unused_pos = {q: pos[q] for q in unused_qubits}
            ax.scatter([p[0] for p in unused_pos.values()],
                      [p[1] for p in unused_pos.values()],
                      c='lightgray', s=300, alpha=0.3, marker='o',
                      edgecolors='gray', linewidth=1, zorder=2,
                      label='Unused Qubits')
        
        # Draw mapped qubits for each patch with different colors
        mapped_count = 0
        for patch_idx, patch_map in mapping_info['logical_to_physical'].items():
            patch_color = get_patch_color(patch_idx)
            
            # Get patch data
            patch_data = None
            if patch_idx in mapping_info['multi_patch_layout']:
                patch_data = mapping_info['multi_patch_layout'][patch_idx]
            elif str(patch_idx) in mapping_info['multi_patch_layout']:
                patch_data = mapping_info['multi_patch_layout'][str(patch_idx)]
            
            if patch_data is None:
                print(f"[WARNING] No layout data found for patch {patch_idx}")
                continue
                
            patch_layout = patch_data.get('layout', {})
            print(f"[DEBUG] Patch {patch_idx} layout has {len(patch_layout)} qubits")
            
            # Draw qubits in this patch
            patch_mapped_count = 0
            for lq, pq in patch_map.items():
                if pq not in pos:
                    print(f"[WARNING] No position found for physical qubit {pq} in patch {patch_idx}")
                    continue
                    
                # Get qubit type and error rate
                lq_data = None
                if str(lq) in patch_layout:
                    lq_data = patch_layout[str(lq)]
                elif lq in patch_layout:
                    lq_data = patch_layout[lq]
                
                if lq_data is None:
                    print(f"[WARNING] No layout data for logical qubit {lq} in patch {patch_idx}")
                    continue
                
                qtype = lq_data.get('type', '')
                error_rate = lq_data.get('error_rate', None)
                
                # Determine marker based on qubit type
                marker = 'o'  # default
                if 'data' in qtype:
                    marker = 's'  # square for data qubits
                elif qtype == 'ancilla_X':
                    marker = '^'  # triangle up for X ancillas
                elif qtype == 'ancilla_Z':
                    marker = 'v'  # triangle down for Z ancillas
                
                # Draw qubit
                ax.scatter(pos[pq][0], pos[pq][1], c=[patch_color], s=400,
                         marker=marker, edgecolors='black', linewidth=1.5,
                         alpha=0.8, zorder=3,
                         label=f'Patch {patch_idx}' if lq == 0 else "")
                
                # Add label with logical qubit index and error rate
                label = f"{patch_idx}:{lq}"
                if error_rate is not None:
                    label += f"\n{error_rate:.3f}"
                ax.text(pos[pq][0], pos[pq][1], label, fontsize=10,
                       ha='center', va='center', color='white',
                       fontweight='bold', zorder=4,
                       path_effects=[path_effects.withStroke(linewidth=3,
                                                          foreground='black')])
                patch_mapped_count += 1
            
            print(f"[DEBUG] Successfully mapped {patch_mapped_count} qubits for patch {patch_idx}")
            mapped_count += patch_mapped_count
            
            # Draw connections between physically adjacent qubits in the same patch
            physical_qubits = list(patch_map.values())
            connections_count = 0
            for i, pq1 in enumerate(physical_qubits):
                for pq2 in physical_qubits[i+1:]:
                    if self._are_physically_adjacent(pq1, pq2, device_info):
                        ax.plot([pos[pq1][0], pos[pq2][0]], 
                               [pos[pq1][1], pos[pq2][1]],
                               color=patch_color, alpha=0.5,
                               linewidth=2, linestyle='--', zorder=2)
                        connections_count += 1
            print(f"[DEBUG] Drew {connections_count} connections for patch {patch_idx}")
        
        print(f"[DEBUG] Total mapped qubits: {mapped_count}")
        
        # Draw inter-patch connections
        if 'inter_patch_connectivity' in mapping_info:
            print(f"[DEBUG] Processing {len(mapping_info['inter_patch_connectivity'])} inter-patch connections")
            for key, connection_info in mapping_info['inter_patch_connectivity'].items():
                # Parse the key for patch indices (handle both tuple and string cases)
                if isinstance(key, tuple):
                    patch1, patch2 = int(key[0]), int(key[1])
                else:
                    patches = key.strip('()').split(',')
                    patch1, patch2 = int(patches[0]), int(patches[1])
                
                if patch1 in mapping_info['logical_to_physical'] and patch2 in mapping_info['logical_to_physical']:
                    qubits1 = list(mapping_info['logical_to_physical'][patch1].values())
                    qubits2 = list(mapping_info['logical_to_physical'][patch2].values())
                    
                    # Find closest pair of qubits between patches
                    min_dist = float('inf')
                    closest_pair = None
                    for q1 in qubits1:
                        for q2 in qubits2:
                            if q1 in pos and q2 in pos:
                                dist = np.sqrt((pos[q1][0] - pos[q2][0])**2 + 
                                             (pos[q1][1] - pos[q2][1])**2)
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_pair = (q1, q2)
                    
                    if closest_pair:
                        q1, q2 = closest_pair
                        ax.plot([pos[q1][0], pos[q2][0]], 
                               [pos[q1][1], pos[q2][1]],
                               color='red', alpha=0.6,
                               linewidth=2, linestyle='-.',
                               zorder=2,
                               label=f'Inter-patch link (d={connection_info.get("distance", "N/A")})')
                        print(f"[DEBUG] Drew connection between patches {patch1} and {patch2}")
        
        # Add legend
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(),
                 loc='center left', bbox_to_anchor=(1, 0.5))
        
        # Set axis properties
        ax.set_aspect('equal')
        ax.grid(True, linestyle=':', alpha=0.3)
        ax.set_title('Physical Device Mapping', fontsize=14)
        
        # Explicitly set axis limits to fit all mapped qubits with padding
        all_x = [pos[q][0] for q in pos]
        all_y = [pos[q][1] for q in pos]
        if all_x and all_y:
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            pad_x = (max_x - min_x) * 0.1 if max_x > min_x else 1
            pad_y = (max_y - min_y) * 0.1 if max_y > min_y else 1
            ax.set_xlim(min_x - pad_x, max_x + pad_x)
            ax.set_ylim(min_y - pad_y, max_y + pad_y)
            print(f"[DEBUG][MappingVisualizer] Set axis limits x:[{min_x - pad_x}, {max_x + pad_x}], y:[{min_y - pad_y}, {max_y + pad_y}]")
        else:
            print("[DEBUG][MappingVisualizer] No positions to set axis limits.")
        print(f"[DEBUG][MappingVisualizer] Finished plotting. Mapped qubits: {mapped_count}, Unused qubits: {len(unused_qubits) if 'unused_qubits' in locals() else 0}")
    
    def _are_physically_adjacent(self, pq1: int, pq2: int, device_info: Dict[str, Any]) -> bool:
        """Check if two physical qubits are adjacent in the device."""
        qubit_positions = device_info.get('qubit_positions', {})
        connectivity = device_info.get('connectivity', {})

        # Helper to get the position of a qubit, handling both str and int keys
        def get_pos(q):
            if str(q) in qubit_positions:
                return qubit_positions[str(q)]
            elif int(q) in qubit_positions:
                return qubit_positions[int(q)]
            else:
                raise KeyError(f"Physical qubit {q} not found in device qubit_positions: {list(qubit_positions.keys())}")

        # Helper to get neighbors from connectivity, handling both str and int keys
        def get_neighbors(q):
            if str(q) in connectivity:
                return connectivity[str(q)]
            elif int(q) in connectivity:
                return connectivity[int(q)]
            else:
                return []

        if connectivity:
            # If we have explicit connectivity information
            return pq2 in get_neighbors(pq1) or pq1 in get_neighbors(pq2)
        else:
            # Fall back to checking if qubits are neighbors in a grid
            pos1 = get_pos(pq1)
            pos2 = get_pos(pq2)
            dx = abs(pos1[0] - pos2[0])
            dy = abs(pos1[1] - pos2[1])
            return (dx == 1 and dy == 0) or (dx == 0 and dy == 1)
    
    def _draw_stabilizers(self, stabilizers: Dict[str, Any], patch_layout: Dict[str, Any],
                         ax: plt.Axes):
        """Draw stabilizer connections between qubits."""
        for stabilizer_data in stabilizers.values():
            qubit_indices = stabilizer_data['qubits']
            stabilizer_type = stabilizer_data.get('type', 'X')
            
            # Get coordinates for all qubits in the stabilizer
            coords = []
            for idx in qubit_indices:
                if str(idx) in patch_layout:
                    qubit_data = patch_layout[str(idx)]
                    coords.append([qubit_data['x'], qubit_data['y']])
            
            if len(coords) > 1:
                coords = np.array(coords)
                color = self.color_scheme.ancilla_x_color if stabilizer_type == 'X' else self.color_scheme.ancilla_z_color
                ax.plot(coords[:, 0], coords[:, 1], '-',
                       color=color, alpha=0.3, linewidth=1)
    
    def _create_device_graph(self, device_info: Dict[str, Any]) -> nx.Graph:
        """Create a NetworkX graph representing the device grid.
        
        Args:
            device_info: Dictionary containing device information including connectivity
            
        Returns:
            NetworkX graph representing the device
        """
        G = nx.Graph()
        
        # Defensive check for qubit_positions
        if 'qubit_positions' not in device_info:
            print("[ERROR] device_info is missing 'qubit_positions'. Cannot create device graph.")
            return G
        
        # Add nodes
        for qubit_id, pos in device_info['qubit_positions'].items():
            G.add_node(int(qubit_id), pos=pos)
        
        # Add edges based on connectivity
        if 'connectivity' in device_info:
            # Handle dictionary-based connectivity format
            for qubit_id, neighbors in device_info['connectivity'].items():
                for neighbor in neighbors:
                    # Add edge only if both qubits exist and edge hasn't been added
                    if int(qubit_id) in G and int(neighbor) in G and not G.has_edge(int(qubit_id), int(neighbor)):
                        G.add_edge(int(qubit_id), int(neighbor))
        
        return G
    
    def _generate_qubit_positions(self, device_info: Dict[str, Any]) -> Dict[int, tuple]:
        """Generate synthetic qubit positions for visualization based on device topology."""
        topology = device_info.get('topology_type', '').lower()
        connectivity = device_info.get('qubit_connectivity', {})
        qubits = list(connectivity.keys())
        qubits = [int(q) for q in qubits]
        n = len(qubits)
        positions = {}
        if topology == 'heavy-hex':
            # Arrange in a heavy-hex-like grid (approximate)
            cols = int(np.ceil(np.sqrt(n)))
            for idx, q in enumerate(sorted(qubits)):
                row = idx // cols
                col = idx % cols
                # Offset every other row for hex effect
                x = col + 0.5 * (row % 2)
                y = row * np.sqrt(3)/2
                positions[q] = (x, y)
        elif topology == 'all_to_all':
            # Arrange in a circle
            for idx, q in enumerate(sorted(qubits)):
                angle = 2 * np.pi * idx / n
                x = np.cos(angle)
                y = np.sin(angle)
                positions[q] = (x, y)
        else:
            # Fallback: grid
            cols = int(np.ceil(np.sqrt(n)))
            for idx, q in enumerate(sorted(qubits)):
                row = idx // cols
                col = idx % cols
                positions[q] = (col, row)
        print(f"[DEBUG][MappingVisualizer] Generated synthetic qubit positions for {device_info.get('device_name', '?')}: {positions}")
        return positions 