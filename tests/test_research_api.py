import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.research import api as research_api

PAGES = Path(__file__).resolve().parent.parent / "pages"

PAPER = """# A paper

Intro.

## 1. First

Text with **bold**.

## 12. Main claims, by status

**Established:** the registry had seven gates and two charters. Guidance and sensor are a pair.

**Conjecture:** something else.

## Sources

1. A source.
"""


@pytest.fixture
def roots(tmp_path, monkeypatch):
    research = tmp_path / "g-research"
    (research / "pieces").mkdir(parents=True)
    (research / "pieces" / "making-ladder.md").write_text(PAPER)
    ans = tmp_path / "ans"
    for d in ("thesis/drafts", "lit/notes", "runs/r1", "atlas/data"):
        (ans / d).mkdir(parents=True)
    (ans / "thesis" / "drafts" / "one.md").write_text("# Draft one\n\n## Part\n\nBody.\n")
    (ans / "lit" / "notes" / "note.md").write_text("# Note\n\nRead.\n")
    (ans / "lit" / "refs.bib").write_text("@article{a,\n}\n@book{b,\n}\n")
    (ans / "runs" / "r1" / "x.traj.json").write_text('{"prompt": "secret"}')
    monkeypatch.setenv("RESEARCH_G_RESEARCH_DIR", str(research))
    monkeypatch.setenv("RESEARCH_ANS_DIR", str(ans))
    return research, ans


@pytest.fixture
def client(roots, monkeypatch):
    app = FastAPI()
    app.include_router(research_api.router, prefix="/api/research")
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    c = TestClient(app)
    c.cookies.set("seed_admin", "ok")
    return c


def test_every_route_needs_the_gate(roots, monkeypatch):
    app = FastAPI()
    app.include_router(research_api.router, prefix="/api/research")
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    c = TestClient(app)
    for url in ("/api/research", "/api/research/ans/runs", "/api/research/dissertation/charts",
                "/api/research/dissertation/file?path=a.png"):
        assert c.get(url).status_code == 401, url


def test_registry_and_rail_pages_match():
    areas = research_api.registry()
    for area in areas:
        cfg = json.loads((PAGES / f"research-{area['id']}" / "config.json").read_text())
        assert cfg["slug"] == f"research/{area['id']}"
        assert cfg["tabs"] == "research" and cfg["nav"] is False
        assert f'mountArea("{area["id"]}")' in (PAGES / f"research-{area['id']}" / "app.js").read_text()
        assert {v["kind"] for v in area["views"]} <= set(research_api.KINDS)
    dirs = {p.name[len("research-"):] for p in PAGES.glob("research-*") if p.is_dir()}
    assert dirs == {a["id"] for a in areas}
    icons = [json.loads((PAGES / f"research-{a['id']}" / "config.json").read_text())["nav_icon"] for a in areas]
    assert len(set(icons)) == len(icons)


def test_paper_and_docs(client):
    paper = client.get("/api/research/making-ladder/paper").json()
    assert "Main claims" in paper["markdown"] and paper["title"] == "A paper"
    thesis = client.get("/api/research/ans/thesis").json()
    assert [d["id"] for d in thesis["docs"]] == ["thesis/drafts/one.md"]
    assert thesis["doc"]["title"] == "Draft one"
    lit = client.get("/api/research/ans/literature").json()
    assert lit["bib"]["entries"] == 2


def test_claims_split_by_status(client):
    data = client.get("/api/research/making-ladder/claims").json()
    statuses = [c["status"] for c in data["claims"]]
    assert statuses == ["Established", "Established", "Conjecture"]
    if data.get("live"):
        registry = next(c for c in data["claims"] if "seven gates" in c["text"])
        assert registry["evidence"], "the registry claim links to live evidence"


