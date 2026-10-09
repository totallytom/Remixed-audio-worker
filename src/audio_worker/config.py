"""Settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    service_role_key: str
    webhook_secret: str
    peak_count: int = 200            # waveform resolution stored per track
    sample_rate: int = 22_050        # decode rate; plenty for peaks and loudness
    match_threshold: float = 0.85    # fingerprint similarity that counts as a duplicate
    max_download_mb: int = 80        # refuse anything bigger than an upload could be
    max_seconds: int = 900           # analyse at most 15 minutes of audio

    @property
    def storage_prefix(self) -> str:
        """Only audio from our own Supabase Storage is ever downloaded."""
        return f"{self.supabase_url.rstrip('/')}/storage/v1/object/public/"


def load_settings() -> Settings:
    def need(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"Missing environment variable {name}")
        return value

    return Settings(
        supabase_url=need("SUPABASE_URL"),
        service_role_key=need("SUPABASE_SERVICE_ROLE_KEY"),
        webhook_secret=need("WEBHOOK_SECRET"),
        peak_count=int(os.environ.get("PEAK_COUNT", 200)),
        match_threshold=float(os.environ.get("MATCH_THRESHOLD", 0.85)),
        max_download_mb=int(os.environ.get("MAX_DOWNLOAD_MB", 80)),
    )
