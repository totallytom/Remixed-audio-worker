"""Acoustic fingerprints (Chromaprint) and duplicate detection.

Chromaprint turns ~8 frames per second of audio into 32-bit integers that
describe its harmonic content. Two encodes of the same recording produce
nearly the same integers even at different bitrates or formats, so comparing
them bit by bit finds re-uploads that metadata checks miss (renamed titles,
different artist name).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FINGERPRINT_SECONDS = 120   # first two minutes are enough to identify a recording
MIN_OVERLAP = 40            # ~5 s of matching frames before a score counts
MAX_OFFSET = 80             # tolerate ~10 s of extra intro/silence at the start


class FingerprintError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fingerprint:
    duration: float
    raw: list[int]   # unsigned 32-bit values


def compute_fingerprint(path: Path) -> Fingerprint:
    """Run `fpcalc -raw` (the Chromaprint CLI) on an audio file."""
    cmd = ["fpcalc", "-raw", "-json", "-length", str(FINGERPRINT_SECONDS), str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    except FileNotFoundError as e:
        raise FingerprintError("fpcalc (Chromaprint) is not installed") from e
    except subprocess.CalledProcessError as e:
        raise FingerprintError(f"fpcalc failed: {e.stderr.decode(errors='replace')[:300]}") from e
    data = json.loads(out.stdout)
    raw = [int(v) & 0xFFFFFFFF for v in data.get("fingerprint", [])]
    if not raw:
        raise FingerprintError("empty fingerprint")
    return Fingerprint(duration=float(data.get("duration", 0.0)), raw=raw)


def _bit_errors(a: np.ndarray, b: np.ndarray) -> int:
    """Number of differing bits between two equal-length uint32 arrays."""
    return int(np.unpackbits(np.bitwise_xor(a, b).view(np.uint8)).sum())


def similarity(a: list[int], b: list[int], max_offset: int = MAX_OFFSET) -> float:
    """Best match score in [0, 1] over small time offsets.

    1.0 = identical, ~0.5 = unrelated (random bits agree half the time).
    Tries shifting one fingerprint against the other so a version with a
    different-length intro still lines up.
    """
    fa = np.asarray(a, dtype=np.uint32)
    fb = np.asarray(b, dtype=np.uint32)
    best = 0.0
    for offset in range(-max_offset, max_offset + 1):
        if offset >= 0:
            x, y = fa[offset:], fb
        else:
            x, y = fa, fb[-offset:]
        n = min(x.size, y.size)
        if n < MIN_OVERLAP:
            continue
        score = 1.0 - _bit_errors(x[:n], y[:n]) / (32.0 * n)
        best = max(best, score)
    return best


def find_matches(
    fingerprint: list[int],
    candidates: list[tuple[str, list[int]]],
    threshold: float,
) -> list[tuple[str, float]]:
    """Candidates (track_id, raw) scoring at or above `threshold`, best first."""
    hits = []
    for track_id, raw in candidates:
        score = similarity(fingerprint, raw)
        if score >= threshold:
            hits.append((track_id, round(score, 4)))
    return sorted(hits, key=lambda h: h[1], reverse=True)
