import io
import json
import urllib.error

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.api.gadmin_panel as gp

COOKIES = {"seed_admin": "ok"}


@pytest.fixture(autouse=True)
def _reset_roster_cache():
    gp._roster_cache["built_at"] = 0.0
    gp._roster_cache["roster"] = {}
    yield
    gp._roster_cache["built_at"] = 0.0
    gp._roster_cache["roster"] = {}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(gp.router, prefix="/api/gadmin_panel")
    return TestClient(app)


class FakeHTTPResponse:
    def __init__(self, status, payload, content_type="application/json"):
        self.status = status
        if content_type == "application/json":
            self._body = json.dumps(payload).encode()
        else:
            self._body = payload.encode() if isinstance(payload, str) else payload
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(responses):
    """responses: dict[url_without_query_or_prefix_match] -> (status, payload, content_type)
    keyed by substring match against the request's full_url."""
    def _urlopen(req, timeout=None):
        url = req.full_url
        for key, spec in responses.items():
            if key in url:
                status, payload, ctype = spec
                if status >= 400:
                    body = json.dumps(payload).encode() if payload is not None else b""
                    raise urllib.error.HTTPError(url, status, "error", {}, io.BytesIO(body))
                return FakeHTTPResponse(status, payload, ctype)
        raise TimeoutError(f"no fake route for {url}")
    return _urlopen


# ---------------------------------------------------------------- gate --


def test_tickets_requires_admin_cookie(client, manifest_dir):
    r = client.get("/api/gadmin_panel/tickets")
    assert r.status_code == 401


def test_tickets_ok_with_cookie(client, manifest_dir, monkeypatch):
    monkeypatch.setattr(gp.urllib.request, "urlopen", _fake_urlopen({}))
    r = client.get("/api/gadmin_panel/tickets", cookies=COOKIES)
    assert r.status_code == 200


def test_tickets_ok_with_device_token(client, manifest_dir, monkeypatch, tmp_path):
    from core import auth
    monkeypatch.setattr(auth, "DEVICES_FILE", tmp_path / "devices.json")
    monkeypatch.setattr(auth, "_cache", {"key": None, "devices": []})
    monkeypatch.setattr(gp.urllib.request, "urlopen", _fake_urlopen({}))
    token, _ = auth.add_device("Phone", "ios")
    assert client.get("/api/gadmin_panel/tickets", cookies={"seed_admin": token}).status_code == 200
    assert client.get("/api/gadmin_panel/tickets", cookies={"seed_admin": "gd_nope"}).status_code == 401


def test_unset_cookie_value_fails_closed(client, manifest_dir, monkeypatch):
    """The value used to default to "ok", so a deploy that forgot it took a
    forged cookie. Unset must refuse everything, including an empty cookie."""
    monkeypatch.delenv("ADMIN_COOKIE_VALUE")
    assert client.get("/api/gadmin_panel/tickets", cookies=COOKIES).status_code == 401
    assert client.get("/api/gadmin_panel/tickets", cookies={"seed_admin": ""}).status_code == 401


def test_server_refuses_to_start_without_cookie_value():
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    env = {k: v for k, v in os.environ.items() if k != "ADMIN_COOKIE_VALUE"}
    r = subprocess.run([sys.executable, "-c", "import server"], cwd=root, env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode != 0
    assert "ADMIN_COOKIE_VALUE" in r.stderr


# ---------------------------------------------------------- token header --


def test_proxy_attaches_token_header(client, manifest_dir, monkeypatch):
    captured = {}

    def _urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        captured["timeout"] = timeout
        return FakeHTTPResponse(200, {"tickets": []})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets", cookies=COOKIES)
    assert r.status_code == 200
    # urllib title-cases header keys it stores (Request.add_header does this)
    assert captured["headers"].get("X-gadmin-token") == "test-secret-token"
    assert captured["timeout"] == gp.REQUEST_TIMEOUT_S


# -------------------------------------------------------------- roster --


def test_roster_is_cached_between_calls(client, manifest_dir, monkeypatch):
    calls = {"n": 0}

    def _urlopen(req, timeout=None):
        calls["n"] += 1
        return FakeHTTPResponse(200, {"tickets": []})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    gp._get_roster()
    first = calls["n"]
    assert first > 0
    gp._get_roster()
    # A second call inside the TTL must not re-probe any project.
    assert calls["n"] == first


def test_roster_rebuilds_after_ttl(client, manifest_dir, monkeypatch):
    calls = {"n": 0}

    def _urlopen(req, timeout=None):
        calls["n"] += 1
        return FakeHTTPResponse(200, {"tickets": []})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    gp._get_roster()
    first = calls["n"]
    gp._roster_cache["built_at"] -= gp.ROSTER_TTL_S + 1
    gp._get_roster()
    assert calls["n"] > first


def test_roster_only_includes_projects_that_speak_the_contract(client, manifest_dir, monkeypatch):
    def _urlopen(req, timeout=None):
        if "alpha" in req.full_url:
            return FakeHTTPResponse(200, {"tickets": []})
        raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, io.BytesIO(b""))

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    roster = gp._get_roster()
    assert "alpha" in roster
    assert "beta" not in roster
    assert "noport" not in roster  # no domain and no port, never a candidate


