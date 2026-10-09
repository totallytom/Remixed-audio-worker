"""Supabase access through its REST API (PostgREST), using the service-role key.

The worker is the only thing holding that key: fingerprints and duplicate
matches are never readable by app users (see sql/001_audio_analysis.sql).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

import httpx

from .config import Settings


class Store(Protocol):
    """What the pipeline needs; the tests provide an in-memory version."""

    def get_track(self, track_id: str) -> dict[str, Any] | None: ...
    def save_analysis(self, row: dict[str, Any]) -> None: ...
    def save_fingerprint(self, track_id: str, raw: list[int], duration: float) -> None: ...
    def fingerprints_except(self, track_id: str) -> Iterator[tuple[str, str, list[int]]]: ...
    def save_match(self, track_id: str, matched_track_id: str, similarity: float) -> None: ...
    def track_ids_without_analysis(self, limit: int) -> list[str]: ...


class SupabaseStore:
    PAGE = 500

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self._rest = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        key = settings.service_role_key
        self._http = client or httpx.Client(
            timeout=30,
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )

    def _upsert(self, table: str, row: dict[str, Any], on_conflict: str) -> None:
        r = self._http.post(
            f"{self._rest}/{table}",
            params={"on_conflict": on_conflict},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=row,
        )
        r.raise_for_status()

    def get_track(self, track_id: str) -> dict[str, Any] | None:
        r = self._http.get(
            f"{self._rest}/tracks",
            params={"id": f"eq.{track_id}", "select": "id,user_id,title,audio_url,status"},
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def save_analysis(self, row: dict[str, Any]) -> None:
        self._upsert("track_audio_analysis", row, "track_id")

    def save_fingerprint(self, track_id: str, raw: list[int], duration: float) -> None:
        # Postgres int4 is signed: store the unsigned 32-bit values in two's complement.
        signed = [v - (1 << 32) if v >= (1 << 31) else v for v in raw]
        self._upsert(
            "track_fingerprints",
            {"track_id": track_id, "fingerprint": signed, "duration_sec": duration},
            "track_id",
        )

    def fingerprints_except(self, track_id: str) -> Iterator[tuple[str, str, list[int]]]:
        """(track_id, owner_id, unsigned raw) for every other fingerprinted track, paged."""
        offset = 0
        while True:
            r = self._http.get(
                f"{self._rest}/track_fingerprints",
                params={
                    "select": "track_id,fingerprint,tracks(user_id)",
                    "track_id": f"neq.{track_id}",
                    "order": "track_id",
                    "limit": self.PAGE,
                    "offset": offset,
                },
            )
            r.raise_for_status()
            rows = r.json()
            for row in rows:
                owner = (row.get("tracks") or {}).get("user_id", "")
                yield row["track_id"], owner, [v & 0xFFFFFFFF for v in row["fingerprint"]]
            if len(rows) < self.PAGE:
                return
            offset += self.PAGE

    def save_match(self, track_id: str, matched_track_id: str, similarity: float) -> None:
        self._upsert(
            "audio_duplicate_matches",
            {"track_id": track_id, "matched_track_id": matched_track_id, "similarity": similarity},
            "track_id,matched_track_id",
        )

    def track_ids_without_analysis(self, limit: int) -> list[str]:
        """Tracks with audio but no finished analysis (for the backfill command)."""
        tracks = self._http.get(
            f"{self._rest}/tracks", params={"select": "id", "audio_url": "not.is.null", "limit": 10_000}
        )
        done = self._http.get(
            f"{self._rest}/track_audio_analysis",
            params={"select": "track_id", "status": "eq.done", "limit": 10_000},
        )
        tracks.raise_for_status()
        done.raise_for_status()
        finished = {row["track_id"] for row in done.json()}
        return [row["id"] for row in tracks.json() if row["id"] not in finished][:limit]
