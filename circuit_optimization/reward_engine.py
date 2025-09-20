from typing import Dict, Any, Optional
from circuit_optimization.utils import count_gates, calculate_depth, count_swaps

class CircuitOptimizationRewardEngine:
    """
    Advanced reward engine for RL-based quantum circuit optimization.
    Considers gate count, depth, SWAPs, native gate compliance, and device-specific penalties.
    Supports reward normalization (running mean/std) if normalize_reward=True (handled in env).
    """
    def __init__(self, device_info: Dict[str, Any], reward_weights: Optional[Dict[str, float]] = None, normalize_reward: bool = False):
        self.device_info = device_info
        self.weights = reward_weights or {
            'gate_count': -1.0,
            'depth': -0.5,
            'swap_count': -2.0,
            'native_gate_bonus': 1.0,
            'invalid_gate_penalty': -5.0,
        }
        self.native_gates = set(device_info.get('native_gates', []))
        self.normalize_reward = normalize_reward

    def compute(self, circuit: Dict, prev_circuit: Optional[Dict] = None) -> float:
        # Reward based on improvement over previous circuit, or absolute if prev_circuit is None
        reward = 0.0
        if prev_circuit is not None:
            reward += self.weights['gate_count'] * (count_gates(prev_circuit) - count_gates(circuit))
            reward += self.weights['depth'] * (calculate_depth(prev_circuit) - calculate_depth(circuit))
            reward += self.weights['swap_count'] * (count_swaps(prev_circuit) - count_swaps(circuit))
        else:
            reward += self.weights['gate_count'] * count_gates(circuit)
            reward += self.weights['depth'] * calculate_depth(circuit)
            reward += self.weights['swap_count'] * count_swaps(circuit)
        # Bonus for native gates
        for gate in circuit.get('gates', []):
            if gate['name'] in self.native_gates:
                reward += self.weights['native_gate_bonus']
            else:
                reward += self.weights['invalid_gate_penalty']
        return reward
