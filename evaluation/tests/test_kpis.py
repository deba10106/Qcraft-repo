# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from evaluation.kpis import compute_mapping_kpis


def test_compute_mapping_kpis_empty():
    out = compute_mapping_kpis({})
    assert 'patch_count' in out
    assert out['mapping_present'] is False


def test_compute_mapping_kpis_counts():
    mapping_info = {
        'multi_patch_mapping': {
            'multi_patch_layout': {
                0: {'layout': {0: {}, 1: {}}},
                1: {'layout': {0: {}, 1: {}, 2: {}}},
            }
        },
        'logical_to_physical': {0: 10, 1: 11}
    }
    out = compute_mapping_kpis(mapping_info)
    assert out['patch_count'] == 2
    assert out['physical_qubits'] == 5
    assert out['mapping_present'] is True
    assert out['has_overlap'] is False


def test_compute_mapping_kpis_overlap():
    mapping_info = {
        'logical_to_physical': {0: 10, 1: 10}
    }
    out = compute_mapping_kpis(mapping_info)
    assert out['has_overlap'] is True
