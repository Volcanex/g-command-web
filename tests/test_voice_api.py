import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.voice import api as voice_api


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    monkeypatch.setattr(voice_api, "TRANSCRIPT_DIR", tmp_path)
    lines = [json.dumps({"ts": "t1", "role": "user", "text": "hi"}), "not json",
             json.dumps({"ts": "t2", "role": "assistant", "text": "hello"}),
             json.dumps({"ts": "t3", "role": "system", "text": "x"})]
    (tmp_path / "app.jsonl").write_text("\n".join(lines))
    app = FastAPI()
    app.include_router(voice_api.router, prefix="/api/voice")
    return TestClient(app)


def test_history_needs_a_cookie(client):
    assert client.get("/api/voice/history").status_code == 401


def test_history_reads_the_app_transcript(client):
    client.cookies.set("seed_admin", "ok")
    r = client.get("/api/voice/history?session=app&limit=5")
    assert r.json() == {"session": "app", "turns": [
        {"ts": "t1", "role": "user", "text": "hi"}, {"ts": "t2", "role": "assistant", "text": "hello"}]}


def test_history_and_chat_refuse_other_sessions(client):
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/voice/history?session=../x").status_code == 422
    assert client.post("/api/voice/chat", json={"message": "a", "session": "+44"}).status_code == 422
