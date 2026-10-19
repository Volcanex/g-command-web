import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import auth
from core.api import admin, alerts, app as app_api


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(auth, "ADMIN_VALUE", "ok")
    monkeypatch.setattr(app_api.auth, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(auth, "DEVICES_FILE", tmp_path / "devices.json")
    monkeypatch.setattr(auth, "_cache", {"key": None, "devices": []})
    monkeypatch.setattr(admin, "_LOGIN_ATTEMPTS", {})
    monkeypatch.setattr(app_api, "_codes", {})
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pw")
    monkeypatch.setenv("PUBLIC_HOST", "command.example.com")
    a = FastAPI()
    a.include_router(app_api.router, prefix="/api/app")
    a.include_router(alerts.router, prefix="/api/alerts")
    return TestClient(a)


ADMIN = {"seed_admin": "ok"}


def pair(client, **body):
    return client.post("/api/app/pair", json={"name": "Phone", "platform": "ios", **body})


def test_pair_code_needs_sign_in_and_works_once(client):
    assert client.post("/api/app/pair/code").status_code == 401
    r = client.post("/api/app/pair/code", cookies=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["url"].startswith("gcommand://pair?server=https%3A%2F%2Fcommand.example.com&code=")
    first = pair(client, code=body["code"])
    assert first.status_code == 200
    assert first.json()["cookie_name"] == "seed_admin"
    assert first.json()["token"].startswith("gd_")
    assert pair(client, code=body["code"]).status_code == 401


def test_expired_code_is_refused(client, monkeypatch):
    code = client.post("/api/app/pair/code", cookies=ADMIN).json()["code"]
    app_api._codes[code] = 0
    assert pair(client, code=code).status_code == 401


def test_pair_with_password(client):
    assert pair(client, password="wrong").status_code == 401
    assert pair(client).status_code == 401
    assert pair(client, password="test-pw").status_code == 200


def test_failed_pairing_is_rate_limited(client):
    for _ in range(5):
        pair(client, code="guess")
    assert pair(client, password="test-pw").status_code == 429


def test_device_token_signs_in_and_revoke_signs_out(client):
    token = pair(client, password="test-pw").json()["token"]
    other = pair(client, password="test-pw").json()["token"]
    me = {"seed_admin": token}
    rows = client.get("/api/app/devices", cookies=me).json()["devices"]
    assert len(rows) == 2
    assert all("sha256" not in d for d in rows)
    mine = next(d for d in rows if d["current"])
    assert client.delete(f"/api/app/devices/{mine['id']}", cookies={"seed_admin": other}).status_code == 200
    assert client.get("/api/app/devices", cookies=me).status_code == 401
    assert client.get("/api/app/devices", cookies={"seed_admin": other}).status_code == 200
    assert client.delete("/api/app/devices/nope", cookies=ADMIN).status_code == 404


def test_device_file_holds_no_token(client, tmp_path):
    token = pair(client, password="test-pw").json()["token"]
    text = (tmp_path / "devices.json").read_text()
    assert token not in text
    assert (tmp_path / "devices.json").stat().st_mode & 0o777 == 0o600


def test_unknown_and_non_ascii_tokens_are_refused(client):
    for value in ("gd_unknown", "nope", "gd_é"):
        assert not auth.cookie_ok({"seed_admin": value})
    assert auth.cookie_ok(ADMIN)


NTFY = "\n".join(json.dumps(m) for m in [
    {"event": "open", "id": "o1"},
    {"event": "message", "id": "a1", "time": 100, "title": "Reminder", "message": "Bins"},
    {"event": "message", "id": "a2", "time": 300, "title": "brain-mcp", "message": "down", "tags": ["rotating_light"]},
    {"event": "message", "id": "a3", "time": 200, "title": "Vital reminder", "message": "Pay rent"},
    {"event": "message", "id": "a4", "time": 50, "title": "x", "click": "https://command.example.com/tickets?id=1"},
    "not json",
])


def test_alerts_parse_routes_and_tones():
    items = alerts.parse(NTFY, "https://command.example.com")
    assert [a["id"] for a in items] == ["a2", "a3", "a1", "a4"]
    by = {a["id"]: a for a in items}
    assert by["a2"]["tone"] == "danger" and by["a2"]["link"] == "/system"
    assert by["a3"]["tone"] == "accent" and by["a3"]["link"] == "/calendar"
    assert by["a1"]["tone"] == "plain"
    assert by["a4"]["link"] == "/tickets?id=1"


def test_alerts_route(client, monkeypatch):
    monkeypatch.setenv("NTFY_URL", "https://ntfy.example.com/secret-topic")
    seen = {}

    def fake(url, token):
        seen["url"] = url
        return NTFY

    monkeypatch.setattr(alerts, "_poll", fake)
    assert client.get("/api/alerts").status_code == 401
    r = client.get("/api/alerts", cookies=ADMIN)
    assert r.status_code == 200
    assert r.json()["cursor"] == "a2"
    assert "since=12h" in seen["url"]
    assert "secret-topic" not in r.text
    assert client.get("/api/alerts?since=a2", cookies=ADMIN).status_code == 200
    assert "since=a2" in seen["url"]
    assert client.get("/api/alerts?since=../x", cookies=ADMIN).status_code == 400


def test_alerts_upstream_failure_hides_the_url(client, monkeypatch):
    import urllib.error
    monkeypatch.setenv("NTFY_URL", "https://ntfy.example.com/secret-topic")

    def boom(url, token):
        raise urllib.error.URLError("https://ntfy.example.com/secret-topic refused")

    monkeypatch.setattr(alerts, "_poll", boom)
    r = client.get("/api/alerts", cookies=ADMIN)
    assert r.status_code == 502
    assert "secret-topic" not in r.text
