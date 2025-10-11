# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from hardware_abstraction.device_abstraction import DeviceAbstraction

def test_normalize_device_info_connectivity_and_positions():
    dev = {
        'name': 'ibm_fake_device',
        'device_name': 'ibm_fake_device',
        'max_qubits': 5,
        'qubit_connectivity': {
            '0': ['1', '2'],
            '1': ['0', '3']
        },
        'qubit_positions': {
            '0': [0.0, 0.0],
            '1': [1.0, 0.0]
        },
        'native_gates': None
    }
    norm = DeviceAbstraction._normalize_device_info('ibm', dev)
    # Provider name
    assert norm.get('provider_name') == 'ibm'
    # Connectivity should be present in both aliases
    assert 'qubit_connectivity' in norm
    assert 'connectivity' in norm
    # Keys should be ints, neighbors should be ints
    assert all(isinstance(k, int) for k in norm['qubit_connectivity'].keys())
    all_neighbors = [n for v in norm['qubit_connectivity'].values() for n in v]
    assert all(isinstance(n, int) for n in all_neighbors)
    # Positions keys to int
    assert all(isinstance(k, int) for k in norm['qubit_positions'].keys())
    # Native gates list
    assert isinstance(norm.get('native_gates'), list)
