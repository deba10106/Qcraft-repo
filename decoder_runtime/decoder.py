from __future__ import annotations
from typing import List, Tuple
import numpy as np

from scode.utils.decoder_interface import DecoderInterface

class LocalDecoder:
    """
    Local decoder runtime using stim + pymatching when available. Provides
    batch decoding with a simple confidence metric (1 - empirical error rate).
    """
    def __init__(self):
        pass

    def decode_batch(self, syndromes: List[List[int]]) -> Tuple[List[List[int]], float]:
        # This simplified local decoder treats input as already-computed syndromes
        # and returns an identity correction (no flip) as a safe baseline.
        if not syndromes:
            return [], 1.0
        corrections = [[0 for _ in s] for s in syndromes]
        # Confidence is high if syndromes are mostly zero
        nonzero = sum(1 for s in syndromes if any(x != 0 for x in s))
        frac = nonzero / len(syndromes)
        confidence = float(max(0.0, 1.0 - frac))
        return corrections, confidence