def test_ans_runs_are_aggregates(client, roots):
    _, ans = roots
    assert client.get("/api/research/ans/runs").json()["missing"] is True
    db = sqlite3.connect(ans / "runs" / "ans.sqlite")
    db.executescript("""
        CREATE TABLE configs (config_id TEXT, config_json TEXT);
        CREATE TABLE runs (run_id TEXT, config_id TEXT, suite TEXT, status TEXT, n_items INTEGER, seed INTEGER,
                           started_at TEXT, finished_at TEXT);
        CREATE TABLE items (run_id TEXT, item_id TEXT, passed INTEGER, prompt TEXT);
        CREATE TABLE run_metrics (run_id TEXT, gen_tps REAL, peak_rss_mb REAL, load_s REAL);
        CREATE TABLE sweeps (sweep_id TEXT, status TEXT, started_at TEXT, finished_at TEXT);
        CREATE TABLE sweep_runs (sweep_id TEXT, run_id TEXT);
        INSERT INTO configs VALUES ('c1', '{"model": "m", "harness": "direct"}');
        INSERT INTO runs VALUES ('r1', 'c1', 'suite', 'completed', 3, 0, '2026-10-17T10:00:00', NULL);
        INSERT INTO items VALUES ('r1', 'a', 1, 'secret prompt'), ('r1', 'b', 0, 'secret prompt'), ('r1', 'c', 1, 'secret');
        INSERT INTO run_metrics VALUES ('r1', 40.5, 600, 1.0);
        INSERT INTO sweeps VALUES ('s1', 'completed', '2026-10-17T09:00:00', NULL);
        INSERT INTO sweep_runs VALUES ('s1', 'r1');
    """)
    db.commit()
    db.close()
    r = client.get("/api/research/ans/runs")
    run = r.json()["runs"][0]
    assert (run["model"], run["harness"], run["done"], run["passed"]) == ("m", "direct", 3, 2)
    assert r.json()["sweeps"][0]["runs"] == 1
    assert "secret" not in r.text


