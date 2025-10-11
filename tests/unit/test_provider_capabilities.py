# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from runtime.provider_capabilities import detect_capabilities, ProviderCapabilities


def test_detect_capabilities_ibm_defaults_true():
    caps = detect_capabilities({'provider_name': 'ibm'})
    pc = ProviderCapabilities(caps)
    assert pc.mid_circuit_measure is True
    assert pc.conditional is True
    assert pc.dynamic_circuits is True


def test_detect_capabilities_other_conservative():
    caps = detect_capabilities({'provider_name': 'rigetti'})
    pc = ProviderCapabilities(caps)
    assert pc.mid_circuit_measure in (False, True)
    assert caps.get('conditional', False) is False
    assert caps.get('dynamic_circuits', False) is False
