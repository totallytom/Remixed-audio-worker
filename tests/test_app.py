import pytest
from fastapi.testclient import TestClient

from audio_worker import app as app_module


@pytest.fixture
def client(settings, monkeypatch):
    queued = []
    monkeypatch.setattr(app_module, "_run", lambda track_id, s: queued.append(track_id))
    app_module.app.dependency_overrides[app_module.get_settings] = lambda: settings
    c = TestClient(app_module.app)
    c.queued = queued
    yield c
    app_module.app.dependency_overrides.clear()


def insert(track_id="t1", audio="https://x/a.mp3"):
    return {"type": "INSERT", "table": "tracks", "record": {"id": track_id, "audio_url": audio}}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("headers", [{}, {"x-webhook-secret": "wrong"}])
def test_rejects_bad_secret(client, headers):
    r = client.post("/webhooks/track", json=insert(), headers=headers)
    assert r.status_code == 401
    assert client.queued == []


def test_queues_new_track(client):
    r = client.post("/webhooks/track", json=insert(), headers={"x-webhook-secret": "s3cret"})
    assert r.status_code == 202 and r.json()["queued"] is True
    assert client.queued == ["t1"]


def test_ignores_update_without_new_audio(client):
    body = {"type": "UPDATE", "table": "tracks",
            "record": {"id": "t1", "audio_url": "a"}, "old_record": {"id": "t1", "audio_url": "a"}}
    r = client.post("/webhooks/track", json=body, headers={"x-webhook-secret": "s3cret"})
    assert r.json()["queued"] is False
    assert client.queued == []


def test_requeues_when_audio_replaced(client):
    body = {"type": "UPDATE", "table": "tracks",
            "record": {"id": "t1", "audio_url": "b"}, "old_record": {"id": "t1", "audio_url": "a"}}
    client.post("/webhooks/track", json=body, headers={"x-webhook-secret": "s3cret"})
    assert client.queued == ["t1"]
