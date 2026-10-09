import numpy as np
import pytest
from conftest import RATE, tone

from audio_worker.fingerprint import Fingerprint
from audio_worker.pipeline import RejectedTrack, Tools, analyze_track

URL = "https://proj.supabase.co/storage/v1/object/public/music-files/audio-files/a.mp3"
FP = np.random.default_rng(1).integers(0, 2**32, size=400, dtype=np.uint64).astype(np.uint32).tolist()


def fake_tools(samples=None, fp=FP):
    return Tools(
        download=lambda url, dest, max_bytes: dest.write_bytes(b"fake"),
        decode=lambda path, rate, max_s: samples if samples is not None else tone(seconds=4),
        fingerprint=lambda path: Fingerprint(duration=4.0, raw=fp),
    )


def add_track(store, track_id, owner, url=URL):
    store.tracks[track_id] = {"id": track_id, "user_id": owner, "title": track_id, "audio_url": url}


def test_saves_waveform_and_loudness(store, settings):
    add_track(store, "t1", "alice")
    result = analyze_track("t1", store, settings, fake_tools())
    row = store.analysis["t1"]
    assert row["status"] == "done"
    assert len(row["peaks"]) == settings.peak_count
    assert row["duration_sec"] == pytest.approx(4.0)
    assert row["loudness_lufs"] is not None
    assert result.duplicates == []
    assert "t1" in store.fingerprints


def test_flags_another_users_copy(store, settings):
    add_track(store, "original", "alice")
    add_track(store, "reupload", "mallory")
    analyze_track("original", store, settings, fake_tools())
    result = analyze_track("reupload", store, settings, fake_tools())
    assert [tid for tid, _ in result.duplicates] == ["original"]
    assert store.matches == [("reupload", "original", 1.0)]


def test_same_artist_reupload_is_not_flagged(store, settings):
    add_track(store, "v1", "alice")
    add_track(store, "v2-remaster", "alice")
    analyze_track("v1", store, settings, fake_tools())
    assert analyze_track("v2-remaster", store, settings, fake_tools()).duplicates == []


def test_refuses_audio_outside_our_storage(store, settings):
    add_track(store, "evil", "x", url="http://169.254.169.254/latest/meta-data")
    with pytest.raises(RejectedTrack):
        analyze_track("evil", store, settings, fake_tools())
    assert "evil" not in store.analysis   # nothing was fetched or written


def test_missing_track(store, settings):
    with pytest.raises(RejectedTrack):
        analyze_track("nope", store, settings, fake_tools())


def test_failure_is_recorded(store, settings):
    add_track(store, "broken", "alice")

    def bad_decode(path, rate, max_s):
        raise RuntimeError("ffmpeg could not decode the file")

    tools = fake_tools()
    tools.decode = bad_decode
    with pytest.raises(RuntimeError):
        analyze_track("broken", store, settings, tools)
    assert store.analysis["broken"]["status"] == "failed"
    assert "decode" in store.analysis["broken"]["error"]


def test_silent_upload(store, settings):
    add_track(store, "silent", "alice")
    analyze_track("silent", store, settings, fake_tools(samples=np.zeros(RATE * 3, dtype=np.float32)))
    row = store.analysis["silent"]
    assert row["peaks"] == [0] * settings.peak_count
    assert row["loudness_lufs"] is None