def test_roster_excludes_a_200_that_is_not_actually_the_contract(client, manifest_dir, monkeypatch):
    """Seen live against gdesign: a catch-all SPA route 200s any unmatched
    path including /api/gadmin/tickets, serving index.html. A bare status
    check would misfile it as a contract speaker; the shape check must not."""
    def _urlopen(req, timeout=None):
        return FakeHTTPResponse(200, "<!doctype html>...", content_type="text/html")

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    roster = gp._get_roster()
    assert roster == {}


# -------------------------------------------------------- degraded state --


def test_down_project_degrades_without_erroring_whole_page(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com", "beta": "https://beta.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()

    def _urlopen(req, timeout=None):
        if "alpha" in req.full_url:
            return FakeHTTPResponse(200, {"tickets": [{"id": "t1", "severity": "minor", "updated_at": "2026-01-01"}]})
        raise TimeoutError("connection refused")

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets", cookies=COOKIES)
    assert r.status_code == 200
    body = r.json()
    assert len(body["tickets"]) == 1
    assert body["tickets"][0]["project"] == "alpha"
    assert body["degraded"] == ["beta"]


# ----------------------------------------------------------- no leaked token --


def test_browser_payload_never_contains_the_token(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()

    def _urlopen(req, timeout=None):
        return FakeHTTPResponse(200, {"tickets": [{"id": "t1", "severity": "minor", "note": "hello"}]})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets", cookies=COOKIES)
    assert r.status_code == 200
    assert "test-secret-token" not in r.text


# ------------------------------------------------------------- filtering --


def test_severity_filter_applied_after_aggregation(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()

    def _urlopen(req, timeout=None):
        return FakeHTTPResponse(200, {"tickets": [
            {"id": "t1", "severity": "minor"},
            {"id": "t2", "severity": "critical"},
        ]})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets", params={"severity": "critical"}, cookies=COOKIES)
    body = r.json()
    assert [t["id"] for t in body["tickets"]] == ["t2"]


def test_project_filter_only_probes_that_project(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com", "beta": "https://beta.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()
    hit = []

    def _urlopen(req, timeout=None):
        hit.append(req.full_url)
        return FakeHTTPResponse(200, {"tickets": []})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets", params={"project": "alpha"}, cookies=COOKIES)
    assert r.status_code == 200
    assert all("alpha" in u for u in hit)


def test_unknown_project_filter_is_404(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()
    r = client.get("/api/gadmin_panel/tickets", params={"project": "ghost"}, cookies=COOKIES)
    assert r.status_code == 404


# --------------------------------------------------------------- detail --


def test_get_ticket_proxies_to_project_base(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()

    def _urlopen(req, timeout=None):
        assert req.full_url == "https://alpha.example.com/api/gadmin/tickets/abc123"
        return FakeHTTPResponse(200, {"id": "abc123", "note": "hi"})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets/alpha/abc123", cookies=COOKIES)
    assert r.status_code == 200
    assert r.json()["id"] == "abc123"


def test_get_ticket_unknown_project_404(client, manifest_dir):
    r = client.get("/api/gadmin_panel/tickets/ghost/abc123", cookies=COOKIES)
    assert r.status_code == 404


def test_brief_returns_markdown(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()

    def _urlopen(req, timeout=None):
        return FakeHTTPResponse(200, "# ticket\n\nsome note", content_type="text/markdown")

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets/alpha/abc123/brief", cookies=COOKIES)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "# ticket" in r.text


def test_brief_unreachable_project_is_502(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()

    def _urlopen(req, timeout=None):
        raise TimeoutError("connection refused")

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.get("/api/gadmin_panel/tickets/alpha/abc123/brief", cookies=COOKIES)
    assert r.status_code == 502


# --------------------------------------------------------------- patch --


def test_patch_forwards_status_and_reply(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()
    captured = {}

    def _urlopen(req, timeout=None):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return FakeHTTPResponse(200, {"id": "abc123", "status": "baked"})

    monkeypatch.setattr(gp.urllib.request, "urlopen", _urlopen)
    r = client.patch(
        "/api/gadmin_panel/tickets/alpha/abc123",
        json={"status": "baked", "reply": "baked in commit abc"},
        cookies=COOKIES,
    )
    assert r.status_code == 200
    assert captured["method"] == "PATCH"
    assert captured["url"] == "https://alpha.example.com/api/gadmin/tickets/abc123"
    assert captured["body"] == {"status": "baked", "reply": "baked in commit abc"}


def test_patch_empty_body_is_400(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()
    r = client.patch("/api/gadmin_panel/tickets/alpha/abc123", json={}, cookies=COOKIES)
    assert r.status_code == 400


def test_patch_rejects_invalid_status(client, manifest_dir, monkeypatch):
    gp._roster_cache["roster"] = {"alpha": "https://alpha.example.com"}
    gp._roster_cache["built_at"] = __import__("time").time()
    r = client.patch(
        "/api/gadmin_panel/tickets/alpha/abc123",
        json={"status": "not-a-real-status"},
        cookies=COOKIES,
    )
    assert r.status_code == 422
