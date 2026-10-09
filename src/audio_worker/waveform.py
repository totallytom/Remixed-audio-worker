"""Waveform peaks: the shape the app draws in its seek bar."""

from __future__ import annotations

import numpy as np


def compute_peaks(samples: np.ndarray, count: int = 200) -> list[int]:
    """Split the track into `count` equal slices and return each slice's loudness as 0-100.

    RMS (not max) per slice: it follows perceived loudness, so a single click
    doesn't show as a full-height bar. Values are scaled to the loudest slice,
    so quiet and loud masters both use the full height of the bar.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    if samples.size == 0:
        return [0] * count

    x = samples.astype(np.float64)
    # array_split handles tracks shorter than `count` samples (some slices empty).
    slices = np.array_split(x, count)
    rms = np.array([np.sqrt(np.mean(s * s)) if s.size else 0.0 for s in slices])

    top = rms.max()
    if top <= 1e-9:                      # digital silence
        return [0] * count
    return [int(round(v)) for v in (rms / top) * 100]


def resample_peaks(peaks: list[int], count: int) -> list[int]:
    """Fit stored peaks to however many bars a screen draws (max of each group)."""
    if not peaks:
        return [0] * count
    groups = np.array_split(np.asarray(peaks), count)
    return [int(g.max()) if g.size else 0 for g in groups]
