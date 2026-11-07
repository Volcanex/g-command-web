"""Jobs reads stay gated, read-only, and confine downloads to the archive."""
import json
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.jobs import api as jobs_api


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    app = FastAPI()
    app.include_router(jobs_api.router, prefix="/api/jobs")
    return TestClient(app)


def test_unauthenticated_reads_never_reach_jobs(client, monkeypatch):
    def unexpected(*args):
        pytest.fail("unauthenticated access reached the archive")
    monkeypatch.setattr(jobs_api, "_read", unexpected)
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs/cv/record.pdf").status_code == 401


def test_only_existing_views_can_be_read(client, monkeypatch):
    client.cookies.set("seed_admin", "ok")
    monkeypatch.setattr(jobs_api, "_read", lambda view: {"items": [{"view": view}]})
    for view in ("roster", "applications", "letters", "questions", "runs"):
        assert client.get("/api/jobs", params={"view": view}).json()["items"] == [{"view": view}]
    assert client.get("/api/jobs?view=apply").status_code == 400
    assert client.post("/api/jobs", json={}).status_code == 405


def test_reader_failure_is_retryable_without_exposing_records(client, monkeypatch):
    client.cookies.set("seed_admin", "ok")
    def broken(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "reader", stderr="private archive content")
    monkeypatch.setattr(jobs_api.subprocess, "run", broken)
    response = client.get("/api/jobs")
    assert response.status_code == 502
    assert "Try again" in response.text
    assert "private" not in response.text


def test_cv_requires_an_archived_file_inside_variants(client, monkeypatch, tmp_path):
    client.cookies.set("seed_admin", "ok")
    monkeypatch.setattr(jobs_api, "_root", lambda: tmp_path)
    archive = tmp_path / "out/variants"
    archive.mkdir(parents=True)
    pdf = archive / "record.pdf"
    pdf.write_bytes(b"%PDF-1.4 archived")
    monkeypatch.setattr(jobs_api, "_read", lambda *args: str(pdf))
    response = client.get("/api/jobs/cv/record.pdf")
    assert response.status_code == 200
    assert response.content == pdf.read_bytes()
    monkeypatch.setattr(jobs_api, "_read", lambda *args: None)
    assert client.get("/api/jobs/cv/missing.pdf").status_code == 404
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"private")
    monkeypatch.setattr(jobs_api, "_read", lambda *args: str(outside))
    assert client.get("/api/jobs/cv/record.pdf").status_code == 404


def test_reader_uses_existing_project_code_without_a_shell(monkeypatch, tmp_path):
    monkeypatch.setenv("GJOBS_DIR", str(tmp_path))
    def reader(args, **kwargs):
        assert args[0] == "/usr/bin/python3"
        assert "from gjobs.site import data as D" in args[2]
        assert kwargs["cwd"] == tmp_path
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(args, 0, json.dumps({"items": []}))
    monkeypatch.setattr(jobs_api.subprocess, "run", reader)
    assert jobs_api._read("roster") == {"items": []}
