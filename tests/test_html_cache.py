import ast
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "server.py"
    tree = ast.parse(source.read_text())
    # Router discovery replaces modules in sys.modules; keep suite fixtures intact.
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and
        (isinstance(node.value.func, ast.Name) and node.value.func.id == "discover_apis" or
         isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "include_router"))]
    server = types.ModuleType("perf_server_test")
    server.__file__ = str(source)
    exec(compile(tree, str(source), "exec"), server.__dict__)
    monkeypatch.setattr(server, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(server, "_OUTPUT_RESOLVED", tmp_path.resolve())
    for name in ("index", "notes", "projects", "system", "not-found"):
        (tmp_path / (name + ".html")).write_text("<!doctype html><title>Fixture " + name + "</title>")
    @server.app.post("/api/test-write")
    def write():
        return {"ok": True}
    with TestClient(server.app) as client:
        client.cookies.set("seed_admin", "ok")
        yield client, tmp_path


@pytest.mark.parametrize("path", ["/", "/notes", "/projects", "/system", "/notes.html", "/notes/example"])
def test_matching_etag_returns_empty_304(client, path):
    browser, _ = client
    first = browser.get(path)
    assert first.status_code == 200
    for tag in (first.headers["etag"], "W/" + first.headers["etag"], '"other", ' + first.headers["etag"], "*"):
        result = browser.get(path, headers={"If-None-Match": tag})
        assert result.status_code == 304
        assert result.content == b""
        assert result.headers["etag"] == first.headers["etag"]
        assert result.headers["cache-control"] == "no-cache"


def test_changed_file_and_unmatched_etag_return_full_html(client):
    browser, root = client
    first = browser.get("/notes")
    (root / "notes.html").write_text("<!doctype html><title>Updated fixture document</title>")
    changed = browser.get("/notes", headers={"If-None-Match": first.headers["etag"]})
    assert changed.status_code == 200
    assert "Updated" in changed.text
    assert changed.headers["etag"] != first.headers["etag"]


def test_conditional_request_still_checks_auth_and_missing_page(client):
    browser, _ = client
    tag = browser.get("/notes").headers["etag"]
    assert browser.get("/missing", headers={"If-None-Match": "*"}).status_code == 404
    browser.cookies.clear()
    assert browser.get("/notes", headers={"If-None-Match": tag}, follow_redirects=False).status_code == 302


def test_successful_write_invalidates_panel_snapshots(client, monkeypatch):
    from core.panels import context
    browser, _ = client
    invalidations = []
    monkeypatch.setattr(context, "invalidate", lambda: invalidations.append(True))
    assert browser.post("/api/test-write").status_code == 200
    assert invalidations == [True]
    browser.post("/api/missing")
    assert invalidations == [True]
