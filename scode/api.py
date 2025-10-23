# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import os
from typing import List, Dict, Any, Optional
import importlib
import io
import numpy as np
import json, yaml
from code_switcher.code_switcher import CodeSwitcher
from logging_results.logging_results_manager import LoggingResultsManager
import uuid
import math
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
import networkx as nx
from hardware_abstraction.device_abstraction import DeviceAbstraction
from configuration_management.config_manager import ConfigManager
try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import SubprocVecEnv
    SB3_AVAILABLE = True
except ImportError:
    PPO = None
    SubprocVecEnv = None
    SB3_AVAILABLE = False
from scode.utils.decoder_interface import DecoderInterface

# Device abstraction and config management
from scode.heuristic_layer.surface_code import SurfaceCode
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from scode.heuristic_layer.surface_code_object import SurfaceCodeObject
from scode.graph_transformer.graph_transformer import ConnectivityAwareGraphTransformer

from scode.rl_agent.environment import SurfaceCodeEnvironment
from scode.rl_agent.progress import ProgressBarCallback

# Utility for deep merging dicts (API > config)
def deep_merge(base: dict, override: Optional[dict]) -> dict:
    if not override:
        return base.copy()
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

class SurfaceCodeAPI:
    """
    Production-ready API for surface code generation and hardware mapping.
    Provides interfaces for initializing surface codes, mapping to hardware,
    and generating optimized layouts.
    """
    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None, device_overrides: Optional[Dict[str, Any]] = None):
        try:
            self.logger.log_event('api_init_called', {}, level='DEBUG')
        except Exception:
            print("[DEBUG][API] SurfaceCodeAPI.__init__ CALLED")
        """
        Initialize the Surface Code API with a configuration.
        Args:
            config_overrides: Dict of config values to override YAML config.
            device_overrides: Dict of device values to override device config.
        """
        # Load config using ConfigManager
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('multi_patch_rl_agent')
        self.config = deep_merge(base_config, config_overrides)
        # Debug (prefer logger once available)
        try:
            self.logger.log_event('api_init_debug', {'config_keys': list(self.config.keys()), 'reward_function': self.config.get('reward_function')}, level='DEBUG')
        except Exception:
            print(f"[DEBUG][API INIT] self.config keys: {list(self.config.keys())}")
            print(f"[DEBUG][API INIT] reward_function section: {self.config.get('reward_function', None)}")
        # Validate config against schema if available
        try:
            valid = ConfigManager.validate_config('multi_patch_rl_agent')
            if not valid:
                try:
                    self.logger.log_event('schema_validation_warning', {'module': 'multi_patch_rl_agent'}, level='WARNING')
                except Exception:
                    print("[WARNING][API INIT] multi_patch_rl_agent config failed schema validation. Proceeding with caution.")
        except Exception as e:
            try:
                self.logger.log_event('schema_validation_warning', {'module': 'multi_patch_rl_agent', 'error': str(e)}, level='WARNING')
            except Exception:
                print(f"[WARNING][API INIT] Schema validation skipped: {e}")
        # Failsafe: if reward_function missing, load from base_config
        if 'reward_function' not in self.config or not self.config['reward_function']:
            try:
                self.logger.log_event('config_warning', {'message': 'reward_function missing after merge, loading from base_config'}, level='WARNING')
            except Exception:
                print("[WARNING][API INIT] reward_function missing after merge, loading from base_config!")
            self.config['reward_function'] = base_config.get('reward_function', {})
        self.surface_code_config = self.config.get('multi_patch_rl_agent', {}).get('environment', {})
        # Enforce provider/device coming from hardware.json only
        try:
            env_cfg = self.config.get('multi_patch_rl_agent', {}).get('environment', {})
            if 'provider' in env_cfg or 'device' in env_cfg:
                env_cfg.pop('provider', None)
                env_cfg.pop('device', None)
                # Best-effort log
                try:
                    self.logger.log_event('config_sanitized', {'removed_fields': ['provider','device'], 'module': 'multi_patch_rl_agent.environment'}, level='WARNING')
                except Exception:
                    print("[WARNING][API INIT] Removed provider/device from multi_patch_rl_agent.environment; values must come from hardware.json")
        except Exception:
            pass
        self.advanced_constraints = self.config.get('advanced_constraints', {})
        # Load device info using DeviceAbstraction
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.hardware_info = deep_merge(base_device, device_overrides)
        # Initialize the heuristic layer for surface code generation
        self.heuristic_layer = HeuristicInitializationLayer(self.config, self.hardware_info)
        # Initialize the graph transformer for hardware mapping
        self.graph_transformer = ConnectivityAwareGraphTransformer(
            self.config,
            self.hardware_info,
            self.hardware_info.get('native_gates', []),
            self.hardware_info.get('gate_error_rates', {}),
            self._get_qubit_error_rates()
        )
        # Initialize reward engine
        from scode.rl_agent.reward_engine import MultiPatchRewardEngine
        self.reward_engine = MultiPatchRewardEngine(self.config)
        # Initialize logger for results and events
        self.logger = LoggingResultsManager()
        # Keep track of generated surface codes and mappings
        self.generated_codes = {}
        self.current_code = None
        self.current_mapping = None

    def _get_qubit_error_rates(self) -> Dict[int, float]:
        qubit_properties = self.hardware_info.get('qubit_properties', {})
        error_rates = {}
        for q_str, properties in qubit_properties.items():
            q = int(q_str)
            error_rates[q] = properties.get('readout_error', 0.0)
        return error_rates

        # '''
        # DEPRECATED: Single-patch mapping is disabled. Use get_multi_patch_mapping exclusively.
        # '''
        # raise NotImplementedError("Single-patch mapping is disabled. Use get_multi_patch_mapping exclusively.")

    def generate_multi_patch_surface_code_layout(self, num_patches: int = 2,
                                               patch_distances: Optional[List[int]] = None,
                                               patch_shapes: Optional[List[str]] = None,
                                               visualize: bool = False, device: str = None) -> Dict[str, Any]:
        """
        Generate a layout with multiple surface code patches.
        
        Args:
            num_patches: Number of surface code patches
            patch_distances: List of code distances for each patch
            patch_shapes: List of layout types for each patch
            visualize: Whether to visualize the layout
            
        Returns:
            Dictionary containing the multi-patch layout
        """
        multi_patch_config = self.config.get('multi_patch', {})
        
        # Use parameters from config if not provided
        if patch_distances is None:
            default_distance = self.surface_code_config.get('code_distance', 3)
            patch_distances = [default_distance] * num_patches
        
        if patch_shapes is None:
            default_shape = self.surface_code_config.get('layout_type', 'planar')
            patch_shapes = multi_patch_config.get('patch_shapes', [default_shape] * num_patches)
            # Ensure we have enough shapes
            if len(patch_shapes) < num_patches:
                patch_shapes = patch_shapes + [default_shape] * (num_patches - len(patch_shapes))
        
        # Generate individual patches
        patches = []
        for i in range(num_patches):
            distance = patch_distances[i] if i < len(patch_distances) else patch_distances[-1]
            shape = patch_shapes[i] if i < len(patch_shapes) else patch_shapes[-1]
            
            patch = self.heuristic_layer.generate_surface_code(
                code_distance=distance,
                layout_type=shape,
                visualize=False
            )
            patches.append(patch)
        
        # Place patches side by side with minimum distance between them
        min_distance = multi_patch_config.get('min_distance_between_patches', 1)
        
        # Combine patches into a single layout
        combined_layout = self._combine_patches(patches, min_distance)
        
        # Set grid_connectivity to device's grid_connectivity type if available, else fallback to topology_type or 'unknown'
        combined_layout['grid_connectivity'] = self.hardware_info.get('grid_connectivity', self.hardware_info.get('topology_type', 'unknown'))
        
        # Visualize if requested
        if visualize:
            self._visualize_multi_patch(combined_layout, patches)
        
        # --- Patch: Add code_spaces key for FT circuit builder compatibility ---
        code_spaces = []
        for i, patch in enumerate(patches):
            patch_dict = {
                'name': f'code_space_{i}',
                'code_distance': patch.code_distance,
                'layout_type': patch.layout_type,
                'qubit_layout': patch.qubit_layout,
                'stabilizer_map': patch.stabilizer_map,
                'logical_operators': patch.logical_operators,
                'adjacency_matrix': patch.adjacency_matrix,
                'topology_type': getattr(patch, 'topology_type', None),
                'supported_logical_gates': getattr(patch, 'supported_logical_gates', None)
            }
            code_spaces.append(patch_dict)
        combined_layout['code_spaces'] = code_spaces
        # Tag family for downstream modules
        combined_layout['family'] = 'surface'
        for cs in combined_layout['code_spaces']:
            cs['family'] = 'surface'
        return combined_layout

    def _combine_patches(self, patches: List[SurfaceCodeObject], min_distance: int) -> Dict[str, Any]:
        """
        Combine multiple surface code patches into a single layout.
        
        Args:
            patches: List of surface code patches
            min_distance: Minimum distance between patches
            
        Returns:
            Dictionary containing the combined layout
        """
        # Create a combined layout
        combined_qubit_layout = {}
        combined_stabilizer_map = {'X': [], 'Z': []}
        combined_logical_operators = {'X': [], 'Z': []}
        
        # Qubit index offset for each patch
        qubit_index = 0
        x_offset = 0
        patch_info = []
        
        # For each patch
        for i, patch in enumerate(patches):
            # Calculate patch width (max x coordinate)
            patch_width = 0
            for q, info in patch.qubit_layout.items():
                patch_width = max(patch_width, info['x'])
            patch_width += 1  # Add 1 for zero-based coordinates
            
            # Map from original qubit indices to new indices
            qubit_map = {}
            
            # Add qubits with offset
            for q, info in patch.qubit_layout.items():
                new_info = info.copy()
                new_info['x'] += x_offset
                combined_qubit_layout[qubit_index] = new_info
                qubit_map[q] = qubit_index
                qubit_index += 1
            
            # Update stabilizer map
            for stab_type, stabilizers in patch.stabilizer_map.items():
                if isinstance(stabilizers, list):
                    if stabilizers and isinstance(stabilizers[0], dict):
                        # New format with dict entries
                        for stab in stabilizers:
                            new_stab = stab.copy()
                            new_stab['ancilla'] = qubit_map[stab['ancilla']]
                            new_stab['data_qubits'] = [qubit_map[q] for q in stab['data_qubits']]
                            combined_stabilizer_map[stab_type].append(new_stab)
                    else:
                        # Old format with just ancilla indices
                        for ancilla in stabilizers:
                            if ancilla in qubit_map:
                                combined_stabilizer_map[stab_type].append(qubit_map[ancilla])
            
            # Update logical operators
            for op_type, qubits in patch.logical_operators.items():
                combined_logical_operators[op_type].extend([qubit_map[q] for q in qubits if q in qubit_map])
            
            # Store patch information
            patch_info.append({
                'index': i,
                'x_offset': x_offset,
                'qubit_map': qubit_map,
                'code_distance': patch.code_distance,
                'layout_type': patch.layout_type
            })
            
            # Update offset for next patch
            x_offset += patch_width + min_distance
        
        # Create adjacency matrix for the combined layout
        combined_graph = nx.Graph()
        for q, info in combined_qubit_layout.items():
            combined_graph.add_node(q, **info)
        
        # Connect qubits within each patch
        for i, patch in enumerate(patches):
            for q1, q2 in patch.adjacency_matrix.edges():
                if q1 in patch_info[i]['qubit_map'] and q2 in patch_info[i]['qubit_map']:
                    new_q1 = patch_info[i]['qubit_map'][q1]
                    new_q2 = patch_info[i]['qubit_map'][q2]
                    combined_graph.add_edge(new_q1, new_q2)
        
        # Return the combined layout
        return {
            'qubit_layout': combined_qubit_layout,
            'stabilizer_map': combined_stabilizer_map,
            'logical_operators': combined_logical_operators,
            'adjacency_matrix': combined_graph,
            'patch_info': patch_info,
            'num_patches': len(patches),
            'code_distance': patches[0].code_distance if patches else None,
            'layout_type': patches[0].layout_type if patches else None
        }

    def _visualize_mapping(self, surface_code: SurfaceCodeObject, mapping_result: Dict[str, Any]) -> None:
        """
        Visualize the mapping of a surface code to hardware.
        
        Args:
            surface_code: Original surface code object
            mapping_result: Result from map_to_hardware
        """
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("Matplotlib is required for visualization. Install with: pip install qcraft[full]")
        # Get the mapping and annotated graph
        mapping = mapping_result.get('transformed_layout', {})
        hw_graph = mapping_result.get('annotated_graph', nx.Graph())
        
        # Create figure
        plt.figure(figsize=(10, 8))
        
        # Draw hardware graph
        pos = nx.spring_layout(hw_graph, seed=42)
        
        # Node colors based on qubit type
        node_colors = []
        for hw_q in hw_graph.nodes():
            if 'qubit_type' in hw_graph.nodes[hw_q]:
                qubit_type = hw_graph.nodes[hw_q].get('qubit_type', 'unknown')
                if qubit_type == 'data':
                    node_colors.append('blue')
                elif qubit_type == 'ancilla_X':
                    node_colors.append('green')
                elif qubit_type == 'ancilla_Z':
                    node_colors.append('red')
                else:
                    node_colors.append('gray')
            else:
                node_colors.append('gray')
        
        # Draw nodes and edges
        nx.draw_networkx_nodes(hw_graph, pos, node_color=node_colors, node_size=200)
        nx.draw_networkx_edges(hw_graph, pos, alpha=0.5)
        
        # Label nodes with hardware and surface code indices
        labels = {}
        for hw_q in hw_graph.nodes():
            sc_qubit = hw_graph.nodes[hw_q].get('sc_qubit', None)
            if sc_qubit is not None:
                labels[hw_q] = f"{hw_q}\n(SC:{sc_qubit})"
            else:
                labels[hw_q] = f"{hw_q}"
        nx.draw_networkx_labels(hw_graph, pos, labels=labels, font_size=8)
        
        # Draw edges used by surface code with thicker lines
        used_edges = [(u, v) for u, v in hw_graph.edges() if hw_graph.edges[u, v].get('used', False)]
        nx.draw_networkx_edges(hw_graph, pos, edgelist=used_edges, width=2.0, edge_color='blue')
        
        # Add title and legend
        plt.title(f"Surface Code Mapping: {surface_code.layout_type} d={surface_code.code_distance}")
        plt.legend([
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='green', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=10),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', markersize=10),
            plt.Line2D([0], [0], color='blue', lw=2)
        ], ['Data Qubit', 'X Ancilla', 'Z Ancilla', 'Unused', 'Used Edge'], loc='upper right')
        
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    def _visualize_multi_patch(self, combined_layout: Dict[str, Any], patches: List[SurfaceCodeObject]) -> None:
        """
        Visualize a multi-patch surface code layout.
        
        Args:
            combined_layout: Combined layout information
            patches: Original patch objects
        """
        if not MATPLOTLIB_AVAILABLE:
            raise ImportError("Matplotlib is required for visualization. Install with: pip install qcraft[full]")
        qubit_layout = combined_layout.get('qubit_layout', {})
        patch_info = combined_layout.get('patch_info', [])
        
        # Create figure
        plt.figure(figsize=(12, 6))
        
        # Plot data and ancilla qubits
        data_x, data_y = [], []
        anc_x_x, anc_x_y = [], []
        anc_z_x, anc_z_y = [], []
        
        for q, info in qubit_layout.items():
            if info['type'] == 'data':
                data_x.append(info['x'])
                data_y.append(info['y'])
            elif info['type'] == 'ancilla_X':
                anc_x_x.append(info['x'])
                anc_x_y.append(info['y'])
            elif info['type'] == 'ancilla_Z':
                anc_z_x.append(info['x'])
                anc_z_y.append(info['y'])
        
        # Plot qubits
        plt.scatter(data_x, data_y, c='blue', marker='o', s=80, label='Data Qubits')
        plt.scatter(anc_x_x, anc_x_y, c='green', marker='x', s=60, label='X Ancilla')
        plt.scatter(anc_z_x, anc_z_y, c='red', marker='s', s=60, label='Z Ancilla')
        
        # Draw patch boundaries
        for i, patch_data in enumerate(patch_info):
            x_offset = patch_data['x_offset']
            
            # Find patch dimensions
            patch = patches[i]
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = float('-inf'), float('-inf')
            
            for q, info in patch.qubit_layout.items():
                min_x = min(min_x, info['x'])
                min_y = min(min_y, info['y'])
                max_x = max(max_x, info['x'])
                max_y = max(max_y, info['y'])
            
            width = max_x - min_x + 1
            height = max_y - min_y + 1
            
            # Draw a rectangle around the patch
            plt.plot(
                [x_offset + min_x, x_offset + min_x + width, x_offset + min_x + width, 
                 x_offset + min_x, x_offset + min_x],
                [min_y, min_y, min_y + height, min_y + height, min_y],
                'k--', alpha=0.7
            )
            
            # Add patch label
            plt.text(
                x_offset + min_x + width/2, 
                min_y + height/2,
                f"Patch {i}\n{patch.layout_type} d={patch.code_distance}",
                ha='center', va='center',
                bbox=dict(facecolor='white', alpha=0.7)
            )
        
        plt.title(f"Multi-Patch Surface Code Layout ({len(patches)} patches)")
        plt.xlabel('x')
        plt.ylabel('y')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    def create_surface_code_environment(self, surface_code: Optional[SurfaceCodeObject] = None,
                                      **kwargs) -> SurfaceCodeEnvironment:
        """
        Create a reinforcement learning environment for surface code optimization.
        
        Args:
            surface_code: Initial surface code to use (if None, will generate one)
            **kwargs: Additional parameters to override config
            
        Returns:
            SurfaceCodeEnvironment instance
        """
        # Generate a surface code if not provided (use heuristic layer)
        if surface_code is None:
            default_distance = self.surface_code_config.get('code_distance', 3)
            default_layout = self.surface_code_config.get('layout_type', 'planar')
            surface_code = self.heuristic_layer.generate_surface_code(
                code_distance=default_distance,
                layout_type=default_layout,
                visualize=False
            )
        
        # Create and return the environment
        env = SurfaceCodeEnvironment(
            config=self.config,
            hardware_graph=self.hardware_info,
            surface_code_generator=self.heuristic_layer,
            reward_engine=self.reward_engine
        )
        
        return env

    def get_single_patch_mapping(self, code_distance: int, layout_type: str, mapping_constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Public wrapper to compute a single logical patch mapping.

        For compatibility with the TSD, this forwards to the heuristic layer's
        SurfaceCode.get_single_patch_mapping(), ensuring the same return shape
        as multi-patch mapping.

        Args:
            code_distance: desired code distance (odd integer), or None for auto-select
            layout_type: code layout type (e.g., 'planar', 'rotated', 'color')
            mapping_constraints: optional constraints dict

        Returns:
            Mapping dictionary compatible with GUI overlays.
        """
        sc = SurfaceCode(config_overrides=self.config, device_overrides=self.hardware_info)
        constraints = mapping_constraints or {}
        return sc.get_single_patch_mapping(code_distance, layout_type, constraints)

    # --- Device, Layout, and Agent Management ---
    def list_available_devices(self) -> List[str]:
        """Return all supported device names (from Device Abstraction module)."""
        # Prefer listing from provider config via DeviceAbstraction
        provider = None
        try:
            provider = (self.hardware_info.get('provider_name') or '').lower()
        except Exception:
            provider = None
        if provider:
            devices = DeviceAbstraction.list_devices(provider)
            if devices:
                return devices
        # Fallback: return the selected device as a single-item list
        selected = self.hardware_info.get('device_name')
        return [selected] if selected else []

    def list_layout_types(self) -> List[str]:
        """Return all supported surface code layout types."""
        return self.surface_code_config.get('supported_layout_types', ['planar', 'rotated'])

    def list_code_distances(self, device: str = None, layout_type: str = None) -> List[int]:
        """Return valid code distances for a given device and layout."""
        if device is None:
            device = self.hardware_info.get('device_name', 'ibm_hummingbird')
        if layout_type is None:
            layout_type = self.surface_code_config.get('layout_type', 'planar')
        
        # Calculate optimal code distances based on hardware constraints
        device_info = self.hardware_info
        max_qubits = device_info.get('max_qubits', 0)
        
        # Get logical qubit count from circuit if available
        logical_qubits = self.config.get('circuit', {}).get('logical_qubits', 1)
        
        # Calculate the maximum possible code distance
        max_distance = self.calculate_max_code_distance(max_qubits, logical_qubits, layout_type)
        
        # Return a list of valid odd distances starting from 3 up to max_distance
        valid_distances = [d for d in range(3, max_distance + 1, 2)]
        
        # If no valid distances, return at least distance 3 (minimum valid distance)
        if not valid_distances:
            valid_distances = [3]
            
        return valid_distances

    def calculate_max_code_distance(self, max_qubits: int, logical_qubits: int = 1, layout_type: str = 'rotated') -> int:
        """
        Calculate the maximum possible code distance based on hardware constraints and logical qubit requirements.
        Uses total number of qubits per patch (data + ancilla) for each layout:
          - Rotated: 2d^2-1
          - Planar: 2d^2-2d+1
          - Color: (3d^2+1)/2
        Args:
            max_qubits: Maximum number of physical qubits available on the device
            logical_qubits: Number of logical qubits required (default: 1)
            layout_type: Type of surface code layout ('planar', 'rotated', 'color')
        Returns:
            Maximum possible code distance (odd integer)
        """
        # Reserve one logical qubit for code switching
        total_logical_qubits = logical_qubits + 1
        num_patches = total_logical_qubits
        max_d = 3
        # Find the largest odd d such that total qubits for all patches <= max_qubits
        d = 3
        while True:
            if layout_type == 'planar':
                qubits_per_patch = 2 * d * d - 2 * d + 1
            elif layout_type == 'rotated':
                qubits_per_patch = 2 * d * d - 1
            elif layout_type == 'color':
                qubits_per_patch = (3 * d * d + 1) // 2
            else:
                qubits_per_patch = d * d  # fallback
            total_qubits_needed = num_patches * qubits_per_patch
            if total_qubits_needed > max_qubits:
                break
            max_d = d
            d += 2  # Only odd distances
        # Cap at a reasonable maximum (e.g., 15)
        max_d = min(max_d, 15)
        try:
            self.logger.log_event('calculated_max_code_distance', {
                'max_d': max_d,
                'layout_type': layout_type,
                'logical_qubits': logical_qubits,
                'max_qubits': max_qubits,
                'num_patches': num_patches
            }, level='DEBUG')
        except Exception:
            print(f"[DEBUG] Calculated max code distance: {max_d} for {layout_type} layout with {logical_qubits} logical qubits on {max_qubits} physical qubits (using {num_patches} patches)")
        return max_d

    def list_supported_logical_gates(self, layout_type: str = None, code_distance: int = None, logical_operators: dict = None) -> List[str]:
        """
        Return the set of logical gates that are fault-tolerantly supported by the given code.
        This is determined based on code layout, code distance, and logical operator structure.
        Never include SWAP unless natively supported.
        """
        gates = set()
        if layout_type is None:
            layout_type = self.list_layout_types()[0]
        # Always X, Z if logical operators exist
        if logical_operators is not None:
            if 'X' in logical_operators and logical_operators['X']:
                gates.add('X')
            if 'Z' in logical_operators and logical_operators['Z']:
                gates.add('Z')
        else:
            gates.update({'X', 'Z'})
        # CNOT if there are at least 2 logical qubits (multi-patch)
        if logical_operators is not None and isinstance(logical_operators.get('X', []), list):
            if len(logical_operators['X']) >= 2 or len(logical_operators['Z']) >= 2:
                gates.add('CNOT')
        else:
            gates.add('CNOT')
        # H if both X and Z present
        if 'X' in gates and 'Z' in gates:
            gates.add('H')
        # S/T if layout and code distance permit (e.g., rotated/color and d>=3)
        if layout_type in ('rotated', 'color') and (code_distance is None or code_distance >= 3):
            gates.add('S')
            gates.add('T')
        # Remove SWAP unless natively supported (not included by default)
        return sorted(gates)

    def list_trained_agents(self) -> List[Dict[str, Any]]:
        """Return metadata for all available trained agents (device, layout, distance, path)."""
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'training_artifacts'))
        agents = []
        if os.path.exists(agents_dir):
            for fname in os.listdir(agents_dir):
                if fname.endswith('.zip'):
                    parts = fname.split('_')
                    agents.append({
                        'device': parts[1] if len(parts) > 1 else '',
                        'layout': parts[2] if len(parts) > 2 else '',
                        'distance': parts[3][1:] if len(parts) > 3 and parts[3].startswith('d') else '',
                        'path': os.path.join(agents_dir, fname)
                    })
        return agents

    # --- Training ---
    def _get_artifacts_dir(self, config=None):
        output_dir = config.get('system', {}).get('output_dir', './outputs')
        return os.path.abspath(os.path.join(output_dir, 'training_artifacts'))

    def train_surface_code_agent(self, provider: str, device: str, layout_type: str, code_distance: int, config_overrides: Optional[dict] = None, log_callback=None, run_id=None) -> dict:
        if not SB3_AVAILABLE:
            raise ImportError("stable-baselines3 is required for training. Install with: pip install qcraft[full]")
        try:
            self.logger.log_event('train_surface_code_agent_called', {'provider': provider, 'device': device, 'layout': layout_type, 'code_distance': code_distance}, level='DEBUG')
        except Exception:
            print("[DEBUG][API] train_surface_code_agent CALLED")
        """
        Train an RL agent for the specified parameters. Returns dict with path to trained agent and run_id.

        If log_callback is provided (e.g., from GUI), it will be called with a dict containing:
            step, total_steps, reward, ler, eta, elapsed, progress, and optionally a 'msg' field for non-training steps.
        For terminal+GUI, mode='both' is used in ProgressBarCallback.
        """
        import time
        config = self.config
        try:
            self.logger.log_event('train_config_debug', {'config_keys': list(config.keys()), 'reward_function': config.get('reward_function')}, level='DEBUG')
        except Exception:
            print(f"[DEBUG][TRAIN] config keys: {list(config.keys())}")
            print(f"[DEBUG][TRAIN] reward_function section: {config.get('reward_function', None)}")
        mp_config = config.get('multi_patch_rl_agent', {})
        agent_config = mp_config.get('agent', {})
        env_config = mp_config.get('environment', {})
        # Enforce provider/device exclusively from hardware.json; ignore args if provided
        hw_provider = self.hardware_info.get('provider_name', 'ibm')
        hw_device = self.hardware_info.get('device_name', 'ibm_hummingbird')
        if (provider and provider != hw_provider) or (device and device != hw_device):
            try:
                self.logger.log_event('deprecated_args_ignored', {
                    'message': 'provider/device args ignored; using hardware.json values',
                    'arg_provider': provider,
                    'arg_device': device,
                    'hw_provider': hw_provider,
                    'hw_device': hw_device
                }, level='WARNING')
            except Exception:
                print(f"[WARNING][TRAIN] provider/device args ignored; using hardware.json values: provider={hw_provider}, device={hw_device}")
        provider = hw_provider
        device = hw_device
        if layout_type is None:
            layout_type = self.list_layout_types()[0]
        if code_distance is None:
            code_distance = self.list_code_distances(device, layout_type)[0]
        if run_id is None:
            run_id = str(uuid.uuid4())
        start_time = time.time()
        self.logger.log_event('run_started', {'run_id': run_id, 'provider': provider, 'device': device, 'layout_type': layout_type, 'code_distance': code_distance}, level='INFO')
        if config_overrides:
            # Patch: update agent/environment config if present
            if 'agent' in config_overrides:
                agent_config.update(config_overrides['agent'])
            if 'environment' in config_overrides:
                env_config.update(config_overrides['environment'])
        # Compute total_timesteps before defining _emit_progress_log
        total_timesteps = config.get('multi_patch_rl_agent', {}).get('agent', {}).get('num_episodes', 10000) * 200
        # Initial config/log messages only (not for training progress)
        if config_overrides and log_callback:
            progress_info = {
                "step": 0,
                "total_steps": total_timesteps,
                "reward": None,
                "ler": None,
                "eta": None,
                "elapsed": time.time() - start_time,
                "progress": 0.0,
                "msg": f"[INFO] Updated config with overrides: {config_overrides}"
            }
            log_callback(progress_info)
        if log_callback:
            progress_info = {
                "step": 0,
                "total_steps": total_timesteps,
                "reward": None,
                "ler": None,
                "eta": None,
                "elapsed": time.time() - start_time,
                "progress": 0.0,
                "msg": f"[INFO] Updated config with overrides: {config_overrides}"
            }
            log_callback(progress_info)
        device_info = self.hardware_info
        h_layer = HeuristicInitializationLayer(config, device_info)
        surface_code = h_layer.generate_surface_code(code_distance, layout_type, visualize=False)
        if log_callback:
            progress_info = {
                "step": 0,
                "total_steps": total_timesteps,
                "reward": None,
                "ler": None,
                "eta": None,
                "elapsed": time.time() - start_time,
                "progress": 0.0,
                "msg": f"[INFO] Generated surface code for layout_type={layout_type}, code_distance={code_distance}"
            }
            log_callback(progress_info)
        transformer = ConnectivityAwareGraphTransformer(
            config=config,
            hardware_graph=device_info,
            native_gates=device_info['native_gates'],
            gate_error_rates=device_info['gate_error_rates'],
            qubit_error_rates={q: device_info['qubit_properties'][q]['readout_error'] for q in device_info['qubit_properties']}
        )
        # Advanced: configurable number of parallel environments (n_envs)
        # Define make_env locally for RL environment creation
        def make_env():
            return SurfaceCodeEnvironment(
                config=config,
                hardware_graph=device_info,
                surface_code_generator=h_layer,
                reward_engine=self.reward_engine
            )
        n_envs = agent_config.get('n_envs', 4)
        # Correct total_timesteps calculation: prefer override, then config
        total_timesteps = None
        if config_overrides and 'multi_patch_rl_agent' in config_overrides and 'agent' in config_overrides['multi_patch_rl_agent'] and 'total_timesteps' in config_overrides['multi_patch_rl_agent']['agent']:
            total_timesteps = config_overrides['multi_patch_rl_agent']['agent']['total_timesteps']
        if total_timesteps is None:
            total_timesteps = config.get('multi_patch_rl_agent', {}).get('agent', {}).get('total_timesteps')
        if total_timesteps is None:
            total_timesteps = config.get('multi_patch_rl_agent', {}).get('agent', {}).get('num_episodes', 10000) * 200
        # Setup progress bar callback for both terminal and GUI
        from scode.rl_agent.progress import ProgressBarCallback
        progress_callback = ProgressBarCallback(
            total_steps=total_timesteps,
            mode='both' if log_callback else 'terminal',
            callback=log_callback if log_callback else None
        )
        if n_envs <= 1:
            env = make_env()
            if log_callback:
                log_callback({
                    "step": 0,
                    "total_steps": total_timesteps,
                    "reward": None,
                    "ler": None,
                    "eta": None,
                    "elapsed": time.time() - start_time,
                    "progress": 0.0,
                    "msg": f"[DEBUG] Using single environment (n_envs={n_envs})"
                })
        else:
            env_fns = [make_env for _ in range(n_envs)]
            env = SubprocVecEnv(env_fns)
            if log_callback:
                log_callback({
                    "step": 0,
                    "total_steps": total_timesteps,
                    "reward": None,
                    "ler": None,
                    "eta": None,
                    "elapsed": time.time() - start_time,
                    "progress": 0.0,
                    "msg": f"[DEBUG] Using SubprocVecEnv (n_envs={n_envs})"
                })

        # Initial config/log messages only (not for training progress)
        if config_overrides:
            # Initial config/log messages handled above
            pass

        # Model creation and training
        model = PPO('MultiInputPolicy', env, verbose=1, batch_size=agent_config.get('batch_size', 64), n_steps=agent_config.get('n_steps', 2048), learning_rate=agent_config.get('learning_rate', 0.0003), gamma=agent_config.get('gamma', 0.99), gae_lambda=agent_config.get('gae_lambda', 0.95), ent_coef=agent_config.get('ent_coef', 0.01), vf_coef=agent_config.get('vf_coef', 0.5))
        progress_callback = ProgressBarCallback(
            total_steps=total_timesteps,
            callback=log_callback,
            mode='both'
        )
        model.learn(total_timesteps=total_timesteps, callback=progress_callback)


        model = PPO('MultiInputPolicy', env, verbose=1, batch_size=agent_config.get('batch_size', 64), n_steps=agent_config.get('n_steps', 2048), learning_rate=agent_config.get('learning_rate', 0.0003), gamma=agent_config.get('gamma', 0.99), gae_lambda=agent_config.get('gae_lambda', 0.95), ent_coef=agent_config.get('ent_coef', 0.01), vf_coef=agent_config.get('vf_coef', 0.5))
        progress_callback = ProgressBarCallback(
            total_steps=total_timesteps,
            bar_length=40,
            print_freq=2.0,
            callback=log_callback,  # Pass log_callback for GUI integration, or None
            mode='both',
            run_id=run_id
        )
        model.learn(total_timesteps=total_timesteps, callback=progress_callback)

        # Use output_dir and artifact_naming from config
        ta_config = config.get('multi_patch_rl_agent', {}).get('training_artifacts', {})
        output_dir = ta_config.get('output_dir', './outputs/training_artifacts')
        artifact_naming = ta_config.get('artifact_naming', '{provider}_{device}_{layout_type}_d{code_distance}_patches{patch_count}_stage{curriculum_stage}_sb3_ppo_surface_code_{timestamp}.zip')
        os.makedirs(output_dir, exist_ok=True)
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        patch_count = env_config.get('patch_count', 1)
        curriculum_stage = agent_config.get('curriculum_stage', 1)
        policy_path = os.path.join(output_dir, artifact_naming.format(
            provider=provider,
            device=device,
            layout_type=layout_type,
            code_distance=code_distance,
            patch_count=patch_count,
            curriculum_stage=curriculum_stage,
            timestamp=timestamp
        ))
        model.save(policy_path)
        elapsed = time.time() - start_time
        self.logger.log_event('run_ended', {'run_id': run_id, 'policy_path': policy_path, 'elapsed': elapsed}, level='INFO')
        self.logger.store_result(run_id, {'policy_path': policy_path, 'provider': provider, 'device': device, 'layout_type': layout_type, 'code_distance': code_distance, 'elapsed': elapsed})
        if log_callback:
            log_callback(f"[INFO] Training complete. Policy saved to {policy_path}", 1.0)
        return {'policy_path': policy_path, 'run_id': run_id}

    def get_training_status(self, agent_path: str) -> dict:
        """Return training progress, metrics, and status for a given agent."""
        status = {'status': 'not_found', 'path': agent_path}
        if not os.path.exists(agent_path):
            return status
        status['status'] = 'completed'
        # Try to find a metadata/log file with the same base name
        base, _ = os.path.splitext(agent_path)
        meta_json = base + '.json'
        meta_yaml = base + '.yaml'
        meta = None
        if os.path.exists(meta_json):
            with open(meta_json, 'r') as f:
                meta = json.load(f)
        elif os.path.exists(meta_yaml):
            with open(meta_yaml, 'r') as f:
                meta = yaml.safe_load(f)
        if meta:
            status.update(meta)
        else:
            # Fallback: try to get file size and mtime
            status['artifact_size'] = os.path.getsize(agent_path)
            status['last_modified'] = os.path.getmtime(agent_path)
        return status

    # --- Code Generation & Mapping ---
    def generate_surface_code_layout(self, layout_type: str = None, code_distance: int = None, device: str = None) -> dict:
        """Generate a surface code layout for the given parameters."""
        # Use config-driven device/layout if not provided
        if device is None:
            device = self.hardware_info.get('device_name', 'ibm_hummingbird')
        if layout_type is None:
            layout_type = self.list_layout_types()[0]
        # Get logical qubit count from circuit or config
        logical_qubits = self._get_logical_qubit_count()
        # Compute valid distances and select appropriate code_distance
        code_distances = self.list_code_distances(device, layout_type)
        if not code_distances:
            try:
                self.logger.log_event('no_valid_code_distances', {'device': device, 'layout_type': layout_type}, level='ERROR')
            except Exception:
                print(f"[ERROR] No valid code distances for device {device} and layout {layout_type}")
            raise ValueError(f"No valid code distances for device {device} and layout {layout_type}")
        if code_distance is None:
            code_distance = code_distances[0]
        elif code_distance not in code_distances:
            orig_cd = code_distance
            if code_distance < code_distances[0]:
                code_distance = code_distances[0]
            elif code_distance > code_distances[-1]:
                code_distance = code_distances[-1]
            else:
                code_distance = min(code_distances, key=lambda x: abs(x - code_distance))
            try:
                self.logger.log_event('adjusted_invalid_code_distance', {'requested': orig_cd, 'adjusted_to': code_distance, 'valid': code_distances}, level='WARNING')
            except Exception:
                print(f"[WARNING] Adjusted invalid code distance {orig_cd} to {code_distance} from valid set {code_distances}")
        # Log selected/adjusted code distance
        try:
            self.logger.log_event('selected_code_distance', {'code_distance': code_distance, 'layout_type': layout_type}, level='INFO')
        except Exception:
            print(f"[INFO] Selected code distance: {code_distance} for {layout_type}")
        # Reload device info for the requested device
        device_info = self.hardware_info
        h_layer = HeuristicInitializationLayer(self.config, device_info)
        code = h_layer.generate_surface_code(code_distance, layout_type, visualize=False)
        # Log that a surface code was generated (tiny patch)
        try:
            self.logger.log_event('surface_code_generated', {
                'layout_type': layout_type,
                'code_distance': code_distance,
                'num_qubits': len(getattr(code, 'qubit_layout', {}) or {})
            }, level='INFO')
        except Exception:
            pass
        # Patch: wrap single patch as code_spaces list for FT circuit builder compatibility
        patch_dict = {
            'name': 'code_space_0',
            'qubit_layout': code.qubit_layout,
            'stabilizer_map': code.stabilizer_map,
            'logical_operators': code.logical_operators,
            'adjacency_matrix': nx.to_dict_of_lists(code.adjacency_matrix),
            'code_distance': code.code_distance,
            'layout_type': code.layout_type,
            'grid_connectivity': (
                getattr(code, 'grid_connectivity', None)
                or self.hardware_info.get('grid_connectivity')
                or self.hardware_info.get('topology_type', 'unknown')
            ),
            'topology_type': getattr(code, 'topology_type', None),
            'supported_logical_gates': getattr(code, 'supported_logical_gates', None)
        }
        return {
            **patch_dict,
            'code_spaces': [patch_dict]
        }

    def get_stabilizer_info(self, layout_type: str, code_distance: int) -> dict:
        """Return stabilizer information for the given code."""
        code = self.heuristic_layer.generate_surface_code(code_distance, layout_type, visualize=False)
        return code.stabilizer_map

    def _find_agent_artifact(self, device, layout_type, code_distance, provider=None):
        """Find the correct trained agent artifact for the given parameters."""
        config = self.config
        artifacts_dir = self._get_artifacts_dir(config)
        candidates = []
        for fname in os.listdir(artifacts_dir):
            if fname.endswith('.zip') and device in fname and layout_type in fname and f'd{code_distance}' in fname:
                if provider is None or provider in fname:
                    candidates.append(os.path.join(artifacts_dir, fname))
        if not candidates:
            raise FileNotFoundError(f"No trained agent artifact found for device={device}, layout_type={layout_type}, code_distance={code_distance}, provider={provider} in {artifacts_dir}")
        # If multiple, pick the most recent
        candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return candidates[0]

    def get_multi_patch_mapping(self, code_distance: int, layout_type: str, mapping_constraints: dict, device: str = None, use_rl_agent: bool = True, rl_policy_path: str = None) -> dict:
        if device is None:
            device = self.hardware_info.get('device_name', 'ibm_hummingbird')
        device_info = self.hardware_info
        h_layer = HeuristicInitializationLayer(self.config, device_info)
        num_patches = mapping_constraints.get('num_patches', 1)
        codes = [h_layer.generate_surface_code(code_distance, layout_type, visualize=False) for _ in range(num_patches)]
        from scode.multi_patch_mapper.multi_patch_mapper import MultiPatchMapper
        mapper = MultiPatchMapper(self.config, device_info)
        return mapper.map_patches(codes, mapping_constraints, use_rl_agent=use_rl_agent, rl_policy_path=rl_policy_path)

    def orchestrate_code_and_mapping(self, code_distance: int, layout_type: str, mapping_constraints: dict, device_config: dict, switcher_config_path: str, config_path: str) -> dict:
        from orchestration_controller.orchestrator import Orchestrator  # moved import here to avoid circular import
        orchestrator = Orchestrator(config_path, device_config, switcher_config_path)
        num_patches = mapping_constraints.get('num_patches', 1)
        codes, mapping = orchestrator.initialize_code(code_distance, layout_type, mapping_constraints)
        return {'codes': codes, 'mapping': mapping}

    # --- Evaluation & Utility ---
    def evaluate_logical_error_rate(self, mapped_circuit: dict, device: str, noise_model=None) -> float:
        """Estimate the logical error rate for a mapped circuit on a given device, using the noise model from the device config."""
        if not hasattr(self, 'evaluator') or self.evaluator is None:
            raise RuntimeError("EvaluationFramework is not available.")
        if not hasattr(self.evaluator, 'evaluate_logical_error_rate'):
            raise AttributeError("EvaluationFramework does not have 'evaluate_logical_error_rate'")
        # Always load noise_model from the device config file based on provider/device from hardware.json
        device_info = self.hardware_info
        noise_model = device_info.get('noise_model', {})
        return self.evaluator.evaluate_logical_error_rate(mapped_circuit, device, noise_model)

    # --- Visualization ---
    def visualize_surface_code(self, layout: dict) -> bytes:
        """Return an image (as bytes) for the frontend to display."""
        G = nx.Graph()
        for q, pos in layout.get('qubit_layout', {}).items():
            G.add_node(q, **pos)
        pos = {q: (v['x'], v['y']) for q, v in layout.get('qubit_layout', {}).items()}
        plt.figure(figsize=(7, 7))
        nx.draw(G, pos, node_color='lightgray', edge_color='gray', node_size=400, alpha=0.3, with_labels=True)
        plt.title(f"Surface Code Layout: d={layout.get('code_distance', '?')}, {layout.get('layout_type', '?')}")
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        return buf.read()

    # --- Utility/Validation ---
    def validate_code_for_device(self, layout_type: str, code_distance: int, device: str) -> bool:
        """Check if a given code can be implemented on the selected device (qubit count, connectivity, etc)."""
        device_info = self.hardware_info
        required_qubits = code_distance ** 2  # Simplified; real logic may differ
        return device_info.get('max_qubits', 0) >= required_qubits

    def switch_code_space(self, old_mapping: dict, new_mapping: dict, switcher_config_path: str, protocol: str = None, **kwargs) -> dict:
        switcher = CodeSwitcher(switcher_config_path)
        # Validate protocol
        import yaml
        with open(switcher_config_path, 'r') as f:
            config = yaml.safe_load(f)
        enabled_protocols = [p['name'] for p in config['switching_protocols'] if p['enabled']]
        if protocol and protocol not in enabled_protocols:
            raise ValueError(f"Protocol '{protocol}' is not enabled. Enabled protocols: {enabled_protocols}")
        return switcher.switch(old_mapping, new_mapping, protocol=protocol, **kwargs)

    def _get_logical_qubit_count(self, circuit: Optional[Dict[str, Any]] = None) -> int:
        """
        Extract the logical qubit count from the circuit or config.
        
        Args:
            circuit: Optional circuit dictionary
            
        Returns:
            Number of logical qubits required
        """
        # If circuit is provided, extract qubit count from it
        if circuit is not None:
            if 'qubits' in circuit:
                return len(circuit['qubits'])
            elif 'max_qubits' in circuit:
                return circuit['max_qubits']
        
        # Otherwise, use the value from config
        return self.config.get('circuit', {}).get('logical_qubits', 1)
    
    def update_logical_qubit_count(self, count: int) -> None:
        """
        Update the logical qubit count in the config.
        
        Args:
            count: Number of logical qubits
        """
        if 'circuit' not in self.config:
            self.config['circuit'] = {}
        self.config['circuit']['logical_qubits'] = count
        try:
            self.logger.log_event('updated_logical_qubit_count', {'count': count}, level='INFO')
        except Exception:
            print(f"[INFO] Updated logical qubit count to {count}")

    def device_has_enough_qubits(self, device_info, required_qubits):
        return device_info.get('max_qubits', 0) >= required_qubits