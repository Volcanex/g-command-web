import urllib.error

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api import brain as brain_api  # noqa: E402


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_send(method, url, body, headers):
        calls.append((method, url, body, headers))
        return 404 if url.endswith("/missing") else 200, "application/json", b'{"ok": true}'

    monkeypatch.setattr(brain_api, "_send", fake_send)
    monkeypatch.setattr(brain_api, "UPSTREAM", "http://brain.test")
    monkeypatch.setattr(brain_api, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(brain_api, "ADMIN_VALUE", "ok")
    return calls


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(brain_api.router, prefix="/api/brain")
    return TestClient(app)


def test_requires_cookie(client, sent):
    assert client.get("/api/brain/api/status").status_code == 401
    assert client.patch("/api/brain/api/todos/x", json={"status": "done"}).status_code == 401
    assert sent == []


def test_forwards_path_query_and_body(client, sent):
    client.cookies.set("seed_admin", "ok")
    r = client.get("/api/brain/api/todos?status=open")
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.patch("/api/brain/api/todos/some slug", json={"status": "done"})
    assert r.status_code == 200
    assert sent[0][:3] == ("GET", "http://brain.test/api/todos?status=open", None)
    method, url, body, headers = sent[1]
    assert (method, url, body) == ("PATCH", "http://brain.test/api/todos/some%20slug", b'{"status":"done"}')
    assert headers["content-type"] == "application/json"


def test_passes_upstream_status_and_maps_unreachable(client, sent, monkeypatch):
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/brain/api/missing").status_code == 404

    def down(*a):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(brain_api, "_send", down)
    assert client.get("/api/brain/api/status").status_code == 502
