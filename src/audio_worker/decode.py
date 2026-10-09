"""Decode any upload format (MP3, WAV, AIFF, M4A) to mono float samples with ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np


class DecodeError(RuntimeError):
    pass


def decode_to_mono(path: Path, sample_rate: int, max_seconds: int) -> np.ndarray:
    """Return mono float32 samples in [-1, 1] at `sample_rate`.

    ffmpeg does the resampling and down-mixing; we read raw 32-bit floats from
    its stdout, so nothing is written to disk and memory stays bounded by
    `max_seconds` (15 min at 22.05 kHz is ~80 MB).
    """
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error",
        "-i", str(path),
        "-t", str(max_seconds),
        "-ac", "1", "-ar", str(sample_rate),
        "-f", "f32le", "-",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True, timeout=180)
    except FileNotFoundError as e:
        raise DecodeError("ffmpeg is not installed") from e
    except subprocess.CalledProcessError as e:
        detail = e.stderr.decode(errors='replace')[:300]
        raise DecodeError(f"ffmpeg could not decode the file: {detail}") from e
    except subprocess.TimeoutExpired as e:
        raise DecodeError("decoding timed out") from e

    samples = np.frombuffer(out.stdout, dtype=np.float32)
    if samples.size == 0:
        raise DecodeError("the file contains no audio")
    return samples
