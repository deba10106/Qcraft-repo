import gymnasium as gym
from gymnasium import spaces
import numpy as np
import networkx as nx
import random

class QLDPCEnvironment(gym.Env):
    metadata = {'render.modes': ['human', 'rgb_array']}

    def __init__(self, config, hardware_graph, qldpc_generator=None, reward_engine=None, logger=None):
        super().__init__()
        self.config = config or {}
        self.hardware_graph = hardware_graph or {}
        self.logger = logger
        self.patch_count = int(self.config.get('multi_patch_rl_agent', {}).get('environment', {}).get('patch_count', 1))
        self.qldpc_generator = qldpc_generator  # may be None; created on reset if missing
        self.reward_engine = reward_engine
        # Simple continuous spaces to start; will be expanded in follow-up patches
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(128,), dtype=np.float32)
        self._steps = 0
        self._max_steps = int(self.config.get('rl_agent', {}).get('max_steps_per_episode', 100))

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
        return np.zeros(self.observation_space.shape, dtype=np.float32), {}

    def step(self, action):
        self._steps += 1
        obs = np.zeros(self.observation_space.shape, dtype=np.float32)
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
        info = {}
        return obs, reward, done, False, info

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
