import unittest
from scode.reward_engine.reward_engine import RewardEngine
from configuration_management.config_manager import ConfigManager
import os

def deep_merge(base: dict, override: dict) -> dict:
    if not override:
        return base.copy()
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

class TestRewardEngine(unittest.TestCase):
    def setUp(self, config_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('surface_code')
        self.config = deep_merge(base_config, config_overrides or {})
        self.engine = RewardEngine(self.config)

    def test_compute_reward(self):
        circuit_metrics = {
            'weighted_single_qubit_gate_error': 0.005,
            'weighted_two_qubit_gate_error': 0.005,
            'weighted_gate_error': 0.01,  # legacy, ignored
            'total_swap_gates': 2,
            'circuit_depth': 10,
            'logical_error_rate': 0.001,
            'weighted_qubit_error': 0.09,
            'stabilizer_score': 0.9
        }
        reward_weights = {
            'alpha1': 1.0,
            'alpha2': 1.0,
            'beta': 1.0,
            'gamma': 1.0,
            'delta': 1.0,
            'epsilon': 1.0,
            'zeta': 1.0
        }
        reward, breakdown = self.engine.compute_reward(None, circuit_metrics, {}, reward_weights)
        self.assertIsInstance(reward, float)
        self.assertIsInstance(breakdown, dict)
        self.assertIn('weighted_single_qubit_gate_error', breakdown)
        self.assertIn('weighted_two_qubit_gate_error', breakdown)

if __name__ == '__main__':
    unittest.main() 