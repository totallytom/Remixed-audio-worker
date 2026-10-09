import numpy as np
from conftest import tone

from audio_worker.waveform import compute_peaks, resample_peaks


def test_length_and_range():
    peaks = compute_peaks(tone(seconds=3), 120)
    assert len(peaks) == 120
    assert all(0 <= p <= 100 for p in peaks)
    assert max(peaks) == 100


def test_follows_volume():
    # Quiet first half, loud second half.
    quiet, loud = tone(amp=0.1), tone(amp=0.8)
    peaks = compute_peaks(np.concatenate([quiet, loud]), 10)
    assert max(peaks[:5]) < 20
    assert min(peaks[5:]) > 90


def test_silence_is_flat():
    assert compute_peaks(np.zeros(10_000, dtype=np.float32), 20) == [0] * 20


def test_shorter_than_bucket_count():
    peaks = compute_peaks(np.array([0.5, -0.5, 0.25], dtype=np.float32), 8)
    assert len(peaks) == 8


def test_resample_keeps_tallest_bar():
    assert resample_peaks([10, 90, 20, 30, 100, 0], 3) == [90, 30, 100]
