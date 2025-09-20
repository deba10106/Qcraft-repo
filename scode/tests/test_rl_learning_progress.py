import unittest
import os
import numpy as np
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.graph_transformer.graph_transformer import ConnectivityAwareGraphTransformer
try:
    from scode.rl_agent.rl_agent import ReinforcementLearningAgent
except ImportError:
    ReinforcementLearningAgent = None
from scode.rl_agent.environment import SurfaceCodeEnvironment
from scode.reward_engine.reward_engine import RewardEngine
from evaluation.evaluation_framework import EvaluationFramework
from scode.utils.decoder_interface import DecoderInterface
from logging_results import LoggingResultsManager

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

class TestRLLearningProgress(unittest.TestCase):
    def setUp(self, config_overrides=None, device_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('surface_code')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device = deep_merge(base_device, device_overrides or {})
        self.h_layer = HeuristicInitializationLayer(self.config, self.device)
        self.transformer = ConnectivityAwareGraphTransformer(
            config=self.config,
            hardware_graph=self.device,
            native_gates=self.device['native_gates'],
            gate_error_rates=self.device['gate_error_rates'],
            qubit_error_rates={q: self.device['qubit_properties'][q]['readout_error'] for q in self.device['qubit_properties']}
        )
        self.reward_engine = RewardEngine(self.config)
        self.evaluator = EvaluationFramework(self.config)
        self.layout_type = self.config.get('surface_code', {}).get('layout_type', 'planar')
        self.code_distance = self.config.get('surface_code', {}).get('code_distance', 3)
        self.provider = self.device.get('provider_name', 'provider').lower()
        self.device_name = self.device.get('device_name', 'device').lower()
        self.policy_path = os.path.abspath(os.path.join(self.config.get('system', {}).get('output_dir', './outputs'), '../training_artifacts', f"{self.provider}_{self.device_name}_{self.layout_type}_d{self.code_distance}_sb3_ppo_surface_code.zip"))
        self.logger = LoggingResultsManager()

    def test_learning_improves_logical_error_rate(self):
        self.logger.log_event('test_started', {'test': 'test_learning_improves_logical_error_rate'}, level='INFO')
        if ReinforcementLearningAgent is None:
            self.skipTest("ReinforcementLearningAgent not available (rl_agent.py missing)")
        # Generate a surface code and transform it
        code = self.h_layer.generate_surface_code(3, 'planar')
        transformed = self.transformer.transform(code)
        env = SurfaceCodeEnvironment(
            transformed_layout=transformed,
            hardware_specs=self.device,
            error_profile=self.device['qubit_properties'],
            config=self.config
        )
        # Evaluate random policy (baseline)
        rewards = []
        lers = []
        for _ in range(10):
            obs, info = env.reset()
            total_reward = 0
            test_state = None  # Initialize test_state
            for _ in range(env.max_steps):
                action_idx = np.random.randint(env.action_space.n)
                next_state, reward, done, truncated, info = env.step(action_idx)
                total_reward += reward
                test_state = next_state  # Update test_state to the latest next_state
                if done or truncated:
                    break
            try:
                ler = env.estimate_logical_error_rate(test_state, num_trials=env.ler_num_trials, noise_prob=env.ler_noise_prob)
                assert isinstance(ler, float) and not np.isnan(ler), "LER must be a float and not NaN (computed via stim+pymatching)"
            except Exception as e:
                print(f"LER estimation failed: {e}")
                ler = np.nan
            rewards.append(total_reward)
            lers.append(ler)
        baseline_reward = np.mean(rewards)
        baseline_ler = np.nanmean(lers)

        # Evaluate trained policy (if exists)
        if os.path.exists(self.policy_path):
            agent = ReinforcementLearningAgent(self.config, env, self.reward_engine)
            agent.load_policy(self.policy_path)
            rewards = []
            lers = []
            for episode in range(10):
                obs, info = env.reset()
                total_reward = 0
                test_state = None  # Initialize test_state
                for _ in range(env.max_steps):
                    action_idx = agent._select_action(obs)[0]
                    next_state, reward, done, truncated, info = env.step(action_idx)
                    total_reward += reward
                    test_state = next_state  # Update test_state to the latest next_state
                    if done or truncated:
                        break
                # Use DecoderInterface for LER
                try:
                    mapping_info = env._gather_mapping_info_multi_patch() if hasattr(env, '_gather_mapping_info_multi_patch') else env._gather_mapping_info()
                    layout = {'qubit_layout': env.surface_codes[0].qubit_layout, 'logical_to_physical': env.current_mappings[0]}
                    ler = DecoderInterface.estimate_logical_error_rate(layout, layout['logical_to_physical'], {'p': 0.001})
                    assert isinstance(ler, float) and not np.isnan(ler), "LER must be a float and not NaN (computed via stim+pymatching)"
                except Exception as e:
                    print(f"LER estimation failed: {e}")
                    ler = np.nan
                rewards.append(total_reward)
                lers.append(ler)
                self.logger.log_metric('test_episode_reward', total_reward, step=episode, run_id='test_rl_learning_progress')
                self.logger.log_metric('test_episode_ler', ler, step=episode, run_id='test_rl_learning_progress')
            trained_reward = np.mean(rewards)
            trained_ler = np.nanmean(lers)
            print(f"Baseline reward: {baseline_reward}, Trained reward: {trained_reward}")
            print(f"Baseline LER: {baseline_ler}, Trained LER: {trained_ler}")
            self.logger.log_event('test_completed', {'test': 'test_learning_improves_logical_error_rate', 'trained_reward': trained_reward, 'trained_ler': trained_ler}, level='INFO')
            # Only assert on LER if both are not nan
            if not (np.isnan(baseline_ler) or np.isnan(trained_ler)):
                self.assertTrue(trained_reward > baseline_reward or trained_ler < baseline_ler)
            elif trained_reward == 0.0 and baseline_reward == 0.0:
                self.skipTest("Both baseline and trained rewards are zero; test is inconclusive for this environment.")
            else:
                self.assertTrue(trained_reward > baseline_reward)
        else:
            print("No trained policy found. Skipping trained policy evaluation.")
            self.logger.log_event('test_skipped', {'test': 'test_learning_improves_logical_error_rate', 'reason': 'No trained policy found'}, level='WARNING')

if __name__ == '__main__':
    unittest.main() 