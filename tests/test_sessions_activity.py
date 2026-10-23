"""Agent activity: read-only snapshot for Voice, opened by a short grant."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.sessions import api


def test_grant_round_trip_expiry_and_tamper():
    g = api.activity_grant(now=1000)
    assert api.grant_ok(g, now=1000) and api.grant_ok(g, now=1000 + api.GRANT_TTL - 1)
    assert not api.grant_ok(g, now=1000 + api.GRANT_TTL + 1)
    exp, sig = g.split(".")
    assert not api.grant_ok(f"{int(exp) + 999}.{sig}", now=1000)
    assert not api.grant_ok("", now=1000) and not api.grant_ok("abc", now=1000)


def test_script_only_reads():
    script = api._activity_script("work-1", 10)
    assert "send-keys" not in script and "paste-buffer" not in script and "new-session" not in script
    assert "capture-pane -p -J" in script and "-S -40" in script and "grep -Fx -- work-1" in script


def test_parse_activity():
    out = "\n".join([
        "@@panes",
        "work\t11\tclaude\tFix login bug\t1000",
        "work\t01\tbash\tother\t1000",
        "idle\t11\tbash\th\t500",
        "@@pane work", "line 1", "line 2", "", "",
        "@@pane idle",
        "@@claude", "1100.5\t/home/gabriel/.claude/projects/-home-gabriel-gcommand",
    ])
    got = api._parse_activity(out, now=1200, lines=1)
    work = got["sessions"][0]
    assert work == {"name": "work", "command": "claude", "title": "Fix login bug", "idle_s": 200, "tail": ["line 2"]}
    assert got["sessions"][1]["tail"] == []
    assert got["claude_code"] == [{"project": "-home-gabriel-gcommand", "idle_s": 99}]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "activity", lambda host, session, lines: {"read_only": True, "args": [host, session, lines]})
    app = FastAPI()
    app.include_router(api.router, prefix="/api/sessions")
    return TestClient(app)


def test_route_needs_cookie_or_grant(client):
    assert client.get("/api/sessions/activity").status_code == 401
    assert client.get("/api/sessions/activity", headers={"X-Voice-Grant": "1.bad"}).status_code == 401
    r = client.get("/api/sessions/activity?lines=5", headers={"X-Voice-Grant": api.activity_grant()})
    assert r.status_code == 200 and r.json()["args"] == [None, None, 5]
    g = {"X-Voice-Grant": api.activity_grant()}
    assert client.get("/api/sessions/activity?host=nope", headers=g).status_code == 400
    assert client.get("/api/sessions/activity?session=a;rm", headers=g).status_code == 400


def test_grant_opens_nothing_else(client):
    g = {"X-Voice-Grant": api.activity_grant()}
    assert client.get("/api/sessions", headers=g).status_code == 401
    assert client.post("/api/sessions/new", json={"host": "local", "name": "x"}, headers=g).status_code == 401
