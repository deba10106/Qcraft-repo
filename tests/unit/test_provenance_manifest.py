# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import pytest
from provenance.manifest import generate_provenance_manifest


def test_generate_provenance_manifest_deterministic_signature(monkeypatch):
    meta = {'a': 1, 'b': 'x'}
    monkeypatch.setattr('provenance.manifest.time.time', lambda: 12345.0)
    m1 = generate_provenance_manifest(meta)
    m2 = generate_provenance_manifest(meta)
    assert m1['signature_alg'] == 'sha256'
    assert m1['metadata'] == meta
    assert m1['timestamp'] == 12345.0
    assert m1['signature'] == m2['signature']