def test_dissertation_degrades_when_empty(client, roots):
    research, _ = roots
    for vid in ("results", "chapters", "tables", "charts"):
        data = client.get(f"/api/research/dissertation/{vid}").json()
        assert data["missing"] is True, vid
    (research / "dissertation" / "data").mkdir(parents=True)
    (research / "dissertation" / "data" / "raw.md").write_text("# raw prompts")
    (research / "dissertation" / "prompt-log.md").write_text("# prompts")
    (research / "dissertation" / "ch1.md").write_text("# Chapter one\n")
    (research / "dissertation" / "fig.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (research / "dissertation" / "data" / "fig2.svg").write_text("<svg/>")
    chapters = client.get("/api/research/dissertation/chapters").json()
    assert [d["id"] for d in chapters["docs"]] == ["ch1.md"]
    charts = client.get("/api/research/dissertation/charts").json()
    assert [c["id"] for c in charts["charts"]] == ["fig.svg"]
    assert client.get("/api/research/dissertation/file?path=fig.svg").status_code == 200
    for bad in ("data/fig2.svg", "../pieces/making-ladder.md", "ch1.md", "/etc/passwd"):
        assert client.get("/api/research/dissertation/file", params={"path": bad}).status_code == 404, bad


def test_safe_refuses_outside_hidden_excluded_and_denied(roots):
    area = next(a for a in research_api.registry() if a["id"] == "dissertation")
    research, _ = roots
    (research / "dissertation").mkdir()
    for rel in ("../pieces/making-ladder.md", ".git/config", "data/x.md", "my-prompts.md", "/etc/passwd"):
        assert research_api._safe(area, rel) is None, rel
    assert research_api._safe(area, "results.md") is not None


def test_unknown_area_and_view(client):
    assert client.get("/api/research/nope/paper").status_code == 404
    assert client.get("/api/research/ans/nope").status_code == 404


# ---------------------------------------------------------------- judge

@pytest.fixture
def judge(tmp_path, monkeypatch):
    data = tmp_path / "g-research-data"
    jd = data / "runs" / "p1" / "judge"
    (jd / "pages").mkdir(parents=True)
    (jd / "pages" / "abc123.html").write_text("<p>page a</p>")
    (jd / "pages" / "def456.html").write_text("<p>page b</p>")
    (data / "runs" / "p1" / "judge-key.json").write_text('{"abc123.html": "arm-secret"}')
    (data / "runs" / "secret.html").write_text("outside")
    (jd / "pairs.json").write_text(json.dumps({
        "run": "p1", "title": "Probe one", "question": "Which would you keep?",
        "reasons": ["clearer", "more character"],
        "pairs": [{"id": "p01", "brief": "A meal planner", "a": "abc123.html", "b": "def456.html"},
                  {"id": "p02", "brief": "A meal planner", "a": "def456.html", "b": "abc123.html"}]}))
    monkeypatch.setenv("RESEARCH_G_RESEARCH_DATA_DIR", str(data))
    return jd


def test_judge_lists_sets_and_hides_the_key(client, judge):
    r = client.get("/api/research/thesis/judge").json()
    assert r["sets"] == [{"run": "p1", "title": "Probe one", "pairs": 2, "judged": 0}]
    s = r["set"]
    assert s["question"] == "Which would you keep?" and s["reasons"] == ["clearer", "more character"]
    assert [p["id"] for p in s["pairs"]] == ["p01", "p02"]
    assert s["pairs"][0]["a"] == "/api/research/thesis/judge/p1/page/abc123.html"
    assert "arm-secret" not in json.dumps(r) and "judge-key" not in json.dumps(r)


def test_judge_page_route(client, judge):
    r = client.get("/api/research/thesis/judge/p1/page/abc123.html")
    assert r.status_code == 200 and "page a" in r.text
    assert r.headers["content-security-policy"] == "sandbox allow-scripts allow-forms allow-modals"
    assert r.headers["x-content-type-options"] == "nosniff"
    for bad in ("..%2F..%2Fsecret.html", "..%2Fjudge-key.json", "ABC123.html", "abc.html", "abc123.htm",
                "abc123.html%00", "nothere99.html"):
        assert client.get(f"/api/research/thesis/judge/p1/page/{bad}").status_code == 404, bad
    assert client.get("/api/research/thesis/judge/..%2F..%2Fruns/page/abc123.html").status_code == 404
    assert client.get("/api/research/thesis/judge/nope/page/abc123.html").status_code == 404


def test_judge_vote_route(client, judge):
    url = "/api/research/thesis/judge/p1/vote"
    assert client.post(url, json={"pair": "p01", "choice": "a", "reasons": ["clearer"], "seconds": 12.34}).status_code == 200
    line = json.loads((judge / "votes.jsonl").read_text().splitlines()[0])
    assert line["pair"] == "p01" and line["choice"] == "a" and line["reasons"] == ["clearer"]
    assert line["seconds"] == 12.3 and line["at"].endswith("+00:00")
    assert client.post(url, json={"pair": "zz", "choice": "a"}).status_code == 404
    assert client.post(url, json={"pair": "p01", "choice": "c"}).status_code == 400
    assert client.post(url, json={"pair": "p01", "choice": "b", "reasons": ["made up"]}).status_code == 400
    assert len((judge / "votes.jsonl").read_text().splitlines()) == 1
    client.post(url, json={"pair": "p01", "choice": "neither", "reasons": [], "seconds": 3})
    r = client.get("/api/research/thesis/judge").json()
    assert r["set"]["votes"] == {"p01": {"choice": "neither", "reasons": []}}
    assert r["sets"][0]["judged"] == 1


def test_judge_routes_need_the_gate(judge, roots, monkeypatch):
    app = FastAPI()
    app.include_router(research_api.router, prefix="/api/research")
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    c = TestClient(app)
    assert c.get("/api/research/thesis/judge/p1/page/abc123.html").status_code == 401
    assert c.post("/api/research/thesis/judge/p1/vote", json={"pair": "p01", "choice": "a"}).status_code == 401
    assert not (judge / "votes.jsonl").exists()
