import json

import pytest
from fastapi import FastAPI
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


def test_every_route_requires_cookie(client):
    assert client.get("/api/levels/snapshot").status_code == 401
    assert client.get("/api/levels/sample").status_code == 401
    assert client.post("/api/levels/grade", json={"id": "abcdef12", "verdict": "agree"}).status_code == 401
    assert len(client.log.read_text().splitlines()) == 1


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
