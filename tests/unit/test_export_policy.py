# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import copy
import pytest

from privacy.export_policy import apply_export_policy


def test_export_policy_none_returns_same():
    pkg = {'native_job': {'qcraft_circuit': {'gates': []}}, 'metadata': {'comments': 'hello'}}
    out = apply_export_policy(copy.deepcopy(pkg), policy='none')
    assert out == pkg


def test_export_policy_strict_local_blocks():
    pkg = {'native_job': {}, 'metadata': {}}
    with pytest.raises(PermissionError):
        apply_export_policy(pkg, policy='strict-local')


def test_export_policy_obfuscate_removes_qcraft_and_redacts():
    pkg = {'native_job': {'qcraft_circuit': {'gates': [1]}}, 'metadata': {'comments': 'secret', 'other': 1}}
    out = apply_export_policy(pkg, policy='obfuscate')
    assert 'qcraft_circuit' not in out['native_job']
    assert out['metadata']['comments'] == '<redacted>'
