import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.crons import api as crons_api  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(crons_api.router, prefix="/api/crons")
    monkeypatch.setattr(crons_api, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(crons_api, "ADMIN_VALUE", "ok")
    monkeypatch.setenv("CRONS_CACHE", str(tmp_path / "g-cron.json"))
    monkeypatch.setenv("CRONS_RUNS", str(tmp_path / "runs.jsonl"))
    return TestClient(app)


def test_requires_cookie(client):
    assert client.get("/api/crons/list").status_code == 401


def test_missing_cache_is_503(client):
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/crons/list").status_code == 503


def test_serves_jobs_runs_and_staleness(client, tmp_path):
    jobs = [{"kind": "timer", "name": "a", "noise": False}, {"kind": "timer", "name": "n", "noise": True},
            {"kind": "pulse", "name": "p", "noise": False}]
    (tmp_path / "g-cron.json").write_text(json.dumps(
        {"generated_at": time.time() - 3600, "hosts": [], "jobs": jobs, "problems": []}))
    (tmp_path / "runs.jsonl").write_text("\n".join(json.dumps(
        {"name": "p", "started": f"2026-10-0{i}T00:00:00+00:00", "result": "ok"}) for i in (1, 2)) + "\nnot json\n")
    client.cookies.set("seed_admin", "ok")
    body = client.get("/api/crons/list").json()
    assert [j["name"] for j in body["jobs"]] == ["a", "p"]
    assert body["stale"] is True and body["age_seconds"] >= 3600
    assert body["runs"]["p"][0]["started"].startswith("2026-10-02")
