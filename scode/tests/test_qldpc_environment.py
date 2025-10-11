# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import numpy as np
from scode.rl_agent.qldpc_environment import QLDPCEnvironment

def make_min_config():
    return {
        'multi_patch_rl_agent': {
            'environment': {
                'patch_count': 1,
                'layout_type': 'tanner',
                'code_distance': 3
            }
        },
        'rl_agent': {'max_steps_per_episode': 5}
    }

def make_hw():
    # Simple line of 4 qubits: 0-1-2-3
    return {'qubit_connectivity': {0: [1], 1: [0,2], 2: [1,3], 3: [2]}}


def test_spaces_and_reset_step():
    env = QLDPCEnvironment(make_min_config(), make_hw())
    obs, info = env.reset()
    assert isinstance(obs, dict)
    assert {'node_features', 'adjacency', 'action_mask'} <= set(obs.keys())
    # Step with a no-op like action (zeros)
    action = np.zeros((6,), dtype=np.float32)
    o2, r, done, truncated, info2 = env.step(action)
    assert isinstance(o2, dict)
    assert isinstance(r, float)
    assert isinstance(done, bool)
    assert 'mapping' in info2
