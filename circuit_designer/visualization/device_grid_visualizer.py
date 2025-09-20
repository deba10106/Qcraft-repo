"""
Device grid visualization with interactive features and optimized layout.
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

class DeviceGridVisualizer:
    def __init__(self, color_scheme: ColorScheme = None):
        """Initialize the device grid visualizer.
        
        Args:
            color_scheme: Optional color scheme to use. If None, uses default.
        """
        self.color_scheme = color_scheme or ColorScheme()
        
        # Create figure with multiple layers
        self.fig, self.ax = plt.subplots(figsize=(8, 8))
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, None)
        
        self._setup_interactive_features()
    
    def _setup_interactive_features(self):
        """Set up interactive matplotlib event handlers."""
        self.ax.set_axis_off()
        
        self.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.canvas.mpl_connect('button_press_event', self.on_pan_start)
        self.canvas.mpl_connect('button_release_event', self.on_pan_end)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('pick_event', self.on_pick)
    
    def optimize_layout(self, G: nx.Graph, device_info: Dict[str, Any]) -> Dict[int, List[float]]:
        """Optimize the layout of the device grid.
        
        Args:
            G: NetworkX graph representing the device
            device_info: Device grid information
            
        Returns:
            Dictionary mapping qubit indices to [x, y] positions
        """
        # Use the provided qubit positions
        pos = {}
        for qubit_id, position in device_info['qubit_positions'].items():
            pos[int(qubit_id)] = position
        
        # Scale positions to match the grid spacing
        min_x = min(p[0] for p in pos.values())
        max_x = max(p[0] for p in pos.values())
        min_y = min(p[1] for p in pos.values())
        max_y = max(p[1] for p in pos.values())
        
        # Add padding
        padding = 0.5
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding
        
        # Draw grid lines
        x_grid = np.arange(min_x, max_x + 1)
        y_grid = np.arange(min_y, max_y + 1)
        
        for x in x_grid:
            self.ax.axvline(x=x, color='gray', alpha=0.2, linestyle=':')
        for y in y_grid:
            self.ax.axhline(y=y, color='gray', alpha=0.2, linestyle=':')
        
        # Set axis limits
        self.ax.set_xlim(min_x, max_x)
        self.ax.set_ylim(min_y, max_y)
        
        return pos
    
    def draw_device_grid(self, G: nx.Graph, pos: Dict[int, Tuple[float, float]]):
        """Draw the device grid with optimized performance.
        
        Args:
            G: NetworkX graph representing the device
            pos: Dictionary mapping node indices to (x, y) positions
        """
        self.ax.clear()
        
        # Convert edge list to segment list for LineCollection
        edge_segments = []
        for (u, v) in G.edges():
            edge_segments.append([pos[u], pos[v]])
        
        # Create collections for batch drawing
        edge_collection = LineCollection(edge_segments,
                                      color=self.color_scheme.device_edge_color,
                                      alpha=0.5,
                                      linewidth=2)
        
        node_positions = np.array([pos[node] for node in G.nodes()])
        node_collection = CircleCollection(sizes=[300]*len(G.nodes()),
                                        offsets=node_positions,
                                        transOffset=self.ax.transData,
                                        facecolor=self.color_scheme.device_node_color,
                                        alpha=0.5,
                                        picker=True)
        
        # Add collections to axis
        self.ax.add_collection(edge_collection)
        self.ax.add_collection(node_collection)
        
        # Add node labels
        for node in G.nodes():
            self.ax.text(pos[node][0], pos[node][1], str(node),
                        color=self.color_scheme.label_color,
                        fontsize=8,
                        ha='center',
                        va='center')
        
        self.ax.set_title('Device Grid', fontsize=14)
        self.ax.set_axis_off()
        plt.tight_layout()
        
        # Store state for interactivity
        self.G = G
        self.pos = pos
        self.edge_collection = edge_collection
        self.node_collection = node_collection
    
    # Interactive event handlers
    def on_scroll(self, event):
        """Handle zoom events."""
        if event.inaxes == self.ax:
            cur_xlim = self.ax.get_xlim()
            cur_ylim = self.ax.get_ylim()
            
            xdata = event.xdata
            ydata = event.ydata
            
            if event.button == 'up':
                scale_factor = 0.9
            else:
                scale_factor = 1.1
            
            self.ax.set_xlim([xdata - (xdata - cur_xlim[0]) * scale_factor,
                             xdata + (cur_xlim[1] - xdata) * scale_factor])
            self.ax.set_ylim([ydata - (ydata - cur_ylim[0]) * scale_factor,
                             ydata + (cur_ylim[1] - ydata) * scale_factor])
            
            self.canvas.draw_idle()
    
    def on_pan_start(self, event):
        """Handle pan start events."""
        if event.inaxes == self.ax:
            self.ax._pan_start = (event.xdata, event.ydata)
    
    def on_pan_end(self, event):
        """Handle pan end events."""
        if hasattr(self.ax, '_pan_start'):
            del self.ax._pan_start
    
    def on_motion(self, event):
        """Handle motion events."""
        if hasattr(self.ax, '_pan_start') and event.inaxes == self.ax:
            dx = event.xdata - self.ax._pan_start[0]
            dy = event.ydata - self.ax._pan_start[1]
            
            cur_xlim = self.ax.get_xlim()
            cur_ylim = self.ax.get_ylim()
            
            self.ax.set_xlim(cur_xlim - dx)
            self.ax.set_ylim(cur_ylim - dy)
            
            self.canvas.draw_idle()
    
    def on_pick(self, event):
        """Handle pick events."""
        pass 