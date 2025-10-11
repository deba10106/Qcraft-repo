# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from typing import Dict, Any
import numpy as np
from scode.utils.decoder_interface import DecoderInterface

class EvaluationFramework:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def evaluate_logical_error_rate(self, layout: Dict[str, Any], hardware: Dict[str, Any], noise_model: Dict[str, Any]) -> float:
        # Use DecoderInterface for LER
        mapping = layout.get('logical_to_physical', None)
        if mapping is None:
            raise ValueError("No logical_to_physical mapping found in layout for LER evaluation.")
        try:
            ler = DecoderInterface.estimate_logical_error_rate(layout, mapping, noise_model)
        except Exception as e:
            raise RuntimeError(f"LER estimation failed: {e}")
        return ler

    def evaluate_resource_efficiency(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        # Compute physical qubit count, circuit depth, SWAP overhead from layout
        physical_qubits = len(layout) if isinstance(layout, dict) else 0
        circuit_depth = layout.get('circuit_depth', 0) if isinstance(layout, dict) else 0
        swap_overhead = layout.get('total_swap_gates', 0) if isinstance(layout, dict) else 0
        result = {'physical_qubits': physical_qubits, 'circuit_depth': circuit_depth, 'swap_overhead': swap_overhead}
        if 'weighted_single_qubit_gate_error' in layout:
            result['weighted_single_qubit_gate_error'] = layout['weighted_single_qubit_gate_error']
        if 'weighted_two_qubit_gate_error' in layout:
            result['weighted_two_qubit_gate_error'] = layout['weighted_two_qubit_gate_error']
        return result

    def evaluate_learning_efficiency(self, training_log: Any) -> Dict[str, Any]:
        # Compute training time, episodes to convergence from training log
        episodes = [entry['episode'] for entry in training_log] if training_log else []
        rewards = [entry['reward'] for entry in training_log] if training_log else []
        training_time = self.config.get('evaluation', {}).get('default_training_time', 0)
        episodes_to_convergence = len(episodes)
        reward_variance_threshold = self.config.get('evaluation', {}).get('reward_variance_threshold', 0.01)
        if rewards:
            # Example: convergence if reward variance < threshold
            for i in range(10, len(rewards)):
                if np.var(rewards[i-10:i]) < reward_variance_threshold:
                    episodes_to_convergence = i
                    break
        return {'training_time': training_time, 'episodes_to_convergence': episodes_to_convergence}

    def evaluate_hardware_adaptability(self, results: Any) -> Dict[str, Any]:
        # Assess performance across hardware profiles from results
        compatibility = results.get('hardware_compatibility', 1.0) if isinstance(results, dict) else 1.0
        return {'hardware_compatibility': compatibility}

    def comprehensive_validate_layout(self, layout: Dict[str, Any], hardware: Dict[str, Any], noise_model: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wrapper that computes core KPIs for a layout: logical error rate and resource metrics.
        Returns a dict suitable for basic comparisons and reporting.
        """
        result = {}
        try:
            ler = self.evaluate_logical_error_rate(layout, hardware, noise_model)
        except Exception as e:
            ler = None
            result['ler_error'] = str(e)
        result['logical_error_rate'] = ler
        result['resource_efficiency'] = self.evaluate_resource_efficiency(layout)
        result['valid'] = (ler is not None)
        return result

    def run_evaluation_scenarios(self, scenarios: list) -> list:
        """
        Minimal runner: for each scenario dict with keys layout, hardware, noise_model,
        return comprehensive validation results.
        """
        outputs = []
        for sc in scenarios or []:
            layout = sc.get('layout', {})
            hardware = sc.get('hardware', {})
            noise = sc.get('noise_model', {})
            outputs.append(self.comprehensive_validate_layout(layout, hardware, noise))
        return outputs

    def compare_against_baseline(self, result: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
        """Return simple diffs between a result and a baseline for key KPIs."""
        cmp = {
            'delta_ler': None,
            'delta_physical_qubits': None,
        }
        if result and baseline:
            r_ler = result.get('logical_error_rate')
            b_ler = baseline.get('logical_error_rate')
            if r_ler is not None and b_ler is not None:
                cmp['delta_ler'] = r_ler - b_ler
            r_phys = (result.get('resource_efficiency') or {}).get('physical_qubits')
            b_phys = (baseline.get('resource_efficiency') or {}).get('physical_qubits')
            if r_phys is not None and b_phys is not None:
                cmp['delta_physical_qubits'] = r_phys - b_phys
        return cmp