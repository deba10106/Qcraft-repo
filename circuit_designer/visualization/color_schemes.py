"""
Color schemes for quantum circuit and surface code visualization.
"""

import yaml
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class ColorScheme:
    """Base color scheme class with default values."""
    # Surface code colors
    data_qubit_color: str = "#003366"
    ancilla_x_color: str = "#FF6B6B"
    ancilla_z_color: str = "#4ECDC4"
    edge_color: str = "#45B7D1"
    
    # Device grid colors
    device_node_color: str = "#2C3E50"
    device_edge_color: str = "#95A5A6"
    
    # Mapping overlay colors
    overlay_edge_color: str = "#003366"
    overlay_node_color: str = "#003366"
    
    # Text colors
    label_color: str = "white"
    title_color: str = "black"
    
    @classmethod
    def from_config(cls, config_path: str) -> 'ColorScheme':
        """Create a color scheme from a YAML configuration file."""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return cls(**config.get('colors', {}))

class ColorblindFriendlyScheme(ColorScheme):
    """Color scheme optimized for color blindness."""
    def __init__(self):
        super().__init__(
            data_qubit_color="#000000",  # Black
            ancilla_x_color="#E69F00",   # Orange
            ancilla_z_color="#56B4E9",   # Light blue
            edge_color="#009E73",        # Green
            device_node_color="#0072B2", # Dark blue
            device_edge_color="#D55E00", # Red
        )

class HighContrastScheme(ColorScheme):
    """High contrast color scheme for better visibility."""
    def __init__(self):
        super().__init__(
            data_qubit_color="#000000",  # Black
            ancilla_x_color="#FFFFFF",   # White
            ancilla_z_color="#FFD700",   # Gold
            edge_color="#FF0000",        # Red
            device_node_color="#0000FF", # Blue
            device_edge_color="#00FF00", # Green
        ) 