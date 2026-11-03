"""Preact pages: compile.py bundles pages/<slug>/app.js, and a failed bundle
never stops the build (last good bundle, else content.html)."""
import json
import shutil

import pytest

import compile as c

needs_esbuild = pytest.mark.skipif(not c.ESBUILD.is_file(), reason="node_modules not installed (npm ci)")


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A one-page site in tmp_path, with output/ and var/bundles/ there too."""
    pages = tmp_path / "pages"
    page = pages / "demo"
    page.mkdir(parents=True)
    (page / "config.json").write_text(json.dumps({"title": "Demo"}))
    (page / "content.html").write_text("<p>plain demo</p>")
    out = tmp_path / "output"
    monkeypatch.setattr(c, "PAGES_DIR", pages)
    monkeypatch.setattr(c, "OUTPUT_DIR", out)
    monkeypatch.setattr(c, "BUNDLE_OUT", out / "js" / "pages")
    monkeypatch.setattr(c, "LAST_GOOD_DIR", tmp_path / "var" / "bundles")
    monkeypatch.setattr(c, "STATIC_SRC", tmp_path / "static")
    monkeypatch.setattr(c, "_bundle_status", {})
    monkeypatch.setenv("G_DESIGN_DOCS", "")
    return tmp_path


def build(site):
    c.main()
    return (site / "output" / "demo.html").read_text()


GOOD = 'const n = document.querySelector("[data-page-app]"); if (n) n.textContent = "built";\n'


@needs_esbuild
def test_good_bundle_mounts_and_is_stamped(site):
    (site / "pages/demo/app.js").write_text(GOOD)
    page = build(site)
    assert "<div data-page-app></div>" in page
    assert '<script type="module" src="/js/pages/demo.js?v=' in page
    assert "plain demo" not in page
    assert (site / "output/js/pages/demo.js").is_file()
    status = json.loads((site / "var/bundles/status.json").read_text())
    assert status["demo"]["state"] == "built"


@needs_esbuild
def test_failed_bundle_keeps_last_good_and_build_finishes(site):
    (site / "pages/demo/app.js").write_text(GOOD)
    first = build(site)
    (site / "pages/demo/app.js").write_text("import { nope } from './missing.js';\n")
    second = build(site)  # main() returns: the server would still start
    assert first.split("demo.js?v=")[1][:10] == second.split("demo.js?v=")[1][:10]
    assert "last good build" in second
    assert (site / "output/js/pages/demo.js").is_file()
    status = json.loads((site / "var/bundles/status.json").read_text())
    assert status["demo"]["state"] == "stale" and "missing.js" in status["demo"]["error"]


def test_failed_bundle_with_no_last_good_serves_content(site, monkeypatch):
    (site / "pages/demo/app.js").write_text(GOOD)
    monkeypatch.setattr(c, "ESBUILD", site / "no-esbuild")  # as on a checkout without npm ci
    page = build(site)
    assert "plain demo" in page
    assert "This page did not build" in page
    assert "data-page-app" not in page
    status = json.loads((site / "var/bundles/status.json").read_text())
    assert status["demo"]["state"] == "failed" and "npm ci" in status["demo"]["error"]


def test_nav_uses_href_and_app_nav_keeps_home_out_of_the_apps():
    nav = c.build_nav_html([{"slug": "index", "href": "/", "nav": True, "nav_section": "Dash", "nav_label": "Home"}])
    assert 'href="/"' in nav
    from core.panels.manifest import build_manifest
    slugs = [e["slug"] for s in build_manifest(c.PAGES_DIR)["sections"] for e in s["entries"]]
    assert "index" not in slugs and "full-dash" in slugs


def test_root_serves_home(monkeypatch):
    if not (c.OUTPUT_DIR / "index.html").is_file():
        pytest.skip("not compiled: run compile.py")
    from fastapi.testclient import TestClient
    import server
    client = TestClient(server.app)
    client.cookies.set("seed_admin", "ok")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "<title>Home - " in r.text
    assert client.get("/full-dash", follow_redirects=False).status_code == 200


def test_todos_redirects_permanently_to_the_calendar():
    from fastapi.testclient import TestClient
    import server
    client = TestClient(server.app)
    r = client.get("/todos", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/calendar"
    r = client.get("/todos/?status=done", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/calendar?status=done"
