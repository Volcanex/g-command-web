"""Voice proxy for the app session: uploads, attachments, block expansion,
history and the streamed chat. The Voice service itself is stubbed."""
import io
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.voice import api as voice_api


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    monkeypatch.setattr(voice_api, "TRANSCRIPT_DIR", tmp_path)
    monkeypatch.setattr(voice_api, "UPLOAD_DIR", tmp_path / "uploads")
    app = FastAPI()
    app.include_router(voice_api.router, prefix="/api/voice")
    c = TestClient(app)
    c.cookies.set("seed_admin", "ok")
    return c


def _fake_panel(monkeypatch):
    import core.panels as panels
    monkeypatch.setattr(panels, "build", lambda name, ctx: {
        "v": 1, "id": name, "title": "Today", "icon": "calendar-blank", "link": "/calendar",
        "link_label": "Open calendar", "meta": "3 today", "state": "ok", "message": "",
        "refresh": 300, "blocks": [{"type": "rows", "rows": [{"id": "a", "title": "Dentist"}]}]})


def test_upload_needs_a_cookie_and_a_known_type(client):
    anon = TestClient(client.app)
    assert anon.post("/api/voice/upload", content=b"x", headers={"Content-Type": "image/png"}).status_code == 401
    assert client.post("/api/voice/upload", content=b"x",
                       headers={"Content-Type": "application/x-msdownload"}).status_code == 415
    assert client.post("/api/voice/upload", content=b"",
                       headers={"Content-Type": "image/png"}).status_code == 400


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(voice_api, "MAX_IMAGE", 10)
    r = client.post("/api/voice/upload", content=b"x" * 11, headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 413
    assert not list((voice_api.UPLOAD_DIR).glob("*")) if voice_api.UPLOAD_DIR.exists() else True


def test_upload_round_trip_behind_the_cookie(client):
    r = client.post("/api/voice/upload", content=b"\x89PNGdata",
                    headers={"Content-Type": "image/png", "X-Filename": "my%20photo.png"})
    assert r.status_code == 200
    up = r.json()
    assert up["kind"] == "image" and up["name"] == "my photo.png" and up["size"] == 8
    assert up["url"] == f"/api/voice/files/{up['id']}" and set(up) == {"id", "kind", "name", "content_type", "size", "url"}
    got = client.get(up["url"])
    assert got.status_code == 200 and got.content == b"\x89PNGdata" and got.headers["content-type"] == "image/png"
    assert TestClient(client.app).get(up["url"]).status_code == 401
    assert client.get("/api/voice/files/../../etc").status_code == 404
    assert client.get("/api/voice/files/" + "0" * 32).status_code == 404
    mode = (voice_api.UPLOAD_DIR / f"{up['id']}.png").stat().st_mode & 0o777
    assert mode == 0o600


def _stub_voice(monkeypatch, reply):
    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout):
        sent.update(json.loads(req.data))
        return Resp(json.dumps(reply).encode())
    monkeypatch.setattr(voice_api.urllib.request, "urlopen", fake)
    return sent


def test_web_chat_is_unchanged(client, monkeypatch):
    sent = _stub_voice(monkeypatch, {"reply": "hi"})
    assert client.post("/api/voice/chat", json={"message": "a"}).json() == {"reply": "hi"}
    assert sent == {"message": "a", "session": "web"}
    assert client.post("/api/voice/chat", json={"message": "a", "attachments": ["0" * 32]}).status_code == 400


def test_app_chat_sends_budget_attachments_grant_and_expands_panels(client, monkeypatch):
    _fake_panel(monkeypatch)
    up = client.post("/api/voice/upload", content=b"ABC", headers={"Content-Type": "image/jpeg"}).json()
    note = client.post("/api/voice/upload", content=b"hello", headers={"Content-Type": "text/plain",
                                                                       "X-Filename": "n.txt"}).json()
    sent = _stub_voice(monkeypatch, {"reply": "Three today.", "blocks": [
        {"type": "panel", "name": "calendar"}, {"type": "detail", "text": "small"}]})
    r = client.post("/api/voice/chat", json={"message": "what's on", "session": "app",
                                             "budget": {"lines": 9, "chars_per_line": 38},
                                             "attachments": [up["id"], note["id"]]})
    out = r.json()
    assert out["reply"] == "Three today."
    assert out["blocks"][0]["type"] == "panel" and out["blocks"][0]["title"] == "Today"
    assert out["blocks"][0]["blocks"][0]["rows"][0]["title"] == "Dentist"
    assert out["blocks"][1] == {"type": "detail", "text": "small"}
    assert sent["budget"] == {"lines": 9, "chars_per_line": 38}
    assert sent["images"] == [{"content_type": "image/jpeg", "data": "QUJD"}]
    assert sent["files"] == [{"name": "n.txt", "content_type": "text/plain", "text": "hello"}]
    assert [a["id"] for a in sent["attachments"]] == [up["id"], note["id"]]
    from pages.sessions.api import grant_ok
    assert sent["activity"]["url"].endswith("/api/sessions/activity") and grant_ok(sent["activity"]["grant"])


def test_chat_validation(client, monkeypatch):
    _stub_voice(monkeypatch, {"reply": "x"})
    bad = [{"message": "a", "session": "app", "budget": {"lines": 0, "chars_per_line": 30}},
           {"message": "a", "session": "app", "attachments": ["x"] * 5},
           {"message": "a", "session": "whatsapp"}]
    for body in bad:
        assert client.post("/api/voice/chat", json=body).status_code == 422, body
    assert client.post("/api/voice/chat", json={"message": "a", "session": "app",
                                                "attachments": ["f" * 32]}).status_code == 400


def test_history_carries_blocks_and_old_panels_become_links(client, tmp_path):
    lines = [{"ts": "t1", "role": "user", "text": "pic [photo]", "attachments": [{"id": "a" * 32}]},
             {"ts": "t2", "role": "assistant", "text": "today", "blocks": [
                 {"type": "panel", "name": "calendar"},
                 {"type": "fold", "title": "More", "blocks": [{"type": "panel", "name": "tasks"}]}]},
             {"ts": "t3", "role": "assistant", "text": "plain"}]
    (tmp_path / "app.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    turns = client.get("/api/voice/history?session=app").json()["turns"]
    assert turns[0]["attachments"] == [{"id": "a" * 32}]
    first = turns[1]["blocks"][0]
    assert first["type"] == "rows" and first["rows"][0]["link"] == "/calendar"
    assert turns[1]["blocks"][1]["blocks"][0]["rows"][0]["link"] == "/todos"
    assert "blocks" not in turns[2]


def test_stream_relays_and_expands_done(client, monkeypatch):
    _fake_panel(monkeypatch)
    body = "\n".join(json.dumps(e) for e in [
        {"t": "delta", "text": "Hi"}, {"t": "tool", "name": "show_panel"},
        {"t": "done", "reply": "Hi", "blocks": [{"type": "panel", "name": "calendar"}], "tools": [], "ms": 5}]) + "\n"
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=body.encode(), headers={"content-type": "application/x-ndjson"})
    real = httpx.AsyncClient
    monkeypatch.setattr(voice_api.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    r = client.post("/api/voice/chat/stream", json={"message": "hi", "session": "app"})
    evs = [json.loads(x) for x in r.text.splitlines()]
    assert seen["path"] == "/chat/stream" and seen["body"]["session"] == "app"
    assert [e["t"] for e in evs] == ["delta", "tool", "done"]
    assert evs[-1]["blocks"][0]["title"] == "Today"
    assert client.post("/api/voice/chat/stream", json={"message": "hi"}).status_code == 400
