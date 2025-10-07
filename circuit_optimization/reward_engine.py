from typing import Dict, Optional
from circuit_optimization.utils import count_gates, calculate_depth, count_swaps


class CircuitOptimizationRewardEngine:
    def __init__(self, device_info: Dict, reward_weights: Optional[Dict[str, float]] = None, normalize_reward: bool = False):
        self.device_info = device_info or {}
        # Default weights favor gate- and depth-reduction; SWAPs are mildly penalized
        self.weights = reward_weights or {
            'gate_count': 1.0,
            'depth': 0.5,
            'swap_count': 0.2,
            'native_gate_bonus': 0.01,
            'invalid_gate_penalty': -0.01,
        }
        # Native gates per device
        self.native_gates = set((self.device_info.get('native_gates') or []))
        self.normalize_reward = normalize_reward

    def compute(self, circuit: Dict, prev_circuit: Optional[Dict] = None) -> float:
        """Compute reward based on improvement between prev and current circuit.

        If prev_circuit is None, use absolute negative metrics to avoid incentivizing bloat.
        Add a small bonus for native-gate usage and penalty for non-native gates.
        """
        reward = 0.0
        if prev_circuit is not None:
            reward += self.weights['gate_count'] * (count_gates(prev_circuit) - count_gates(circuit))
            reward += self.weights['depth'] * (calculate_depth(prev_circuit) - calculate_depth(circuit))
            reward += self.weights['swap_count'] * (count_swaps(prev_circuit) - count_swaps(circuit))
        else:
            # Encourage smaller circuits when no baseline is available
            reward += -self.weights['gate_count'] * count_gates(circuit)
            reward += -self.weights['depth'] * calculate_depth(circuit)
            reward += -self.weights['swap_count'] * count_swaps(circuit)

        # Native gate shaping
        for gate in circuit.get('gates', []):
            name = (gate.get('name') or '').upper()
            if name in self.native_gates:
                reward += self.weights['native_gate_bonus']
            else:
                reward += self.weights['invalid_gate_penalty']

        return float(reward)
