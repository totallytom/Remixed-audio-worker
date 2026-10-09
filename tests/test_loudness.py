import numpy as np
import pytest
from conftest import RATE, tone

from audio_worker.loudness import integrated_lufs


def test_full_scale_sine_is_about_minus_3_lufs():
    # BS.1770 reference: a full-scale 997 Hz sine measures -3.01 LUFS.
    assert integrated_lufs(tone(997, seconds=5, amp=1.0), RATE) == pytest.approx(-3.0, abs=0.3)


def test_half_amplitude_is_6db_quieter():
    loud = integrated_lufs(tone(997, seconds=5, amp=1.0), RATE)
    quiet = integrated_lufs(tone(997, seconds=5, amp=0.5), RATE)
    assert loud - quiet == pytest.approx(6.02, abs=0.2)


def test_silence_and_short_audio():
    assert integrated_lufs(np.zeros(RATE * 3, dtype=np.float32), RATE) is None
    assert integrated_lufs(tone(seconds=0.1), RATE) is None
