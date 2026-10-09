"""Integrated loudness (LUFS, ITU-R BS.1770) — lets the app play tracks at an even volume."""

from __future__ import annotations

import math

import numpy as np
import pyloudnorm as pyln

MIN_SECONDS = 0.5  # BS.1770 gating needs at least one 400 ms block


def integrated_lufs(samples: np.ndarray, sample_rate: int) -> float | None:
    """Return integrated loudness in LUFS, or None for silence / too-short audio."""
    if samples.size < int(MIN_SECONDS * sample_rate):
        return None
    meter = pyln.Meter(sample_rate)
    value = meter.integrated_loudness(samples.astype(np.float64))
    if value is None or math.isinf(value) or math.isnan(value):
        return None
    return round(float(value), 2)
