"""/api/diagram: gcore graph + live health, Studio clients and edge liveness; degrades, never 500s."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api import diagram

GRAPH = {
    "nodes": [
        {"id": "host:h", "kind": "host", "name": "h", "health": None},
        {"id": "service:g-studio", "kind": "service", "name": "g-studio", "health": None},
        {"id": "service:brain-api", "kind": "service", "name": "brain-api", "health": None},
        {"id": "project:g-studio", "kind": "project", "name": "g-studio", "health": None, "clients": None,
         "path": "/x/g-studio"},
        {"id": "project:g-command-web", "kind": "project", "name": "g-command-web", "health": None},
        {"id": "repo:gbrain", "kind": "repo", "name": "gbrain", "health": None},
        {"id": "dependency:openrouter", "kind": "dependency", "name": "openrouter", "health": None},
    ],
    "edges": [
        {"kind": "runs_on", "from": "service:g-studio", "to": "host:h"},
        {"kind": "has_service", "from": "project:g-studio", "to": "service:g-studio"},
        {"kind": "has_service", "from": "repo:gbrain", "to": "service:brain-api"},
        {"kind": "connects", "from": "project:g-command-web", "to": "project:g-studio", "via": "http",
         "sources": ["declared"], "drift": None},
        {"kind": "connects", "from": "project:g-command-web", "to": "repo:gbrain", "via": "http",
         "sources": ["declared"], "drift": None},
        {"kind": "connects", "from": "project:g-studio", "to": "dependency:openrouter", "via": "http",
         "sources": ["declared"], "drift": None},
        {"kind": "connects", "from": "project:g-studio", "to": "repo:gbrain", "via": "vendor",
         "sources": ["declared"], "drift": "unobserved"},
    ],
    "problems": [],
}
STATUS = {"checked_at": "2026-11-03T00:00:00Z",
          "services": [{"id": "g-studio", "state": "down", "detail": "HTTP 502"},
                       {"id": "brain-api", "state": "up", "detail": "HTTP 200"}],
          "dependencies": [{"id": "openrouter", "state": "up", "detail": "balance ok"}]}
NERVES = {"nodes": [{"type": "repo", "repo": "g-studio", "pair": "symlink", "nerve_dirs": 3, "compliant": True}]}
BLOCKS = {"blocks": {"repo": {"label": "GitHub repository", "rests_on": {"module": "gstudio.repos"}}},
          "projects": [{"id": "fixture-a", "kind": "seed", "blocks": [{"id": "repo"}]}],
          "totals": {"repo": 1}}


@pytest.fixture
def client(monkeypatch):
    diagram._graph.update(at=0.0, value=None, error=None, refreshing=False, took_s=None)
    diagram._live.update(at=0.0, value=None)
    monkeypatch.setattr(diagram, "_assemble", lambda: json.loads(json.dumps(GRAPH)))
    monkeypatch.setenv("STUDIO_GADMIN_URL", "http://studio.invalid")
    app = FastAPI()
    app.include_router(diagram.router, prefix="/api/diagram")
    c = TestClient(app)
    c.cookies.set("seed_admin", "ok")
    return c


def fake_sources(monkeypatch, status=True, nerves=True, studio=True, seen=None):
    def get(url, headers=None):
        if seen is not None:
            seen.append((url, headers))
        if url.endswith("/api/status"):
            return (STATUS, None) if status else (None, "unreachable: refused")
        if url.endswith("/api/nerves"):
            return (NERVES, None) if nerves else (None, "HTTP 502")
        return (BLOCKS, None) if studio else (None, "unreachable: refused")
    monkeypatch.setattr(diagram, "_get_json", get)


def by_id(body):
    return {n["id"]: n for n in body["nodes"]}


def test_needs_cookie(client):
    client.cookies.clear()
    assert client.get("/api/diagram").status_code == 401


def test_joined_payload(client, monkeypatch):
    seen = []
    fake_sources(monkeypatch, seen=seen)
    body = client.get("/api/diagram").json()
    n = by_id(body)
    assert n["service:g-studio"]["health"]["state"] == "down"
    assert n["project:g-studio"]["health"]["state"] == "down"
    assert n["project:g-studio"]["health"]["nerves"]["pair"] == "symlink"
    assert n["host:h"]["health"]["services"] == {"g-studio": "down"}
    assert n["dependency:openrouter"]["health"]["state"] == "up"
    assert n["project:g-studio"]["clients"][0]["id"] == "fixture-a"
    assert n["project:g-studio"]["blocks"]["repo"]["rests_on"] == {"module": "gstudio.repos"}
    live = {(e["from"], e["to"], e["via"]): e["live"] for e in body["edges"] if e["kind"] == "connects"}
    assert live[("project:g-command-web", "project:g-studio", "http")] == "down"
    assert live[("project:g-command-web", "repo:gbrain", "http")] == "up"
    assert live[("project:g-studio", "dependency:openrouter", "http")] == "up"
    assert live[("project:g-studio", "repo:gbrain", "vendor")] is None
    assert body["summary"] == {"nodes": 7, "edges": 7, "drift": 1, "live_down": 1, "clients": 1}
    studio_call = [h for u, h in seen if u.startswith("http://studio.invalid")][0]
    assert studio_call == {"X-Gadmin-Token": "test-secret-token"}
    assert "test-secret-token" not in json.dumps(body)


def test_degrades_when_everything_is_down(client, monkeypatch):
    fake_sources(monkeypatch, status=False, nerves=False, studio=False)
    r = client.get("/api/diagram")
    assert r.status_code == 200
    body = r.json()
    n = by_id(body)
    assert n["project:g-studio"]["clients"] is None and n["service:g-studio"]["health"] is None
    assert body["sources"]["clients"] == {"ok": False, "reason": "unreachable: refused", "count": None}
    assert body["sources"]["status"]["ok"] is False
    assert all(e.get("live") is None for e in body["edges"] if e["kind"] == "connects")


def test_no_token_means_no_studio_call(client, monkeypatch):
    seen = []
    fake_sources(monkeypatch, seen=seen)
    monkeypatch.delenv("GADMIN_TOKEN")
    body = client.get("/api/diagram").json()
    assert body["sources"]["clients"]["ok"] is False and "GADMIN_TOKEN" in body["sources"]["clients"]["reason"]
    assert not any(u.startswith("http://studio.invalid") for u, _ in seen)


def test_studio_wrong_shape(client, monkeypatch):
    fake_sources(monkeypatch)
    real = diagram._get_json
    monkeypatch.setattr(diagram, "_get_json",
                        lambda u, h=None: ({"tickets": []}, None) if "studio" in u else real(u, h))
    body = client.get("/api/diagram").json()
    assert by_id(body)["project:g-studio"]["clients"] is None
    assert body["sources"]["clients"]["reason"] == "Studio answered without a projects list"


def test_gcore_failure_is_not_a_500(client, monkeypatch):
    fake_sources(monkeypatch)
    monkeypatch.setattr(diagram, "_assemble", lambda: (_ for _ in ()).throw(RuntimeError("bad manifest")))
    r = client.get("/api/diagram")
    assert r.status_code == 200 and r.json()["sources"]["gcore"]["ok"] is False
    assert "bad manifest" in r.json()["graph"]["error"]


def test_graph_cached(client, monkeypatch):
    fake_sources(monkeypatch)
    calls = []
    monkeypatch.setattr(diagram, "_assemble", lambda: calls.append(1) or json.loads(json.dumps(GRAPH)))
    client.get("/api/diagram")
    client.get("/api/diagram")
    assert len(calls) == 1


def test_studio_port_from_manifest(manifest_dir, monkeypatch):
    monkeypatch.delenv("STUDIO_GADMIN_URL", raising=False)
    (manifest_dir / "manifest.json").write_text(json.dumps({"services": [{"id": "g-studio", "port": 8240}]}))
    assert diagram._studio_base() == "http://127.0.0.1:8240"
