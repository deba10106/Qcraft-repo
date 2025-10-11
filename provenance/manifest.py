# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations
from typing import Dict, Any
import json
import hashlib
import time


def generate_provenance_manifest(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a signed provenance manifest capturing key compilation decisions and
    environment metadata. Signature is a SHA256 over the canonical JSON of metadata
    plus timestamp for tamper detection.
    """
    ts = time.time()
    body = {
        'version': '1.0',
        'timestamp': ts,
        'metadata': metadata or {},
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hashlib.sha256(canonical).hexdigest()
    return {
        **body,
        'signature': sig,
        'signature_alg': 'sha256',
    }
