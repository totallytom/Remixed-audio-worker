from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from audio_worker.config import Settings

RATE = 22_050


def tone(freq: float = 440.0, seconds: float = 2.0, amp: float = 0.5, rate: int = RATE) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        supabase_url="https://proj.supabase.co",
        service_role_key="service-key",
        webhook_secret="s3cret",
        peak_count=50,
    )


class MemoryStore:
    """In-memory stand-in for SupabaseStore."""

    def __init__(self) -> None:
        self.tracks: dict[str, dict[str, Any]] = {}
        self.analysis: dict[str, dict[str, Any]] = {}
        self.fingerprints: dict[str, tuple[list[int], float]] = {}
        self.matches: list[tuple[str, str, float]] = []

    def get_track(self, track_id):
        return self.tracks.get(track_id)

    def save_analysis(self, row):
        self.analysis.setdefault(row["track_id"], {}).update(row)

    def save_fingerprint(self, track_id, raw, duration):
        self.fingerprints[track_id] = (raw, duration)

    def fingerprints_except(self, track_id):
        for tid, (raw, _) in self.fingerprints.items():
            if tid != track_id:
                yield tid, self.tracks[tid]["user_id"], raw

    def save_match(self, track_id, matched_track_id, similarity):
        self.matches.append((track_id, matched_track_id, similarity))

    def track_ids_without_analysis(self, limit):
        return [t for t in self.tracks if self.analysis.get(t, {}).get("status") != "done"][:limit]


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()
