import gymnasium as gym
from gymnasium import spaces
import numpy as np
import networkx as nx
from typing import Dict, Any, List, Tuple, Optional, Union
import copy
import random

from scode.heuristic_layer.surface_code_object import SurfaceCodeObject

from scode.rl_agent.reward_engine import MultiPatchRewardEngine
from scode.utils.decoder_interface import DecoderInterface

MAX_PATCHES = 3  # Set to the maximum number of patches you will use in curriculum
MAX_QUBITS = 65  # Set to the maximum number of qubits for your hardware
NUM_FEATURES = 5

class SurfaceCodeEnvironment(gym.Env):
    """
    Reinforcement Learning environment for surface code layout generation and optimization.
    This environment allows an RL agent to learn optimal qubit placement and connectivity
    for surface codes on specific hardware architectures.
    """
    metadata = {'render.modes': ['human', 'rgb_array']}

    def __init__(self, config: Dict[str, Any], hardware_graph: Dict[str, Any], 
                 surface_code_generator=None, reward_engine=None, device=None, logger=None):
        """
        Initialize the Surface Code RL Environment.
        
        Args:
            config: Configuration dictionary containing RL parameters
            hardware_graph: Hardware device description with connectivity and qubit properties
            surface_code_generator: Optional generator for initial surface code layouts
            reward_engine: Optional reward engine for custom reward calculation
            device: Hardware device description
            logger: Optional logger for logging metrics
        """
        super(SurfaceCodeEnvironment, self).__init__()
        
        # Set patch_count first
        self.patch_count = config.get('multi_patch_rl_agent', {}).get('environment', {}).get('patch_count', 1)
        self.config = config
        self.hardware_graph = hardware_graph
        self.device = device
        self.logger = logger
        
        # Use MultiPatchRewardEngine for multi-patch RL
        print(f"[DEBUG][ENV INIT] reward_function={config.get('reward_function', {})}")
        self.reward_engine = reward_engine if reward_engine else MultiPatchRewardEngine(config)
        
        # Extract configuration parameters
        self.surface_code_config = config.get('multi_patch_rl_agent', {}).get('environment', {})
        self.action_config = config.get('actions', {})
        
        # Current phase of curriculum learning
        self.current_phase = 0
        # Improved curriculum config loading
        if 'curriculum_learning' in config:
            self.curriculum_config = config['curriculum_learning']
            self.use_curriculum = self.curriculum_config.get('enabled', False)
            self.phases = self.curriculum_config.get('stages', [{}])
        elif 'curriculum' in config:
            self.curriculum_config = config['curriculum']
            self.use_curriculum = self.curriculum_config.get('enabled', False)
            self.phases = self.curriculum_config.get('phases', [{}])
        else:
            self.curriculum_config = {}
            self.use_curriculum = False
            self.phases = [{}]
        
        # Setup hardware graph
        self._setup_hardware_graph()
        
        # Setup action and observation spaces
        self._setup_spaces()
        
        # Initial state
        self.surface_codes = []  # List of SurfaceCodeObject, one per patch
        self.current_mappings = [{} for _ in range(self.patch_count)]
        self.episode_step_count = 0
        self.max_steps = config.get('rl_agent', {}).get('max_steps_per_episode', 100)
        
        # Surface code generator for initial layouts
        self.surface_code_generator = surface_code_generator
        
        # Performance tracking
        self.episode_rewards = []
        self.successful_episodes = 0
        self.total_episodes = 0
        
        # Action masking (for legal actions)
        self.action_masks = None
        
        # Logging and debug
        self.verbose = config.get('system', {}).get('log_level', 'INFO') == 'DEBUG'
        
        # All environment parameters are config-driven
        self.env_cfg = config.get('multi_patch_rl_agent', {}).get('environment', {})
        self.patch_cfg = config.get('multi_patch', {})
        self.reward_cfg = config.get('reward_engine', config.get('reward_function', {}))
        self.device_cfg = hardware_graph

    def _setup_hardware_graph(self):
        """Setup hardware graph from device description."""
        self.hw_graph = nx.Graph()
        
        # Add nodes (qubits)
        connectivity = self.hardware_graph.get('qubit_connectivity', {})
        qubit_properties = self.hardware_graph.get('qubit_properties', {})
        
        for qubit_id in connectivity:
            error_rate = 0.0
            if qubit_id in qubit_properties:
                error_rate = qubit_properties[qubit_id].get('readout_error', 0.0)
            self.hw_graph.add_node(int(qubit_id), error_rate=error_rate)
        
        # Add edges (connectivity)
        for qubit_id, neighbors in connectivity.items():
            for neighbor in neighbors:
                self.hw_graph.add_edge(int(qubit_id), int(neighbor))
        
        # Cache hardware properties
        self.num_hw_qubits = len(self.hw_graph.nodes())
        self.qubit_connectivity = {int(q): [int(n) for n in neighbors] 
                                  for q, neighbors in connectivity.items()}
        # Hardware constraints
        excluded_qubits = self.config.get('advanced_constraints', {}).get('exclude_qubits', [])
        self.excluded_qubits = set(excluded_qubits)
        # Debug: print hardware graph info
        print(f"[DEBUG] Hardware graph nodes: {list(self.hw_graph.nodes())}")
        print(f"[DEBUG] Number of hardware qubits: {self.num_hw_qubits}")

    def _setup_spaces(self):
        """Setup the action and observation spaces."""
        # Use fixed max values for SB3 compatibility
        self.action_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([
                MAX_PATCHES-1,  # patch_idx
                2,                  # action_type
                MAX_QUBITS-1,       # qubit1
                MAX_QUBITS-1,       # qubit2
                MAX_QUBITS-1,       # param1
                1                   # param2 (e.g., error scale)
            ], dtype=np.float32),
            dtype=np.float32
        )
        self.observation_space = spaces.Dict({
            'node_features': spaces.Box(
                low=0, high=1, 
                shape=(MAX_PATCHES * MAX_QUBITS, NUM_FEATURES), 
                dtype=np.float32
            ),
            'adjacency': spaces.Box(
                low=0, high=1, 
                shape=(MAX_PATCHES * MAX_QUBITS, MAX_QUBITS), 
                dtype=np.float32
            ),
            'action_mask': spaces.Box(
                low=0, high=1,
                shape=(MAX_PATCHES * 3, MAX_QUBITS, MAX_QUBITS),
                dtype=np.float32
            )
        })

    def reset(self, seed=None, options=None):
        """
        Reset the environment to start a new episode.
        
        Args:
            seed: Optional random seed
            options: Optional configuration overrides
            
        Returns:
            Initial observation
        """
        super().reset(seed=seed)
        
        # Enforce: Always use a real surface_code_generator, never dummy code
        if self.surface_code_generator is None:
            raise RuntimeError("SurfaceCodeEnvironment requires a real surface_code_generator. Dummy/stub code is not allowed.")
        
        # --- Curriculum learning: update patch_count from current stage if specified ---
        if self.use_curriculum and self.phases:
            # Clamp current_phase to valid range
            self.current_phase = min(self.current_phase, len(self.phases) - 1)
            stage = self.phases[self.current_phase]
            print(f"[DEBUG] Curriculum: current stage={stage}")
            if 'patch_count' in stage:
                self.patch_count = stage['patch_count']
        else:
            # Defensive: If curriculum is disabled, ensure patch_count is from config/env, not stale
            # Try to get from config in the most robust way
            patch_count_from_config = None
            # Try multi_patch_rl_agent.environment.patch_count
            patch_count_from_config = self.config.get('multi_patch_rl_agent', {}).get('environment', {}).get('patch_count')
            # Fallback: try surface_code.patch_count
            if patch_count_from_config is None:
                patch_count_from_config = self.config.get('surface_code', {}).get('patch_count')
            # Fallback: try top-level patch_count
            if patch_count_from_config is None:
                patch_count_from_config = self.config.get('patch_count')
            # Fallback: default to 1
            if patch_count_from_config is None:
                patch_count_from_config = 1
            self.patch_count = patch_count_from_config
            print(f"[DEBUG] Curriculum disabled. Using patch_count={self.patch_count} from config.")
        
        # Generate new surface code layouts for each patch
        self.surface_codes = []
        for i in range(self.patch_count):
            code_distance = self.surface_code_config.get('code_distance', 3)
            layout_type = self.surface_code_config.get('layout_type', 'planar')
            code = self.surface_code_generator.generate_surface_code(
                code_distance, layout_type, visualize=False
            )
            # Strict validation: ensure code is valid, raise error if not
            try:
                valid = code.validate(raise_error=True)
                if not valid:
                    print(f'[ERROR] Surface code for patch {i} failed validation.')
                    raise ValueError(f'Generated surface code for patch {i} is invalid. RL agent must only train on valid codes.')
            except Exception as e:
                print(f'[ERROR] Surface code validation failed for patch {i}: {e}')
                raise
            code.is_valid = True
            if not hasattr(code, 'logical_operators') or not isinstance(code.logical_operators, dict):
                code.logical_operators = {'X': [], 'Z': []}
            for op in ['X', 'Z']:
                if op not in code.logical_operators or not isinstance(code.logical_operators[op], list):
                    code.logical_operators[op] = []
            if not hasattr(code, 'adjacency_matrix') or code.adjacency_matrix is None:
                code.adjacency_matrix = nx.Graph()
            if not hasattr(code, 'qubit_layout') or not isinstance(code.qubit_layout, dict):
                code.qubit_layout = {}
            self.surface_codes.append(code)
        
        # Initialize random mappings for each patch
        self.current_mappings = []
        for code in self.surface_codes:
            mapping = self._initialize_mapping_multi_patch(code)
            self.current_mappings.append(mapping)
        
        # Reset counters
        self.episode_step_count = 0
        self.total_episodes += 1
        
        # Get initial observation
        observation = self._get_observation_multi_patch()
        self.action_masks = self._get_action_masks_multi_patch()
        
        # Debug: print patch_count and mapping/surface_codes lengths
        print(f"[DEBUG] SurfaceCodeEnvironment.reset: patch_count={self.patch_count}, len(current_mappings)={len(self.current_mappings)}, len(surface_codes)={len(self.surface_codes)}")
        for i, mapping in enumerate(self.current_mappings):
            print(f"[DEBUG] Initial mapping for patch {i}: {mapping}")
        # Return observation and action mask info
        return observation, {}

    def _initialize_mapping_multi_patch(self, code):
        """Initialize the mapping from surface code qubits to hardware qubits, prohibiting overlap across patches."""
        sc_qubits = list(code.qubit_layout.keys())
        hw_qubits = [q for q in self.hw_graph.nodes() if q not in self.excluded_qubits]
        # Track used hardware qubits across all current mappings
        used_hw_qubits = set()
        for mapping in getattr(self, 'current_mappings', []):
            used_hw_qubits.update(mapping.values())
        # Only use hardware qubits not already assigned
        available_hw_qubits = [q for q in hw_qubits if q not in used_hw_qubits]
        if len(available_hw_qubits) < len(sc_qubits):
            if self.verbose:
                print(f"Warning: Not enough available hardware qubits ({len(available_hw_qubits)}) for surface code ({len(sc_qubits)})")
            sc_qubits = sc_qubits[:len(available_hw_qubits)]
        random.shuffle(available_hw_qubits)
        mapping = {sc_q: hw_q for sc_q, hw_q in zip(sc_qubits, available_hw_qubits[:len(sc_qubits)])}
        # Assert no overlap in mapping
        if len(set(mapping.values()).intersection(used_hw_qubits)) > 0:
            raise RuntimeError("Illegal mapping: Overlap detected in _initialize_mapping_multi_patch.")
        return mapping

    def step(self, action):
        """
        Take an action in the environment.
        
        Args:
            action: The action to take
            
        Returns:
            (observation, reward, terminated, truncated, info)
        """
        self.episode_step_count += 1
        # Robustly handle action input from stable-baselines3 (may be np.ndarray)
        if isinstance(action, np.ndarray):
            action = action.flatten().tolist()
        # Extract action components
        patch_idx = int(np.clip(action[0], 0, self.patch_count - 1))
        action_type = int(action[1])
        qubit1 = int(action[2])
        qubit2 = int(action[3])
        param1 = int(action[4])
        param2 = float(action[5])
        # Apply the action
        action_result = False
        if action_type == 0:  # SWAP
            action_result = self._apply_swap_multi_patch(self.current_mappings[patch_idx], qubit1, qubit2)
        elif action_type == 1:  # REWIRE
            action_result = self._apply_rewire_multi_patch(self.current_mappings[patch_idx], qubit1, qubit2, param1)
        elif action_type == 2:  # ASSIGN_GATE
            action_result = self._apply_assign_gate_multi_patch(patch_idx, self.current_mappings[patch_idx], qubit1, qubit2, param1, param2)
        # Check for overlap after action
        all_hw = []
        for mapping in self.current_mappings:
            all_hw.extend(list(mapping.values()))
        has_overlap = len(set(all_hw)) < len(all_hw)
        if has_overlap:
            # Prohibit further steps, end episode with high penalty
            observation = self._get_observation_multi_patch()
            reward = -100.0  # Large negative penalty
            done = True
            info = {
                'mapping': self.current_mappings[patch_idx],
                'action_masks': self.action_masks,
                'episode_step': self.episode_step_count,
                'action_result': action_result,
                'connectivity_score': 0.0,
                'reward_breakdown': {'overlap_penalty': -100.0},
                'has_overlap': True
            }
            if self.verbose:
                print(f"[ENV DEBUG] Step {self.episode_step_count}: Overlap detected, terminating episode with penalty.")
            return observation, reward, done, False, info
        # Get the new observation
        observation = self._get_observation_multi_patch()
        # Calculate reward
        mapping_info = self._gather_mapping_info_multi_patch()
        is_inference = getattr(self, 'inference_mode', False)
        reward, reward_breakdown = self.reward_engine.compute_reward(mapping_info, env_info={}, is_inference=is_inference)
        # Check if episode is done
        done = self._is_episode_done_multi_patch()
        # Update action masks
        self.action_masks = self._get_action_masks_multi_patch()
        # Additional info
        info = {
            'mapping': self.current_mappings[patch_idx],
            'action_masks': self.action_masks,
            'episode_step': self.episode_step_count,
            'action_result': action_result,
            'connectivity_score': self._calculate_connectivity_score(),
            'reward_breakdown': reward_breakdown
        }
        # --- Add LER/logical_error_rate to info dict ---
        ler = None
        try:
            # Use DecoderInterface for LER
            layout = self.surface_codes[patch_idx]
            mapping = self.current_mappings[patch_idx]
            logical_ops = getattr(layout, 'logical_operators', {})
            print(f'[DEBUG] LER calculation: logical_operators={logical_ops}, mapping={mapping}')
            if not logical_ops or (not logical_ops.get('Z') and not logical_ops.get('X')):
                print('[WARNING] No logical operators defined in surface code object! LER may be meaningless.')
            noise_model = self.error_profile if hasattr(self, 'error_profile') else {'p': 0.001}
            ler = DecoderInterface.estimate_logical_error_rate(layout, mapping, noise_model, num_trials=getattr(self, 'ler_num_trials', 100), error_prob=getattr(self, 'ler_noise_prob', 0.001))
        except Exception as e:
            if self.verbose:
                print(f"[LER ERROR] {e}")
            ler = None
        if ler is not None:
            info['ler'] = ler
            info['logical_error_rate'] = ler
        # Debug print for reward and LER
        if self.verbose:
            print(f"[ENV DEBUG] Step {self.episode_step_count}: reward={reward:.4f}, LER={ler}")
        # Record success if done
        if done:
            self.episode_rewards.append(reward)
            info['success'] = self._is_successful_mapping()
            if info['success']:
                self.successful_episodes += 1
        return observation, reward, done, False, info

    def _apply_swap_multi_patch(self, mapping, qubit1, qubit2):
        """Swap the mapping of two surface code qubits."""
        # Check if both qubits are in the mapping
        if qubit1 not in mapping or qubit2 not in mapping:
            return False
        
        # Swap the mapping
        mapping[qubit1], mapping[qubit2] = mapping[qubit2], mapping[qubit1]
        
        return True

    def _apply_rewire_multi_patch(self, mapping, qubit1, qubit2, target_hw_qubit):
        """Rewire a surface code qubit to a different hardware qubit."""
        # Check if qubits are in the mapping
        if qubit1 not in mapping or qubit2 not in mapping:
            return False
            
        # Check if target hardware qubit is valid and not in use
        if target_hw_qubit not in self.hw_graph.nodes() or \
           target_hw_qubit in mapping.values() or \
           target_hw_qubit in self.excluded_qubits:
            return False
        
        # Check if the target hardware qubit is connected to qubit2's hardware qubit
        hw_qubit2 = mapping[qubit2]
        if not self.hw_graph.has_edge(target_hw_qubit, hw_qubit2):
            return False
        
        # Update mapping
        mapping[qubit1] = target_hw_qubit
        
        return True

    def _apply_assign_gate_multi_patch(self, patch_idx, mapping, qubit1, qubit2, gate_idx, error_scale):
        """Assign a gate to a pair of qubits, potentially adjusting error rates."""
        # Check if qubits are in the mapping and connected
        if qubit1 not in mapping or qubit2 not in mapping:
            return False
            
        # Check if qubits are connected in the surface code
        sc_graph = self.surface_codes[patch_idx].adjacency_matrix
        if not sc_graph.has_edge(qubit1, qubit2):
            return False
            
        # Check if the corresponding hardware qubits are connected
        hw_qubit1 = mapping[qubit1]
        hw_qubit2 = mapping[qubit2]
        if not self.hw_graph.has_edge(hw_qubit1, hw_qubit2):
            return False
            
        # Simplified gate assignment (success without actually modifying anything)
        return True

    def _get_observation_multi_patch(self):
        """Generate the current observation."""
        # Use fixed max values for SB3 compatibility
        max_qubits = MAX_QUBITS
        patch_count = self.patch_count
        node_features = np.zeros((patch_count, max_qubits, NUM_FEATURES), dtype=np.float32)
        adjacency = np.zeros((patch_count, max_qubits, max_qubits), dtype=np.float32)
        for i, code in enumerate(self.surface_codes):
            for hw_q in code.qubit_layout:
                if hw_q >= max_qubits:
                    continue
                error_rate = code.qubit_layout[hw_q].get('error_rate', 0.0)
                node_features[i, hw_q, 0] = error_rate
                qubit_type_idx = 4  # Default to unassigned
                for sc_q, hw_map_q in self.current_mappings[i].items():
                    if hw_map_q == hw_q:
                        sc_type = code.qubit_layout[sc_q].get('type', '')
                        if sc_type == 'data':
                            qubit_type_idx = 1
                        elif sc_type == 'ancilla_X':
                            qubit_type_idx = 2
                        elif sc_type == 'ancilla_Z':
                            qubit_type_idx = 3
                        break
                node_features[i, hw_q, qubit_type_idx] = 1.0
                for neighbor in self.hw_graph.neighbors(hw_q):
                    if neighbor < max_qubits:
                        adjacency[i, hw_q, neighbor] = 1.0
        action_masks = self._get_action_masks_multi_patch()
        # Flatten patch dimension
        node_features_flat = node_features.reshape(patch_count * max_qubits, NUM_FEATURES)
        adjacency_flat = adjacency.reshape(patch_count * max_qubits, max_qubits)
        # Pad to max shape
        node_features_padded = np.zeros((MAX_PATCHES * MAX_QUBITS, NUM_FEATURES), dtype=np.float32)
        adjacency_padded = np.zeros((MAX_PATCHES * MAX_QUBITS, MAX_QUBITS), dtype=np.float32)
        node_features_padded[:node_features_flat.shape[0], :node_features_flat.shape[1]] = node_features_flat
        adjacency_padded[:adjacency_flat.shape[0], :adjacency_flat.shape[1]] = adjacency_flat
        action_masks_padded = np.zeros((MAX_PATCHES * 3, MAX_QUBITS, MAX_QUBITS), dtype=np.float32)
        action_masks_padded[:action_masks.shape[0], :action_masks.shape[1], :action_masks.shape[2]] = action_masks
        return {
            'node_features': node_features_padded,
            'adjacency': adjacency_padded,
            'action_mask': action_masks_padded
        }

    def _get_action_masks_multi_patch(self):
        max_qubits = MAX_QUBITS
        patch_count = self.patch_count
        action_masks = np.zeros((patch_count, 3, max_qubits, max_qubits), dtype=np.float32)
        for i, mapping in enumerate(self.current_mappings):
            sc_qubits = list(mapping.keys())
            for a_type in range(3):
                for q1 in sc_qubits:
                    for q2 in sc_qubits:
                        if q1 != q2:
                            action_masks[i, a_type, q1, q2] = 1.0
        # Flatten patch dimension
        action_masks_flat = action_masks.reshape(patch_count * 3, max_qubits, max_qubits)
        return action_masks_flat

    def _calculate_connectivity_score(self) -> float:
        """Calculate how well the surface code connectivity is preserved in the hardware mapping."""
        # Count preserved edges
        preserved_edges = 0
        total_edges = 0
        
        for sc_q1, sc_q2 in self.surface_codes[0].adjacency_matrix.edges():
            total_edges += 1
            
            if sc_q1 in self.current_mappings[0] and sc_q2 in self.current_mappings[0]:
                hw_q1 = self.current_mappings[0][sc_q1]
                hw_q2 = self.current_mappings[0][sc_q2]
                
                if self.hw_graph.has_edge(hw_q1, hw_q2):
                    preserved_edges += 1
        
        return preserved_edges / max(1, total_edges)

    def _is_episode_done_multi_patch(self) -> bool:
        """Check if the episode is complete."""
        # Check step limit
        if self.episode_step_count >= self.max_steps:
            return True
        # Check if all patches are fully mapped
        all_mapped = True
        for i, code in enumerate(self.surface_codes):
            mapping = self.current_mappings[i] if i < len(self.current_mappings) else {}
            if len(mapping) < len(getattr(code, 'qubit_layout', {})):
                all_mapped = False
                break
        if not all_mapped:
            return False
        # Check if mapping is successful (good enough connectivity)
        if self._is_successful_mapping():
            return True
        return False

    def _is_successful_mapping(self) -> bool:
        """Check if the current mapping is considered successful."""
        # Current phase success criteria
        phase = self.phases[self.current_phase]
        criteria = phase.get('criteria', {})
        
        # Check connectivity score against threshold
        connectivity_score = self._calculate_connectivity_score()
        conn_threshold = criteria.get('hardware_compatibility', 0.8)
        
        return connectivity_score >= conn_threshold

    def update_curriculum(self):
        """Update the curriculum phase if criteria are met."""
        if not self.use_curriculum or self.current_phase >= len(self.phases) - 1:
            return
        
        # Get current phase criteria
        phase = self.phases[self.current_phase]
        criteria = phase.get('criteria', {})
        
        # Check success rate
        success_rate = self.successful_episodes / max(1, self.total_episodes)
        valid_layouts_threshold = criteria.get('valid_layouts', 0.8)
        
        # Check reward convergence
        reward_variance = np.var(self.episode_rewards[-10:]) if len(self.episode_rewards) >= 10 else float('inf')
        variance_threshold = criteria.get('reward_variance', 0.05)
        
        # Advance to next phase if criteria met
        if success_rate >= valid_layouts_threshold and reward_variance <= variance_threshold:
            self.current_phase += 1
            
            if self.verbose:
                print(f"Advancing to curriculum phase {self.current_phase + 1}: "
                      f"{self.phases[self.current_phase].get('name', 'Unnamed')}")
            
            # Reset counters for new phase
            self.successful_episodes = 0
            self.total_episodes = 0
            self.episode_rewards = []

    def render(self, mode='human'):
        """Render the current state."""
        if mode == 'human':
            # Print the current mapping
            print("Surface Code to Hardware Mapping:")
            for i, (code, mapping) in enumerate(zip(self.surface_codes, self.current_mappings)):
                print(f"Patch {i}:")
                for sc_q, hw_q in mapping.items():
                    sc_type = code.qubit_layout[sc_q].get('type', '')
                    print(f"SC qubit {sc_q} ({sc_type}) -> HW qubit {hw_q}")
            
            # Print connectivity score
            print(f"Connectivity score: {self._calculate_connectivity_score():.4f}")
            
            return None
        
        elif mode == 'rgb_array':
            # Return a simple representation of the mapping (dummy implementation)
            return np.zeros((84, 84, 3), dtype=np.uint8)
        
        else:
            raise ValueError(f"Unsupported render mode: {mode}")

    def _gather_mapping_info_multi_patch(self):
        info = {'is_valid': True, 'has_overlap': False, 'connectivity_score': 0, 'adjacency_score': 0, 'inter_patch_distance': 0, 'resource_utilization': 0}
        all_hw = []
        for mapping in self.current_mappings:
            all_hw.extend(list(mapping.values()))
        print(f"[DEBUG] _gather_mapping_info_multi_patch: current_mappings={self.current_mappings}")
        if len(set(all_hw)) < len(all_hw):
            raise RuntimeError("Illegal mapping: Physical qubit overlap detected across patches. Training/inference halted.")
            info['has_overlap'] = True
            info['is_valid'] = False
        # Compute connectivity and adjacency scores using device config
        try:
            info['connectivity_score'] = self._compute_connectivity_score()
        except Exception:
            info['connectivity_score'] = 0.0
        try:
            info['adjacency_score'] = self._compute_adjacency_score()
        except Exception:
            info['adjacency_score'] = 0.0
        try:
            info['inter_patch_distance'] = self._compute_inter_patch_distance()
        except Exception:
            info['inter_patch_distance'] = 0.0
        try:
            info['resource_utilization'] = self._compute_resource_utilization()
        except Exception:
            info['resource_utilization'] = 0.0
        # Advanced metrics
        error_rates = []
        for mapping in self.current_mappings:
            for hw_q in mapping.values():
                try:
                    error_rates.append(self.hw_graph.nodes[hw_q].get('error_rate', 0.0))
                except Exception:
                    error_rates.append(0.0)
        info['avg_error_rate'] = float(np.mean(error_rates)) if error_rates else 0.0
        logical_scores = []
        for i, code in enumerate(self.surface_codes):
            logical_x = getattr(code, 'logical_operators', {}).get('X', []) if hasattr(code, 'logical_operators') else []
            logical_z = getattr(code, 'logical_operators', {}).get('Z', []) if hasattr(code, 'logical_operators') else []
            mapping = self.current_mappings[i] if i < len(self.current_mappings) else {}
            x_mapped = sum(1 for q in logical_x if q in mapping)
            z_mapped = sum(1 for q in logical_z if q in mapping)
            x_ratio = x_mapped / max(1, len(logical_x)) if logical_x else 0.0
            z_ratio = z_mapped / max(1, len(logical_z)) if logical_z else 0.0
            logical_scores.append((x_ratio + z_ratio) / 2.0)
        info['logical_operator_score'] = float(np.mean(logical_scores)) if logical_scores else 0.0
        mapped_qubits = sum(len(mapping) for mapping in self.current_mappings)
        total_qubits = sum(len(getattr(code, 'qubit_layout', {})) for code in self.surface_codes)
        info['mapped_qubits'] = mapped_qubits
        info['total_qubits'] = total_qubits
        print(f"[DEBUG] _gather_mapping_info_multi_patch: info={info}")
        # Remove debug prints for mapping completeness and validity
        mapped_graph = nx.Graph()
        for i, code in enumerate(self.surface_codes):
            mapping = self.current_mappings[i] if i < len(self.current_mappings) else {}
            adj = getattr(code, 'adjacency_matrix', nx.Graph())
            if adj is None:
                adj = nx.Graph()
            for sc_q1, sc_q2 in adj.edges():
                if sc_q1 in mapping and sc_q2 in mapping:
                    mapped_graph.add_edge(mapping[sc_q1], mapping[sc_q2])
            mapped_graph.add_nodes_from(mapping.values())
        try:
            info['num_components'] = nx.number_connected_components(mapped_graph)
        except Exception:
            info['num_components'] = 0
        info['num_nodes'] = mapped_graph.number_of_nodes()
        # Add any custom, config-driven metrics
        for term in self.reward_cfg.get('custom_terms', []):
            name = term.get('name')
            value = getattr(self, f'_compute_{name}', lambda: 0)()
            info[name] = value
        # LER calculation during inference
        self.inference_mode = True
        if hasattr(self, 'inference_mode') and self.inference_mode:
            try:
                from scode.utils.decoder_interface import DecoderInterface
                lers = []
                for i, code in enumerate(self.surface_codes):
                    mapping = self.current_mappings[i] if i < len(self.current_mappings) else {}
                    noise_model = getattr(self, 'error_profile', {'p': 0.001})
                    ler = DecoderInterface.estimate_logical_error_rate(code, mapping, noise_model, num_trials=getattr(self, 'ler_num_trials', 100), error_prob=getattr(self, 'ler_noise_prob', 0.001))
                    if ler is not None:
                        lers.append(ler)
                info['logical_error_rate'] = float(np.mean(lers)) if lers else None
            except Exception as e:
                info['logical_error_rate'] = None
        if self.logger:
            self.logger.log_metric('mapping_info', info)
        return info

    def _compute_connectivity_score(self) -> float:
        # Count preserved edges
        preserved_edges = 0
        total_edges = 0
        
        for sc_q1, sc_q2 in self.surface_codes[0].adjacency_matrix.edges():
            total_edges += 1
            
            if sc_q1 in self.current_mappings[0] and sc_q2 in self.current_mappings[0]:
                hw_q1 = self.current_mappings[0][sc_q1]
                hw_q2 = self.current_mappings[0][sc_q2]
                
                if self.hw_graph.has_edge(hw_q1, hw_q2):
                    preserved_edges += 1
        
        return preserved_edges / max(1, total_edges)

    def _compute_adjacency_score(self) -> float:
        # Count adjacent pairs
        adjacent_pairs = 0
        total_edges = 0
        
        for sc_q1, sc_q2 in self.surface_codes[0].adjacency_matrix.edges():
            total_edges += 1
            
            if sc_q1 in self.current_mappings[0] and sc_q2 in self.current_mappings[0]:
                hw_q1 = self.current_mappings[0][sc_q1]
                hw_q2 = self.current_mappings[0][sc_q2]
                
                if self.hw_graph.has_edge(hw_q1, hw_q2):
                    adjacent_pairs += 1
        
        return adjacent_pairs / max(1, total_edges)

    def _compute_inter_patch_distance(self) -> float:
        # Calculate inter-patch distance
        patch_centers = []
        for mapping in self.current_mappings:
            xs = [self.hw_graph.nodes[q]['error_rate'] if 'error_rate' in self.hw_graph.nodes[q] else 0 for q in mapping.values()]
            if xs:
                patch_centers.append(np.mean(xs))
        if len(patch_centers) > 1:
            return float(np.abs(patch_centers[0] - patch_centers[1]))
        else:
            return 0.0

    def _compute_resource_utilization(self) -> float:
        # Count unique hardware qubits used
        all_hw = []
        for mapping in self.current_mappings:
            all_hw.extend(list(mapping.values()))
        return len(set(all_hw)) / self.num_hw_qubits if self.num_hw_qubits else 0.0 