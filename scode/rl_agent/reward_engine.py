import numpy as np
import networkx as nx

class MultiPatchRewardEngine:
    def __init__(self, config):
        # Failsafe debug: print full reward config
        reward_cfg = config.get('reward_function', {})
        print(f"[DEBUG][REWARD ENGINE INIT - TOP] reward_cfg={reward_cfg} (keys: {list(reward_cfg.keys())})")
        # All weights and parameters are config-driven
        # Use only the top-level reward_cfg (no shadowing)
        if 'normalization' not in reward_cfg:
            print("[WARNING][REWARD ENGINE INIT] normalization missing from reward_function config, forcing to 'running_mean_std'")
            reward_cfg['normalization'] = 'running_mean_std'
        self.valid_mapping = reward_cfg.get('valid_mapping', 10.0)
        self.invalid_mapping = reward_cfg.get('invalid_mapping', -20.0)
        self.overlap_penalty = reward_cfg.get('overlap_penalty', -5.0)
        self.connectivity_bonus = reward_cfg.get('connectivity_bonus', 2.0)
        self.adjacency_bonus = reward_cfg.get('adjacency_bonus', 1.0)
        self.inter_patch_distance_penalty = reward_cfg.get('inter_patch_distance_penalty', -1.0)
        self.resource_utilization_bonus = reward_cfg.get('resource_utilization_bonus', 0.5)
        self.custom_terms = reward_cfg.get('custom_terms', [])
        # Advanced/Granular terms
        self.error_rate_bonus = reward_cfg.get('error_rate_bonus', 0.0)
        self.logical_operator_bonus = reward_cfg.get('logical_operator_bonus', 0.0)
        self.fully_mapped_bonus = reward_cfg.get('fully_mapped_bonus', 0.0)
        self.mapped_qubit_bonus = reward_cfg.get('mapped_qubit_bonus', 0.0)
        self.unmapped_qubit_penalty = reward_cfg.get('unmapped_qubit_penalty', 0.0)
        self.connected_bonus = reward_cfg.get('connected_bonus', 0.0)
        self.disconnected_graph_penalty = reward_cfg.get('disconnected_graph_penalty', 0.0)
        # Normalization
        self.normalization = reward_cfg.get('normalization', None)
        print(f"[DEBUG][REWARD ENGINE INIT] reward_cfg={reward_cfg}, normalization={self.normalization}")
        if not self.normalization:
            self.normalization = 'tanh'  # Default to 'tanh' for robust, bounded training
        print(f"[DEBUG][REWARD ENGINE INIT] FINAL normalization={self.normalization}")
        self.reward_history = []
        self.running_mean = 0.0
        self.running_std = 1.0
        # Curriculum phase shaping
        self.curriculum_config = config.get('curriculum_learning', {})
        self.phases = self.curriculum_config.get('stages', [{}])
        self.dynamic_weights = reward_cfg.get('dynamic_weights', False)
        self.phase_multipliers = reward_cfg.get('phase_multipliers', {})
        self.normalization_constant = reward_cfg.get('normalization_constant', 1.0)

    def compute_reward(self, mapping_info, env_info, current_phase=0, is_inference=False):
        breakdown = {}
        reward = 0.0
        # Valid/invalid mapping
        if mapping_info.get('is_valid', False):
            reward += self.valid_mapping
            breakdown['valid_mapping'] = self.valid_mapping
        else:
            reward += self.invalid_mapping
            breakdown['invalid_mapping'] = self.invalid_mapping
        # Overlap penalty
        if mapping_info.get('has_overlap', False):
            reward += self.overlap_penalty
            breakdown['overlap_penalty'] = self.overlap_penalty
        # Connectivity and adjacency
        conn_score = mapping_info.get('connectivity_score', 0)
        adj_score = mapping_info.get('adjacency_score', 0)
        reward += self.connectivity_bonus * conn_score
        breakdown['connectivity'] = self.connectivity_bonus * conn_score
        reward += self.adjacency_bonus * adj_score
        breakdown['adjacency'] = self.adjacency_bonus * adj_score
        # Inter-patch distance and resource utilization
        inter_patch_dist = mapping_info.get('inter_patch_distance', 0)
        resource_util = mapping_info.get('resource_utilization', 0)
        reward += self.inter_patch_distance_penalty * inter_patch_dist
        breakdown['inter_patch_distance'] = self.inter_patch_distance_penalty * inter_patch_dist
        reward += self.resource_utilization_bonus * resource_util
        breakdown['resource_utilization'] = self.resource_utilization_bonus * resource_util
        # Granular/advanced terms
        error_rate = mapping_info.get('avg_error_rate', 0)
        reward += self.error_rate_bonus * (1.0 - error_rate)
        breakdown['error_rate'] = self.error_rate_bonus * (1.0 - error_rate)
        logical_score = mapping_info.get('logical_operator_score', 0)
        reward += self.logical_operator_bonus * logical_score
        breakdown['logical_operator'] = self.logical_operator_bonus * logical_score
        # Mapping completeness
        mapped_qubits = mapping_info.get('mapped_qubits', 0)
        total_qubits = mapping_info.get('total_qubits', 1)
        fully_mapped = int(mapped_qubits == total_qubits)
        reward += self.fully_mapped_bonus * fully_mapped
        breakdown['fully_mapped'] = self.fully_mapped_bonus * fully_mapped
        reward += self.mapped_qubit_bonus * mapped_qubits
        breakdown['mapped_qubit_bonus'] = self.mapped_qubit_bonus * mapped_qubits
        reward += self.unmapped_qubit_penalty * (total_qubits - mapped_qubits)
        breakdown['unmapped_qubit_penalty'] = self.unmapped_qubit_penalty * (total_qubits - mapped_qubits)
        # Connected/disconnected graph
        num_components = mapping_info.get('num_components', 1)
        num_nodes = mapping_info.get('num_nodes', 1)
        if num_nodes > 0:
            conn_bonus = self.connected_bonus * (1.0 - (num_components - 1) / max(1, num_nodes - 1))
            reward += conn_bonus
            breakdown['connected_bonus'] = conn_bonus
        if num_components > 1:
            disc_penalty = self.disconnected_graph_penalty * (num_components - 1)
            reward += disc_penalty
            breakdown['disconnected_graph_penalty'] = disc_penalty
        # Custom terms
        for term in self.custom_terms:
            name = term.get('name')
            weight = term.get('weight', 0.0)
            value = mapping_info.get(name, 0)
            reward += weight * value
            breakdown[name] = weight * value
        # LER reward during inference
        if is_inference:
            ler = mapping_info.get('ler', mapping_info.get('logical_error_rate', None))
            ler_weight = getattr(self, 'ler_weight', 1.0)
            ler_threshold = getattr(self, 'ler_threshold', 0.1)
            # Allow config override
            if hasattr(self, 'config'):
                reward_cfg = self.config.get('reward_engine', self.config.get('reward_function', {}))
                ler_weight = reward_cfg.get('ler_weight', ler_weight)
                ler_threshold = reward_cfg.get('ler_threshold', ler_threshold)
            if ler is not None:
                ler_reward = ler_weight * (1.0 - min(1.0, ler / ler_threshold))
                reward += ler_reward
                breakdown['ler_reward'] = ler_reward
        # Curriculum phase shaping (dynamic weights)
        if self.dynamic_weights and current_phase < len(self.phases):
            phase = self.phases[current_phase]
            phase_weights = phase.get('reward_weights', {})
            for k, v in phase_weights.items():
                if v is not None and k in breakdown:
                    reward += (v - 1.0) * breakdown[k]
        # Normalization
        normalized_reward = self._normalize_reward(reward)
        breakdown['normalized_reward'] = normalized_reward
        # Debug print for normalization
        print(f"[DEBUG][REWARD ENGINE] Raw reward: {reward}, Normalized reward: {normalized_reward}, Normalization: {self.normalization}")
        # Normalization for inference
        normalization_constant = getattr(self, 'normalization_constant', 1.0)
        if hasattr(self, 'reward_cfg') and 'normalization_constant' in self.reward_cfg:
            normalization_constant = self.reward_cfg['normalization_constant']
        if is_inference and normalization_constant != 1.0:
            normalized_reward /= normalization_constant
            for k in breakdown:
                breakdown[k] /= normalization_constant
        return normalized_reward, breakdown

    def _normalize_reward(self, reward: float) -> float:
        print(f"[DEBUG][REWARD ENGINE] _normalize_reward called with normalization={self.normalization}, reward={reward}")
        self.reward_history.append(reward)
        if self.normalization == 'none':
            return reward
        elif self.normalization == 'tanh':
            return np.tanh(reward)
        elif self.normalization == 'running_mean_std':
            if len(self.reward_history) == 1:
                self.running_mean = reward
                self.running_std = 1.0
            else:
                alpha = 0.01
                self.running_mean = (1 - alpha) * self.running_mean + alpha * reward
                self.running_std = (1 - alpha) * self.running_std + alpha * abs(reward - self.running_mean)
                self.running_std = max(0.1, self.running_std)
            normalized = (reward - self.running_mean) / self.running_std
            return max(-5.0, min(5.0, normalized))
        elif self.normalization == 'clip':
            return max(-1.0, min(1.0, reward))
        elif self.normalization == 'percentile':
            if len(self.reward_history) > 100:
                sorted_rewards = sorted(self.reward_history[-100:])
                percentile_5 = sorted_rewards[4]
                percentile_95 = sorted_rewards[94]
                if percentile_95 > percentile_5:
                    normalized = (reward - percentile_5) / (percentile_95 - percentile_5)
                    return max(0.0, min(1.0, normalized))
            return max(0.0, min(1.0, reward))
        return reward 