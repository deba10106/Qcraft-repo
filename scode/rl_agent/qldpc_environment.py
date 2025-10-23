# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import networkx as nx
import random
from scode.rl_agent.env_constants import MAX_PATCHES, MAX_QUBITS, NUM_FEATURES
from scode.utils.decoder_interface import DecoderInterface
from scode.rl_agent.env_interface import RLMappingEnvInterface

class QLDPCEnvironment(gym.Env, RLMappingEnvInterface):
    metadata = {'render.modes': ['human', 'rgb_array']}

    def __init__(self, config, hardware_graph, qldpc_generator=None, reward_engine=None, logger=None):
        super().__init__()
        self.config = config or {}
        self.hardware_graph = hardware_graph or {}
        self.logger = logger
        self.patch_count = int(self.config.get('multi_patch_rl_agent', {}).get('environment', {}).get('patch_count', 1))
        self.qldpc_generator = qldpc_generator  # may be None; created on reset if missing
        self.reward_engine = reward_engine
        # Align spaces with SurfaceCodeEnvironment for SB3 compatibility
        self.action_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([
                MAX_PATCHES-1,  # patch_idx
                2,              # action_type (SWAP/REWIRE/ASSIGN)
                MAX_QUBITS-1,   # qubit1
                MAX_QUBITS-1,   # qubit2
                MAX_QUBITS-1,   # param1
                1               # param2
            ], dtype=np.float32),
            dtype=np.float32
        )
        self.observation_space = spaces.Dict({
            'node_features': spaces.Box(low=0, high=1, shape=(MAX_PATCHES * MAX_QUBITS, NUM_FEATURES), dtype=np.float32),
            'adjacency': spaces.Box(low=0, high=1, shape=(MAX_PATCHES * MAX_QUBITS, MAX_QUBITS), dtype=np.float32),
            'action_mask': spaces.Box(low=0, high=1, shape=(MAX_PATCHES * 3, MAX_QUBITS, MAX_QUBITS), dtype=np.float32)
        })
        self._steps = 0
        self._max_steps = int(self.config.get('rl_agent', {}).get('max_steps_per_episode', 100))

    # Expose max_steps for external control (curriculum stage wiring)
    @property
    def max_steps(self) -> int:
        return int(self._max_steps)

    @max_steps.setter
    def max_steps(self, value: int) -> None:
        try:
            self._max_steps = int(value)
        except Exception:
            pass

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._steps = 0
        # Minimal qLDPC code generation per patch
        self.codes = []
        env = self.config.get('multi_patch_rl_agent', {}).get('environment', {})
        layout = env.get('layout_type', 'tanner')
        dist = int(env.get('code_distance', 3))
        # Lazy-create generator if needed
        if self.qldpc_generator is None:
            try:
                from qldpc.generator import QLDPCGenerator
                self.qldpc_generator = QLDPCGenerator()
            except Exception:
                self.qldpc_generator = None
        for _ in range(self.patch_count):
            code = (self.qldpc_generator.generate_code(layout, dist) if self.qldpc_generator else None)
            self.codes.append(code)
        # Initialize trivial mappings (no overlap)
        hw_nodes = list((self.hardware_graph or {}).get('qubit_connectivity', {}).keys())
        random.shuffle(hw_nodes)
        self.current_mappings = []
        for code in self.codes:
            sc_qubits = list(getattr(code, 'qubit_layout', {}).keys()) if code else []
            mapping = {int(sc_q): int(hw_nodes[i % max(1, len(hw_nodes))]) for i, sc_q in enumerate(sc_qubits)}
            self.current_mappings.append(mapping)
        return self._build_observation(), {}

    def _make_empty_observation(self):
        node_features = np.zeros((MAX_PATCHES * MAX_QUBITS, NUM_FEATURES), dtype=np.float32)
        adjacency = np.zeros((MAX_PATCHES * MAX_QUBITS, MAX_QUBITS), dtype=np.float32)
        action_mask = self._get_action_masks()
        return {
            'node_features': node_features,
            'adjacency': adjacency,
            'action_mask': action_mask
        }

    def _get_action_masks(self):
        """Minimal legal action mask based on current mappings (per patch)."""
        masks = np.zeros((self.patch_count, 3, MAX_QUBITS, MAX_QUBITS), dtype=np.float32)
        for i, mapping in enumerate(getattr(self, 'current_mappings', [])):
            sc_qubits = list(mapping.keys())
            code_adj = None
            try:
                code_adj = getattr(self.codes[i], 'adjacency_matrix', None)
            except Exception:
                code_adj = None
            # Hardware connectivity for mask tightening (align with Surface env semantics)
            conn = (self.hardware_graph or {}).get('qubit_connectivity', {})
            for a_type in range(3):
                for q1 in sc_qubits:
                    for q2 in sc_qubits:
                        if q1 == q2:
                            continue
                        # For SWAP/REWIRE (a_type 0/1), require HW adjacency when both are mapped
                        if a_type in (0, 1):
                            hw1 = mapping.get(int(q1))
                            hw2 = mapping.get(int(q2))
                            if hw1 is not None and hw2 is not None:
                                if int(hw2) not in [int(n) for n in conn.get(int(hw1), [])]:
                                    continue
                        if a_type == 2 and code_adj is not None and not code_adj.has_edge(q1, q2):
                            continue
                        masks[i, a_type, int(q1), int(q2)] = 1.0
        return masks.reshape(self.patch_count * 3, MAX_QUBITS, MAX_QUBITS)

    def step(self, action):
        self._steps += 1
        # Observation is a Dict; initialize an empty one (will be enriched later)
        obs = self._build_observation()
        # Compute a minimal reward using reward_engine if available
        reward = 0.0
        if self.reward_engine is None:
            try:
                from scode.rl_agent.reward_engine import MultiPatchRewardEngine
                self.reward_engine = MultiPatchRewardEngine(self.config)
            except Exception:
                self.reward_engine = None
        if self.reward_engine is not None:
            mapping_info = {'is_valid': True, 'connectivity_score': self._connectivity_score()}
            r, _ = self.reward_engine.compute_reward(mapping_info, env_info={}, is_inference=False)
            reward = float(r)
        done = self._steps >= self._max_steps
        info = {
            'mapping': (self.current_mappings[0] if self.current_mappings else {}),
            'episode_step': self._steps,
        }
        # Best-effort logical error rate estimation (optional)
        try:
            code = self.codes[0] if self.codes else None
            mapping0 = self.current_mappings[0] if self.current_mappings else {}
            if code and mapping0:
                noise_model = getattr(self, 'error_profile', {'p': 0.001})
                ler = DecoderInterface.estimate_logical_error_rate(
                    code, mapping0, noise_model,
                    num_trials=getattr(self, 'ler_num_trials', 50),
                    error_prob=getattr(self, 'ler_noise_prob', 0.001)
                )
                if ler is not None:
                    info['ler'] = float(ler)
                    info['logical_error_rate'] = float(ler)
        except Exception:
            pass
        return obs, reward, done, False, info

    def _build_observation(self):
        obs = self._make_empty_observation()
        conn = (self.hardware_graph or {}).get('qubit_connectivity', {})
        qprops = (self.hardware_graph or {}).get('qubit_properties', {})
        for i, mapping in enumerate(getattr(self, 'current_mappings', [])):
            for sc_q, hw_q in mapping.items():
                if 0 <= int(hw_q) < MAX_QUBITS:
                    idx = i * MAX_QUBITS + int(hw_q)
                    # Feature[0]: error_rate from hardware properties (fallback 0.0)
                    try:
                        obs['node_features'][idx, 0] = float(qprops.get(int(hw_q), {}).get('readout_error', 0.0))
                    except Exception:
                        obs['node_features'][idx, 0] = 0.0
                    # One-hot role similar to Surface env (1=data,2=ancilla_X,3=ancilla_Z,4=unassigned)
                    role = None
                    try:
                        role = getattr(self.codes[i], 'qubit_layout', {}).get(int(sc_q), {}).get('type')
                    except Exception:
                        role = None
                    role_idx = 4
                    if role == 'data':
                        role_idx = 1
                    elif role == 'ancilla_X':
                        role_idx = 2
                    elif role == 'ancilla_Z':
                        role_idx = 3
                    obs['node_features'][idx, role_idx] = 1.0
                    for nb in conn.get(int(hw_q), []):
                        if 0 <= int(nb) < MAX_QUBITS:
                            obs['adjacency'][idx, int(nb)] = 1.0
        obs['action_mask'] = self._get_action_masks()
        return obs

    def _connectivity_score(self) -> float:
        try:
            # Approximate: use first patch if present
            if not self.codes or not self.current_mappings:
                return 0.0
            code = self.codes[0]
            mapping = self.current_mappings[0]
            # Build HW adjacency
            conn = (self.hardware_graph or {}).get('qubit_connectivity', {})
            preserved = 0
            total = 0
            for (u, v) in getattr(code, 'adjacency_matrix', nx.Graph()).edges():
                total += 1
                hu = mapping.get(int(u))
                hv = mapping.get(int(v))
                if hu is None or hv is None:
                    continue
                if int(hv) in [int(n) for n in conn.get(int(hu), [])]:
                    preserved += 1
            return preserved / max(1, total)
        except Exception:
            return 0.0

    # Interface utility
    def get_mapping_info(self) -> dict:
        return {
            'mapping': (self.current_mappings[0] if self.current_mappings else {}),
            'patch_count': self.patch_count
        }
