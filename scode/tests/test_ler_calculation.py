import unittest
import networkx as nx
import numpy as np
from scode.rl_agent.environment import SurfaceCodeEnvironment
from scode.rl_agent.reward_engine import MultiPatchRewardEngine
from scode.reward_engine.reward_engine import RewardEngine
from scode.environment.multi_patch_env import MultiPatchEnvironment
from typing import Dict, Any

class TestLERCalculation(unittest.TestCase):
    def setUp(self):
        """Set up test environment with mock surface code and device."""
        # Mock configuration
        self.config = {
            'device': {
                'connectivity': [(0,1), (1,2), (2,3), (3,4), (0,5), (5,6), (6,7), (7,8), (8,9)],
                'error_rates': {str(i): 0.01 for i in range(10)}
            },
            'reward_engine': {
                'ler_calculation': {
                    'num_verification_rounds': 100,
                    'error_threshold': 0.1,
                    'use_stim': True,
                    'use_pymatching': True
                }
            },
            'environment': {
                'inference': {
                    'calculate_ler': True,
                    'ler_threshold': 0.1,
                    'min_verification_rounds': 50
                }
            },
            'system': {
                'log_level': 'DEBUG'
            },
            'multi_patch_rl_agent': {
                'environment': {
                    'patch_count': 2
                }
            }
        }
        
        # Create mock surface code
        self.surface_code = MockSurfaceCode()
        
        # Initialize environment
        self.env = SurfaceCodeEnvironment(self.config, {}, reward_engine=MultiPatchRewardEngine(self.config))
        self.env.surface_code = self.surface_code
        self.env.set_inference_mode(True)
        
        # Initialize reward engine
        self.reward_engine = RewardEngine(self.config)
        
    def test_ler_calculation_basic(self):
        """Test basic LER calculation functionality."""
        # Create simple mapping
        mapping = {
            0: {0: 0, 1: 1, 2: 2},  # patch_id -> {logical_qubit -> physical_qubit}
            1: {0: 3, 1: 4, 2: 5}
        }
        
        # Calculate LER
        ler = self.reward_engine.calculate_ler(
            self.surface_code,
            mapping,
            self.env.device_graph
        )
        
        # Verify LER is calculated and in valid range
        self.assertIsNotNone(ler)
        self.assertGreaterEqual(ler, 0.0)
        self.assertLessEqual(ler, 1.0)
        
    def test_ler_during_inference(self):
        """Test LER calculation during environment inference."""
        # Set up initial state
        obs = self.env.reset()
        
        # Perform some actions
        actions = [
            {'patch_id': 0, 'logical_qubit': 0, 'physical_qubit': 0},
            {'patch_id': 0, 'logical_qubit': 1, 'physical_qubit': 1},
            {'patch_id': 0, 'logical_qubit': 2, 'physical_qubit': 2}
        ]
        
        for action in actions:
            obs, reward, done, info = self.env.step(action)
            
            # Verify LER is calculated and included in info
            self.assertIn('logical_error_rate', info)
            if info['logical_error_rate'] is not None:
                self.assertGreaterEqual(info['logical_error_rate'], 0.0)
                self.assertLessEqual(info['logical_error_rate'], 1.0)
                
    def test_ler_threshold_effect(self):
        """Test that LER threshold affects rewards during inference."""
        # Set very low LER threshold
        self.env.ler_threshold = 0.001
        
        # Perform action that should trigger threshold
        action = {'patch_id': 0, 'logical_qubit': 0, 'physical_qubit': 0}
        obs, reward, done, info = self.env.step(action)
        
        # Verify reward is minimum if LER exceeds threshold
        if info['logical_error_rate'] is not None and info['logical_error_rate'] > self.env.ler_threshold:
            self.assertEqual(reward, self.reward_engine.min_reward_inference)
            
    def test_stim_circuit_generation(self):
        """Test Stim circuit generation for surface code."""
        # Create simple mapping
        mapping = {0: {0: 0, 1: 1, 2: 2}}
        
        # Generate circuit
        circuit = self.reward_engine._generate_stim_circuit(self.surface_code, mapping)
        
        # Verify circuit is valid
        self.assertIsNotNone(circuit)
        self.assertTrue(len(str(circuit)) > 0)
        
class MockSurfaceCode:
    """Mock surface code for testing."""
    def __init__(self):
        self.qubit_layout = {0: [0,1,2], 1: [3,4,5]}
        self.stabilizers = [
            {'type': 'X', 'qubits': [0,1,2]},
            {'type': 'Z', 'qubits': [3,4,5]}
        ]
        self.logical_operators = [
            {'type': 'X', 'qubits': [0,3]},
            {'type': 'Z', 'qubits': [2,5]}
        ]
        self.patches = {
            '0': {
                'data_qubits': [0,1,2],
                'ancilla_qubits': [],
                'connectivity': [(0,1), (1,2)]
            },
            '1': {
                'data_qubits': [3,4,5],
                'ancilla_qubits': [],
                'connectivity': [(3,4), (4,5)]
            }
        }

if __name__ == '__main__':
    unittest.main() 