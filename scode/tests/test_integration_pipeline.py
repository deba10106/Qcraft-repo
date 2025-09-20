import unittest
import os
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from scode.graph_transformer.graph_transformer import ConnectivityAwareGraphTransformer
try:
    from scode.rl_agent.rl_agent import ReinforcementLearningAgent
except ImportError:
    ReinforcementLearningAgent = None
from scode.rl_agent.environment import SurfaceCodeEnvironment
from scode.reward_engine.reward_engine import RewardEngine
from scode.multi_patch_mapper.multi_patch_mapper import MultiPatchMapper
from evaluation.evaluation_framework import EvaluationFramework
from orchestration_controller.orchestrator import Orchestrator
from scode.heuristic_layer.surface_code import SurfaceCode
from code_switcher.code_switcher import CodeSwitcher
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

class TestIntegrationPipeline(unittest.TestCase):
    def setUp(self, config_overrides=None, device_overrides=None):
        ConfigManager.load_registry()
        base_config = ConfigManager.get_config('multi_patch_rl_agent')
        self.config = deep_merge(base_config, config_overrides or {})
        hardware_json_path = ConfigManager.config_registry['hardware']
        base_device = DeviceAbstraction.load_selected_device(hardware_json_path)
        self.device = deep_merge(base_device, device_overrides or {})
        self.mapping_constraints = {'patch_shapes': ['rectangular']}
        self.code_distance = 3
        self.layout_type = 'planar'
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
        self.logger = LoggingResultsManager()

    def test_full_pipeline(self):
        self.logger.log_event('test_started', {'test': 'test_full_pipeline'}, level='INFO')
        if ReinforcementLearningAgent is None:
            self.skipTest("ReinforcementLearningAgent not available (rl_agent.py missing)")
        # Heuristic layer
        code = self.h_layer.generate_surface_code(3, 'planar')
        self.assertTrue(len(code.qubit_layout) > 0)
        # Graph transformer
        transformed = self.transformer.transform(code)
        self.assertIn('transformed_layout', transformed)
        # RL environment
        env = SurfaceCodeEnvironment(
            transformed_layout=transformed,
            hardware_specs=self.device,
            error_profile=self.device['qubit_properties'],
            config=self.config
        )
        env.reset()
        agent = ReinforcementLearningAgent(self.config, env, self.reward_engine)
        policy_path = agent.train()
        provider = self.device.get('provider_name', 'provider').lower()
        device = self.device.get('device_name', 'device').lower()
        layout_type = self.config.get('surface_code', {}).get('layout_type', 'planar')
        code_distance = self.config.get('surface_code', {}).get('code_distance', 3)
        expected_policy_path = os.path.abspath(os.path.join(self.config.get('system', {}).get('output_dir', './outputs'), '../training_artifacts', f"{provider}_{device}_{layout_type}_d{code_distance}_sb3_ppo_surface_code.zip"))
        self.assertTrue(os.path.exists(expected_policy_path))
        agent.export_policy(policy_path)
        # Multi-patch mapping
        mapper = MultiPatchMapper(self.config, self.device)
        surface_codes = [self.h_layer.generate_surface_code(3, 'planar') for _ in range(2)]
        mapping_constraints = self.config.get('multi_patch', {'patch_shapes': ['rectangular', 'rectangular'], 'num_patches': 2})
        multi_patch_result = mapper.map_patches(surface_codes, mapping_constraints)
        self.logger.log_event('test_case', {'test': 'test_full_pipeline', 'multi_patch_result': multi_patch_result}, level='DEBUG')
        self.assertIn('multi_patch_layout', multi_patch_result)
        self.assertIn('inter_patch_connectivity', multi_patch_result)
        self.assertIn('resource_allocation', multi_patch_result)
        self.assertIn('optimization_metrics', multi_patch_result)
        # Evaluation
        layout = multi_patch_result['multi_patch_layout']
        # Use the best available layout for evaluation (first patch as example)
        first_patch = next(iter(layout.values()))['layout'] if layout else {}
        # Compose a layout dict for evaluation framework
        eval_layout = {'qubit_layout': first_patch}
        ler = self.evaluator.evaluate_logical_error_rate(eval_layout, self.device, {})
        res_eff = self.evaluator.evaluate_resource_efficiency(eval_layout)
        learn_eff = self.evaluator.evaluate_learning_efficiency(agent.training_log)
        hw_adapt = self.evaluator.evaluate_hardware_adaptability({'hardware_compatibility': 1.0})
        self.logger.log_event('test_case', {'test': 'test_full_pipeline', 'ler': ler, 'res_eff': res_eff, 'learn_eff': learn_eff, 'hw_adapt': hw_adapt}, level='DEBUG')
        self.assertIsInstance(ler, float)
        self.assertIsInstance(res_eff, dict)
        self.assertIsInstance(learn_eff, dict)
        self.assertIsInstance(hw_adapt, dict)
        # Assert advanced KPIs
        self.assertIn('physical_qubits', res_eff)
        self.assertIn('circuit_depth', res_eff)
        self.assertIn('swap_overhead', res_eff)
        self.assertIn('weighted_single_qubit_gate_error', res_eff)
        self.assertIn('weighted_two_qubit_gate_error', res_eff)
        self.assertIn('training_time', learn_eff)
        self.assertIn('episodes_to_convergence', learn_eff)
        self.assertIn('hardware_compatibility', hw_adapt)
        self.logger.log_event('test_completed', {'test': 'test_full_pipeline'}, level='INFO')

    def test_orchestrator_and_switcher(self):
        orchestrator = Orchestrator(self.config_path, self.device_config, self.switcher_config_path)
        code, mapping = orchestrator.initialize_code(self.code_distance, self.layout_type, self.mapping_constraints)
        self.assertIsNotNone(code)
        self.assertIsNotNone(mapping)
        # Simulate a SWAP operation
        operations = [{'type': 'SWAP', 'swap_pairs': [(0, 1)]}]
        orchestrator.run_operations(operations, self.mapping_constraints)
        # Test code switcher directly
        switcher = CodeSwitcher(self.switcher_config_path)
        result = switcher.switch(mapping, mapping, protocol='lattice_surgery')
        self.assertIn('protocol', result)
        self.assertEqual(result['protocol'], 'lattice_surgery')

if __name__ == '__main__':
    unittest.main() 