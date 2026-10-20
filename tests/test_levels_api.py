import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from pages.levels import api as levels_api

ROW = {"ts": "2026-10-18T17:00:00", "gate": "correct.copy.voice", "version": 2, "charter": "g-site",
       "repo": "g-site", "path": "pages", "result": "caught", "note": "x", "by": "agent", "id": "abcdef12"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    log = tmp_path / "results.jsonl"
    log.write_text(json.dumps(ROW) + "\n")
    # The grade route shells out to `glevels grade`, which honours GLEVELS_LOG, so the real log is never touched.
    monkeypatch.setenv("GLEVELS_LOG", str(log))
    app = FastAPI()
    app.include_router(levels_api.router, prefix="/api/levels")
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    c = TestClient(app)
    c.log = log
    return c


def authed(client):
    client.cookies.set("seed_admin", "ok")
    return client


@pytest.fixture
def project_export(manifest_dir, monkeypatch):
    (manifest_dir / "manifest.json").write_text(json.dumps({"projects": [
        {"id": "gbrowser", "url": "https://github.com/Volcanex/g-browser.git"},
        {"id": "g-site", "url": "git@github.com:Volcanex/g-site.git"},
        {"id": "uncovered"},
    ]}))
    names = {"gbrowser": ["gbrowser", "g-browser"], "g-site": ["g-site"], "uncovered": ["uncovered"]}
    counts = {"met": 0, "attempted": 0, "waived": 0, "impossible": 0,
              "caught": 0, "silent": 0, "not-run": 0, "hook": 0}
    views = {pid: {"repos": repos, "charter": None, "chain": [], "gates": [],
                   "counts": dict(counts), "blocking": {"total": 0, "silent": 0, "failing": 0}}
             for pid, repos in names.items()}
    views["gbrowser"].update({
        "charter": "g-browser",
        "chain": [{"id": "g-system", "title": "G-System"}, {"id": "g-browser", "title": "Browser"}],
        "gates": [{"gate": "correct.browser.check", "charter": "g-browser", "version": 1,
                   "trigger": "every-run", "sensor": "command", "blocking": True, "waived": False,
                   "state": "caught", "last": "2026-10-20T12:00:00", "result": "caught"}],
        "counts": {**counts, "caught": 1}, "blocking": {"total": 1, "silent": 0, "failing": 1},
    })
    compact = {pid: {"charter": view["charter"], "counts": view["counts"], "blocking": view["blocking"],
                     "total": len(view["gates"])} for pid, view in views.items()}
    export = SimpleNamespace(projects_view=Mock(return_value=compact),
                             project_view=Mock(side_effect=lambda repos: views[repos[0]]))
    monkeypatch.setattr(levels_api, "_export", lambda: export)
    return SimpleNamespace(export=export, names=names, views=views, compact=compact)


def assert_no_notes(value):
    if isinstance(value, dict):
        assert "note" not in value
        for item in value.values():
            assert_no_notes(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_notes(item)


def test_every_route_requires_cookie(client):
    assert client.get("/api/levels/snapshot").status_code == 401
    assert client.get("/api/levels/sample").status_code == 401
    assert client.get("/api/levels/projects").status_code == 401
    assert client.get("/api/levels/project/gbrowser").status_code == 401
    assert client.post("/api/levels/grade", json={"id": "abcdef12", "verdict": "agree"}).status_code == 401
    assert len(client.log.read_text().splitlines()) == 1


def test_projects_shape(client, project_export):
    r = authed(client).get("/api/levels/projects")
    assert r.status_code == 200, r.text
    assert r.json() == {"projects": project_export.compact}
    project_export.export.projects_view.assert_called_once_with(project_export.names)
    project_export.export.project_view.assert_not_called()
    assert_no_notes(r.json())


@pytest.mark.parametrize("pid", ["gbrowser", "g-site", "uncovered"])
def test_project_shape(client, project_export, pid):
    r = authed(client).get(f"/api/levels/project/{pid}")
    assert r.status_code == 200, r.text
    assert r.json() == {**project_export.views[pid], "id": pid}
    project_export.export.project_view.assert_called_once_with(project_export.names[pid])
    project_export.export.projects_view.assert_not_called()
    assert_no_notes(r.json())


@pytest.mark.parametrize("pid", ["unknown", "Gbrowser", "bad.id", "gbrowser%0A", "a" * 65])
def test_project_unknown_or_invalid_id_is_404(client, project_export, pid):
    r = authed(client).get(f"/api/levels/project/{pid}")
    assert r.status_code == 404
    project_export.export.project_view.assert_not_called()
    assert_no_notes(r.json())


@pytest.mark.parametrize("path", ["/projects", "/project/gbrowser"])
def test_project_routes_export_unavailable_is_503(client, project_export, monkeypatch, path):
    monkeypatch.setattr(levels_api, "_export", Mock(side_effect=HTTPException(503, "g-levels unavailable")))
    r = authed(client).get(f"/api/levels{path}")
    assert r.status_code == 503
    assert_no_notes(r.json())


@pytest.mark.parametrize("body", [{"id": "abcdef12", "verdict": "maybe"}, {"id": "../etc", "verdict": "agree"},
                                  {"id": "abcdef12; rm", "verdict": "agree"}, {"id": "abcdef12\n", "verdict": "agree"}])
def test_grade_rejects_bad_input(client, body):
    assert authed(client).post("/api/levels/grade", json=body).status_code == 400


@pytest.mark.skipif(not levels_api._dir().is_dir(), reason="no g-levels checkout beside this one")
def test_grade_writes_one_row_through_the_cli(client):
    r = authed(client).post("/api/levels/grade", json={"id": "abcdef12", "verdict": "disagree", "note": "-v too loud"})
    assert r.status_code == 200, r.text
    rows = [json.loads(line) for line in client.log.read_text().splitlines()]
    assert len(rows) == 2
    g = rows[-1]
    assert g["result"] == "grade" and g["by"] == "gabriel" and g["gate"] == ROW["gate"]
    assert g["note"] == "disagree abcdef12 -v too loud"


@pytest.mark.skipif(not levels_api._dir().is_dir(), reason="no g-levels checkout beside this one")
def test_grade_unknown_id_is_404(client):
    assert authed(client).post("/api/levels/grade", json={"id": "00000000", "verdict": "agree"}).status_code == 404
