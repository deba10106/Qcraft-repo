import gymnasium as gym
import numpy as np
from typing import Dict, Any, Optional
from circuit_optimization.utils import count_gates, calculate_depth, count_swaps, decompose_to_native_gates

from circuit_optimization.reward_engine import CircuitOptimizationRewardEngine

# Uses gymnasium, not gym
class CircuitOptimizationEnvironment(gym.Env):
    """
    Advanced RL environment for quantum circuit optimization.
    Observation: Encodes the circuit and device state as a feature vector.
    Action: Discrete set of optimization actions (e.g., gate fusion, swap insertion, commutation, mapping, etc.).
    Reward: Computed by CircuitOptimizationRewardEngine based on circuit improvement.
    Supports reward normalization (running mean/std) and curriculum learning.
    """
    metadata = {'render.modes': ['human']}

    def __init__(self, circuit: Dict, device_info: Dict, action_space_size: int = 8, reward_weights: Optional[Dict[str, float]] = None, curriculum: Optional[dict] = None, normalize_reward: bool = False):
        super().__init__()
        self.device_info = device_info
        self.original_circuit = circuit
        self.current_circuit = circuit.copy()
        self.prev_circuit = None
        self.action_space = gym.spaces.Discrete(action_space_size)
        # Observation: [gate_count, depth, swap_count, native_gate_frac, ...device-specific features]
        self.observation_space = gym.spaces.Box(low=0, high=1000, shape=(5,), dtype=np.float32)
        self.reward_engine = CircuitOptimizationRewardEngine(device_info, reward_weights, normalize_reward=normalize_reward)
        self.steps = 0
        self.max_steps = 50
        # Reward normalization state
        self.reward_running_mean = 0.0
        self.reward_running_var = 1.0
        self.reward_count = 1
        # Curriculum learning support
        self.curriculum = curriculum or None
        self.curriculum_level = 0
        self.curriculum_schedule = self.curriculum.get('schedule', []) if self.curriculum else []
        self.curriculum_progress = 0

    def reset(self, *, seed=None, options=None, **kwargs):
        """
        Reset the environment. Compatible with Gymnasium/Stable-Baselines3 vectorized envs.
        Accepts 'seed', 'options', and arbitrary kwargs.
        """
        if seed is not None:
            import numpy as np
            np.random.seed(seed)
        self.current_circuit = self.original_circuit.copy()
        self.prev_circuit = None
        self.steps = 0
        # Optionally handle options/kwargs for curriculum or other features
        obs = self._get_obs()
        info = {}
        return obs, info

    def step(self, action):
        self.prev_circuit = self.current_circuit.copy()
        # Apply the selected optimization action
        self.current_circuit = self._apply_action(self.current_circuit, action)
        obs = self._get_obs()
        reward = self.reward_engine.compute(self.current_circuit, self.prev_circuit)
        # Reward normalization using running mean/std
        if getattr(self.reward_engine, 'normalize_reward', False):
            self.reward_count += 1
            prev_mean = self.reward_running_mean
            self.reward_running_mean += (reward - self.reward_running_mean) / self.reward_count
            self.reward_running_var += (reward - prev_mean) * (reward - self.reward_running_mean)
            std = max(np.sqrt(self.reward_running_var / self.reward_count), 1e-6)
            reward = (reward - self.reward_running_mean) / std
        self.steps += 1
        # Curriculum learning progression
        if self.curriculum:
            self.curriculum_progress += 1
            if self.curriculum_level < len(self.curriculum_schedule) - 1 and self.curriculum_progress >= self.curriculum_schedule[self.curriculum_level]:
                self.curriculum_level = min(self.curriculum_level + 1, len(self.curriculum_schedule) - 1)
                self.curriculum_progress = 0
                # Optionally update environment difficulty here
        # Gymnasium API: return obs, reward, terminated, truncated, info
        terminated = self._is_optimized()  # True if task is solved
        truncated = self.steps >= self.max_steps  # True if max steps reached
        info = {
            'gate_count': count_gates(self.current_circuit),
            'depth': calculate_depth(self.current_circuit),
            'swap_count': count_swaps(self.current_circuit),
            'curriculum_level': self.curriculum_level if self.curriculum else None
        }
        return obs, reward, terminated, truncated, info

    def _get_obs(self):
        gate_count = count_gates(self.current_circuit)
        depth = calculate_depth(self.current_circuit)
        swap_count = count_swaps(self.current_circuit)
        native_gates = sum(1 for g in self.current_circuit.get('gates', []) if g['name'] in self.device_info.get('native_gates', []))
        total_gates = len(self.current_circuit.get('gates', []))
        native_gate_frac = native_gates / total_gates if total_gates > 0 else 0.0
        # Placeholder for device-specific features (extend as needed)
        device_features = [self.device_info.get('max_qubits', 0)]
        return np.array([gate_count, depth, swap_count, native_gate_frac, *device_features], dtype=np.float32)

    def _apply_action(self, circuit: Dict, action: int) -> Dict:
        # Map action index to optimization pass
        # 0: Gate fusion, 1: Commutation, 2: SWAP insertion, 3: Scheduling, 4: Qubit mapping, etc.
        # For demonstration, call utility functions (expand as needed)
        if action == 0:
            from circuit_optimization.utils import fuse_gates
            return fuse_gates(circuit)
        elif action == 1:
            from circuit_optimization.utils import commute_gates
            return commute_gates(circuit)
        elif action == 2:
            from circuit_optimization.utils import insert_swaps
            return insert_swaps(circuit)
        elif action == 3:
            from circuit_optimization.utils import schedule_gates
            return schedule_gates(circuit)
        elif action == 4:
            from circuit_optimization.utils import map_qubits
            return map_qubits(circuit)
        elif action == 5:
            from circuit_optimization.utils import decompose_to_native_gates
            return decompose_to_native_gates(circuit, set(self.device_info.get('native_gates', [])))
        elif action == 6:
            from circuit_optimization.utils import remove_redundant_gates
            return remove_redundant_gates(circuit)
        elif action == 7:
            from circuit_optimization.utils import optimize_measurements
            return optimize_measurements(circuit)
        else:
            return circuit

    def _is_optimized(self):
        # Advanced stopping criterion: no further improvement in reward or circuit metrics
        if self.prev_circuit is None:
            return False
        prev_metrics = (count_gates(self.prev_circuit), calculate_depth(self.prev_circuit), count_swaps(self.prev_circuit))
        curr_metrics = (count_gates(self.current_circuit), calculate_depth(self.current_circuit), count_swaps(self.current_circuit))
        return curr_metrics >= prev_metrics

    def render(self, mode='human'):
        print(f"Step {self.steps}: Gate count={count_gates(self.current_circuit)}, Depth={calculate_depth(self.current_circuit)}, SWAPs={count_swaps(self.current_circuit)}")
        # Optionally visualize the circuit graphically
