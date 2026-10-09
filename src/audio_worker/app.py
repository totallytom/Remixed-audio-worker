"""HTTP entry point. Supabase calls POST /webhooks/track when a track row is inserted
or its audio changes (Database Webhook); analysis runs after the response is sent."""

from __future__ import annotations

import hmac
import logging
import threading
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from . import __version__
from .config import Settings, load_settings
from .pipeline import RejectedTrack, analyze_track
from .store import SupabaseStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("audio_worker")

app = FastAPI(title="Re-Mixed audio worker", version=__version__)

# Decoding a long WAV holds tens of MB; two at a time keeps a small instance safe.
_slots = threading.BoundedSemaphore(2)


def get_settings() -> Settings:
    return load_settings()


class WebhookPayload(BaseModel):
    """The body Supabase Database Webhooks send."""
    type: str                              # INSERT | UPDATE | DELETE
    table: str
    record: dict[str, Any] | None = None
    old_record: dict[str, Any] | None = None


def _check_secret(given: str | None, settings: Settings) -> None:
    if not given or not hmac.compare_digest(given, settings.webhook_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad webhook secret")


def _run(track_id: str, settings: Settings) -> None:
    with _slots:
        try:
            analyze_track(track_id, SupabaseStore(settings), settings)
        except RejectedTrack as e:
            log.warning("skipped %s: %s", track_id, e)
        except Exception:
            pass  # already logged and recorded as failed by the pipeline


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/webhooks/track", status_code=status.HTTP_202_ACCEPTED)
def track_webhook(
    payload: WebhookPayload,
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_secret(x_webhook_secret, settings)
    record = payload.record or {}
    track_id = record.get("id")
    if payload.table != "tracks" or not track_id:
        return {"queued": False, "reason": "not a track row"}
    if payload.type == "UPDATE":
        old = payload.old_record or {}
        if old.get("audio_url") == record.get("audio_url"):
            return {"queued": False, "reason": "audio unchanged"}
    elif payload.type != "INSERT":
        return {"queued": False, "reason": f"ignored {payload.type}"}
    if not record.get("audio_url"):
        return {"queued": False, "reason": "no audio"}

    background.add_task(_run, track_id, settings)
    return {"queued": True, "track_id": track_id}


@app.post("/analyze/{track_id}", status_code=status.HTTP_202_ACCEPTED)
def analyze_now(
    track_id: str,
    background: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    """Manual re-run for one track (same secret as the webhook)."""
    _check_secret(x_webhook_secret, settings)
    background.add_task(_run, track_id, settings)
    return {"queued": True, "track_id": track_id}
