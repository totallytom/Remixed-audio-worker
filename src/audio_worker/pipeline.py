"""analyze_track: download → decode → peaks + loudness + fingerprint → duplicates → save."""

from __future__ import annotations

import logging
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

from . import __version__
from .config import Settings
from .decode import decode_to_mono
from .fingerprint import Fingerprint, compute_fingerprint, find_matches
from .loudness import integrated_lufs
from .store import Store
from .waveform import compute_peaks

log = logging.getLogger("audio_worker")


class RejectedTrack(ValueError):
    """The track can't be analysed (missing, no audio, audio hosted elsewhere)."""


@dataclass
class Result:
    track_id: str
    duration_sec: float = 0.0
    peaks: list[int] = field(default_factory=list)
    loudness_lufs: float | None = None
    duplicates: list[tuple[str, float]] = field(default_factory=list)
    elapsed_sec: float = 0.0


@dataclass
class Tools:
    """The parts that need external programs or the network; swapped out in tests."""
    download: Callable[[str, Path, int], None]
    decode: Callable[[Path, int, int], np.ndarray]
    fingerprint: Callable[[Path], Fingerprint]


def download_file(url: str, dest: Path, max_bytes: int) -> None:
    """Stream to disk, refusing anything larger than `max_bytes`."""
    with httpx.stream("GET", url, timeout=60, follow_redirects=False) as r:
        r.raise_for_status()
        size = 0
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise RejectedTrack(f"audio file is larger than {max_bytes // 1_048_576} MB")
                f.write(chunk)


DEFAULT_TOOLS = Tools(download=download_file, decode=decode_to_mono, fingerprint=compute_fingerprint)


def analyze_track(track_id: str, store: Store, settings: Settings, tools: Tools = DEFAULT_TOOLS) -> Result:
    started = time.monotonic()
    track = store.get_track(track_id)
    if not track:
        raise RejectedTrack("track not found")
    url = track.get("audio_url") or ""
    # Only ever fetch from our own storage: the URL comes from the database, but
    # a webhook payload or a bad row must not make the worker request arbitrary hosts.
    if not url.startswith(settings.storage_prefix):
        raise RejectedTrack("audio is not hosted in this project's storage")

    store.save_analysis({"track_id": track_id, "status": "processing", "worker_version": __version__})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio"
            tools.download(url, path, settings.max_download_mb * 1_048_576)
            samples = tools.decode(path, settings.sample_rate, settings.max_seconds)
            fp = tools.fingerprint(path)

        result = Result(
            track_id=track_id,
            duration_sec=round(samples.size / settings.sample_rate, 2),
            peaks=compute_peaks(samples, settings.peak_count),
            loudness_lufs=integrated_lufs(samples, settings.sample_rate),
        )

        # Duplicates: compare against other uploaders only — an artist re-uploading
        # their own song (e.g. a remaster) isn't a rights problem.
        owner = track.get("user_id")
        candidates = [(tid, raw) for tid, cand_owner, raw in store.fingerprints_except(track_id)
                      if cand_owner != owner]
        result.duplicates = find_matches(fp.raw, candidates, settings.match_threshold)

        store.save_fingerprint(track_id, fp.raw, fp.duration)
        for matched_id, score in result.duplicates:
            store.save_match(track_id, matched_id, score)
        store.save_analysis({
            "track_id": track_id,
            "status": "done",
            "duration_sec": result.duration_sec,
            "peaks": result.peaks,
            "loudness_lufs": result.loudness_lufs,
            "error": None,
            "analyzed_at": datetime.now(UTC).isoformat(),
            "worker_version": __version__,
        })
        result.elapsed_sec = round(time.monotonic() - started, 2)
        log.info("analysed %s in %.1fs (%d duplicate candidates)", track_id, result.elapsed_sec,
                 len(result.duplicates))
        return result
    except Exception as e:
        store.save_analysis({
            "track_id": track_id, "status": "failed", "error": str(e)[:500], "worker_version": __version__,
        })
        log.exception("analysis failed for %s", track_id)
        raise
