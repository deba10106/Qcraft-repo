"""
Surface code visualization with support for multiple patches and interactive features.
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

class SurfaceCodeVisualizer:
    def __init__(self, color_scheme: ColorScheme = None):
        """Initialize the surface code visualizer.
        
        Args:
            color_scheme: Optional color scheme to use. If None, uses default.
        """
        self.color_scheme = color_scheme or ColorScheme()
        self.fig = plt.figure(figsize=(10, 8))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, None)
        
        # Interactive state
        self.selected_qubit = None
        self.is_panning = False
        self.pan_start = None
        
        self._setup_interactive_features()
    
    def _setup_interactive_features(self):
        """Set up interactive matplotlib event handlers."""
        self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.canvas.mpl_connect('button_press_event', self.on_pan_start)
        self.canvas.mpl_connect('button_release_event', self.on_pan_end)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('pick_event', self.on_pick)
    
    def draw_surface_code(self, layout_result: Dict[str, Any]):
        """Draw the surface code layout.
        
        Args:
            layout_result: Surface code layout information
        """
        self._validate_input(layout_result)
        self.ax.clear()
        
        # Draw each patch
        for patch_idx, patch_data in layout_result['multi_patch_layout'].items():
            self._draw_patch(patch_idx, patch_data)
        
        # Add legend and title
        self._add_legend_and_title()
        
        self.ax.set_axis_off()
        plt.tight_layout()
        self.canvas.draw_idle()
    
    def _validate_input(self, layout_result: Dict[str, Any]):
        """Validate the input layout data."""
        if 'multi_patch_layout' not in layout_result:
            raise ValueError("Layout result must contain 'multi_patch_layout'")
        
        for patch_idx, patch_data in layout_result['multi_patch_layout'].items():
            if 'layout' not in patch_data:
                raise ValueError(f"Patch {patch_idx} missing 'layout' data")
            
            for qubit_idx, qubit_data in patch_data['layout'].items():
                required_keys = ['x', 'y', 'type']
                if not all(key in qubit_data for key in required_keys):
                    raise ValueError(f"Qubit {qubit_idx} in patch {patch_idx} missing required keys: {required_keys}")
    
    def _draw_patch(self, patch_idx: int, patch_data: Dict[str, Any]):
        """Draw a single surface code patch."""
        patch_layout = patch_data['layout']
        patch_color = plt.cm.tab10(int(patch_idx) % 10)
        
        # Draw patch boundary
        boundary_coords = self._get_patch_boundary(patch_layout)
        self.ax.plot(boundary_coords[:, 0], boundary_coords[:, 1], '--', 
                    color=patch_color, alpha=0.5, linewidth=2)
        
        # Create collections for batch drawing
        data_points, ancilla_x_points, ancilla_z_points = [], [], []
        data_labels, ancilla_x_labels, ancilla_z_labels = [], [], []
        
        for qubit_idx, pos_data in patch_layout.items():
            x, y = pos_data['x'], pos_data['y']
            qtype = pos_data['type']
            
            if 'data' in qtype:
                data_points.append([x, y])
                data_labels.append((x, y, str(qubit_idx)))
            elif qtype == 'ancilla_X':
                ancilla_x_points.append([x, y])
                ancilla_x_labels.append((x, y, str(qubit_idx)))
            else:  # ancilla_Z
                ancilla_z_points.append([x, y])
                ancilla_z_labels.append((x, y, str(qubit_idx)))
        
        # Draw qubit collections
        if data_points:
            data_points = np.array(data_points)
            self.ax.scatter(data_points[:, 0], data_points[:, 1],
                          c=self.color_scheme.data_qubit_color,
                          s=300, alpha=0.8, picker=True)
            for x, y, label in data_labels:
                self._draw_label(x, y, label)
        
        if ancilla_x_points:
            ancilla_x_points = np.array(ancilla_x_points)
            self.ax.scatter(ancilla_x_points[:, 0], ancilla_x_points[:, 1],
                          c=self.color_scheme.ancilla_x_color,
                          s=300, alpha=0.8, picker=True)
            for x, y, label in ancilla_x_labels:
                self._draw_label(x, y, label)
        
        if ancilla_z_points:
            ancilla_z_points = np.array(ancilla_z_points)
            self.ax.scatter(ancilla_z_points[:, 0], ancilla_z_points[:, 1],
                          c=self.color_scheme.ancilla_z_color,
                          s=300, alpha=0.8, picker=True)
            for x, y, label in ancilla_z_labels:
                self._draw_label(x, y, label)
        
        # Draw stabilizer connections if available
        if 'stabilizers' in patch_data:
            self._draw_stabilizers(patch_data['stabilizers'], patch_layout)
    
    def _draw_label(self, x: float, y: float, label: str):
        """Draw a qubit label with a black outline."""
        self.ax.text(x, y, label,
                    color='white',
                    fontsize=8,
                    ha='center',
                    va='center',
                    fontweight='bold',
                    path_effects=[path_effects.withStroke(linewidth=2, foreground='black')])
    
    def _draw_stabilizers(self, stabilizers: Dict[str, Any], patch_layout: Dict[str, Any]):
        """Draw stabilizer connections between qubits."""
        for stabilizer_data in stabilizers.values():
            qubit_indices = stabilizer_data['qubits']
            stabilizer_type = stabilizer_data.get('type', 'X')  # Default to X-type
            
            # Get coordinates for all qubits in the stabilizer
            coords = []
            for idx in qubit_indices:
                if str(idx) in patch_layout:
                    qubit_data = patch_layout[str(idx)]
                    coords.append([qubit_data['x'], qubit_data['y']])
            
            if len(coords) > 1:
                coords = np.array(coords)
                color = self.color_scheme.ancilla_x_color if stabilizer_type == 'X' else self.color_scheme.ancilla_z_color
                self.ax.plot(coords[:, 0], coords[:, 1], '-',
                           color=color, alpha=0.3, linewidth=1)
    
    def _get_patch_boundary(self, patch_layout: Dict[str, Any]) -> np.ndarray:
        """Calculate the boundary coordinates for a patch."""
        points = np.array([[data['x'], data['y']] for data in patch_layout.values()])
        hull = self._compute_convex_hull(points)
        return hull
    
    def _compute_convex_hull(self, points: np.ndarray) -> np.ndarray:
        """Compute the convex hull of a set of points."""
        # Simple implementation - in practice, use scipy.spatial.ConvexHull
        min_x, min_y = np.min(points, axis=0)
        max_x, max_y = np.max(points, axis=0)
        
        # Add some padding
        padding = 0.2
        min_x -= padding
        min_y -= padding
        max_x += padding
        max_y += padding
        
        return np.array([
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y],
            [min_x, min_y]
        ])
    
    def _add_legend_and_title(self):
        """Add legend and title to the visualization."""
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', label='Data Qubit',
                   markerfacecolor=self.color_scheme.data_qubit_color,
                   markersize=15, markeredgecolor='black'),
            Line2D([0], [0], marker='o', color='w', label='Ancilla X',
                   markerfacecolor=self.color_scheme.ancilla_x_color,
                   markersize=15, markeredgecolor='black'),
            Line2D([0], [0], marker='o', color='w', label='Ancilla Z',
                   markerfacecolor=self.color_scheme.ancilla_z_color,
                   markersize=15, markeredgecolor='black'),
        ]
        
        self.ax.legend(handles=legend_elements, loc='upper right',
                      fontsize=12, framealpha=0.8)
        self.ax.set_title('Surface Code Layout', fontsize=14)
    
    # Interactive event handlers
    def on_scroll(self, event):
        """Handle zoom events."""
        if event.inaxes != self.ax:
            return
        
        # Get the current axis limits
        cur_xlim = self.ax.get_xlim()
        cur_ylim = self.ax.get_ylim()
        
        # Get the current mouse position
        xdata, ydata = event.xdata, event.ydata
        
        # Calculate zoom factor
        base_scale = 1.1
        if event.button == 'up':
            scale_factor = 1/base_scale
        else:
            scale_factor = base_scale
        
        # Set new limits
        self.ax.set_xlim([xdata - (xdata - cur_xlim[0]) * scale_factor,
                         xdata - (xdata - cur_xlim[1]) * scale_factor])
        self.ax.set_ylim([ydata - (ydata - cur_ylim[0]) * scale_factor,
                         ydata - (ydata - cur_ylim[1]) * scale_factor])
        
        self.canvas.draw_idle()
    
    def on_pan_start(self, event):
        """Handle pan start events."""
        if event.inaxes != self.ax:
            return
        
        if event.button == 1:  # Left click
            self.is_panning = True
            self.pan_start = (event.xdata, event.ydata)
    
    def on_pan_end(self, event):
        """Handle pan end events."""
        self.is_panning = False
        self.pan_start = None
    
    def on_motion(self, event):
        """Handle motion events."""
        if not self.is_panning or event.inaxes != self.ax:
            return
        
        # Calculate the distance moved
        dx = event.xdata - self.pan_start[0]
        dy = event.ydata - self.pan_start[1]
        
        # Update the view limits
        self.ax.set_xlim(self.ax.get_xlim() - dx)
        self.ax.set_ylim(self.ax.get_ylim() - dy)
        
        self.canvas.draw_idle()
    
    def on_pick(self, event):
        """Handle pick events (qubit selection)."""
        if not hasattr(event.artist, 'get_offsets'):
            return
        
        ind = event.ind[0]
        pos = event.artist.get_offsets()[ind]
        
        if self.selected_qubit == (pos[0], pos[1]):
            # Deselect if already selected
            self.selected_qubit = None
            event.artist.set_alpha(0.8)
        else:
            # Select new qubit
            self.selected_qubit = (pos[0], pos[1])
            event.artist.set_alpha(1.0)
        
        self.canvas.draw_idle() 