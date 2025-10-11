# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from code_switcher.code_switcher import CodeSwitcherAPI


def test_identify_switching_points_basic():
    api = CodeSwitcherAPI()
    circuit = {
        'gates': [
            {'name': 'X', 'qubits': [0]},
            {'name': 'SWAP', 'qubits': [0, 1]},
            {'name': 'CNOT', 'qubits': [0, 1]},
            {'name': 'T', 'qubits': [0]},
        ]
    }
    code_info = {'supported_gates': ['X', 'CNOT']}
    sps = api.identify_switching_points(circuit, code_info)
    names = [sp['gate'] for sp in sps]
    assert 'SWAP' in names and 'T' in names


def test_select_switching_protocol_prefers_supported():
    api = CodeSwitcherAPI()
    chosen = api.select_switching_protocol('SWAP', ['magic_state_injection', 'teleportation'])
    assert chosen == 'teleportation'


def test_apply_code_switching_teleportation_inserts_wrappers():
    api = CodeSwitcherAPI()
    circuit = {
        'gates': [
            {'name': 'X', 'qubits': [0]},
            {'name': 'SWAP', 'qubits': [0, 1]},
        ]
    }
    sps = [{'index': 1, 'gate': 'SWAP', 'qubits': [0, 1], 'location': 1, 'protocol': 'teleportation'}]
    protocols = [{'name': 'teleportation'}]
    out = api.apply_code_switching(circuit, sps, protocols)
    names = [g['name'] for g in out['gates']]
    assert 'teleportation_start' in names and 'teleportation_end' in names
