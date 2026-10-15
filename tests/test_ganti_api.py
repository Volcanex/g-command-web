import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.ganti import api as ganti_api  # noqa: E402

CARD = {
    "card_version": 3,
    "sources": [{"name": "Diary_2_.txt", "register": "diary", "words": 600},
                {"name": "Report_22030670.txt", "register": "formal", "words": 400}],
    "overall": {"words": 1000, "sentence_lengths": {"mean": 11.8}},
    "by_register": {"diary": {"words": 600}, "formal": {"words": 400}},
    "vocabulary": {"top": {"the": 40, "and": 30, "robust": 2}},
    "SECRET_TEXT": "dear diary today I did a private thing",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    gdir = tmp_path / "g-anti-ai"
    (gdir / "data").mkdir(parents=True)
    (gdir / "data/style-card.json").write_text(json.dumps(CARD))
    monkeypatch.setenv("GANTI_DIR", str(gdir))
    # Keep the real checkout out of the in-process path so the card fallback is what runs.
    monkeypatch.setattr(ganti_api, "_ganti", lambda name: None)
    monkeypatch.setattr(ganti_api, "_run", lambda args, stdin=None: None)
    app = FastAPI()
    app.include_router(ganti_api.router, prefix="/api/ganti")
    monkeypatch.setattr(ganti_api, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(ganti_api, "ADMIN_VALUE", "ok")
    c = TestClient(app)
    return c


def authed(client):
    client.cookies.set("seed_admin", "ok")
    return client


def test_requires_cookie(client):
    assert client.get("/api/ganti/snapshot").status_code == 401
    assert client.post("/api/ganti/score", json={"text": "hello"}).status_code == 401


def test_card_fallback_is_honest_and_derives_frequencies(client):
    data = authed(client).get("/api/ganti/snapshot").json()
    assert data["source"] == "card"
    assert data["recent"] == [] and data["thresholds"] is None
    assert data["freq"]["top"][0] == ["the", 400.0]
    assert data["card"]["version"] == 3


def test_snapshot_never_carries_corpus_text(client):
    body = authed(client).get("/api/ganti/snapshot").text
    assert "dear diary" not in body and "SECRET_TEXT" not in body
    assert "22030670" not in body  # long digit runs in file names are masked


def test_missing_checkout_is_503(client, tmp_path, monkeypatch):
    monkeypatch.setenv("GANTI_DIR", str(tmp_path / "nowhere"))
    assert authed(client).get("/api/ganti/snapshot").status_code == 503


def test_dash_snapshot_is_preferred_and_whitelisted(client, monkeypatch):
    class Dash:
        @staticmethod
        def snapshot():
            return {"card": {"version": 4, "sources": [{"name": "a.txt", "register": "diary", "words": 5, "text": "leak"}],
                             "overall": {}, "by_register": {}},
                    "thresholds": {"low": 12}, "freq": {"top": [["x", 1.0]], "ai_words": [["robust", 2.0, False]]},
                    "absolutes": ["em_dash"], "recent": [{"ts": "2026-10-15T10:00:00Z", "words": 9, "loudness": 8,
                                                     "verdict": "low", "label": "t", "text": "leak"}]}
    monkeypatch.setattr(ganti_api, "_ganti", lambda name: Dash if name == "ganti.dash" else None)
    body = authed(client).get("/api/ganti/snapshot")
    assert "leak" not in body.text
    data = body.json()
    assert data["source"] == "dash" and data["thresholds"] == {"low": 12}
    assert data["recent"][0]["verdict"] == "low"


def test_cli_snapshot_when_no_module(client, monkeypatch):
    seen = []

    def run(args, stdin=None):
        seen.append(args)
        return 0, json.dumps({"card": {"sources": []}, "thresholds": {"low": 9}, "freq": {}, "recent": []})
    monkeypatch.setattr(ganti_api, "_run", run)
    data = authed(client).get("/api/ganti/snapshot").json()
    assert seen == [["dash", "--json"]] and data["source"] == "cli" and data["thresholds"]["low"] == 9


def test_score_passes_text_on_stdin_only_and_no_log(client, monkeypatch):
    seen = {}

    def run(args, stdin=None):
        seen.update(args=args, stdin=stdin)
        return 0, json.dumps({"loudness": 12, "findings": [{"loudness": 1, "tier": "vocabulary"},
                                                           {"loudness": 9, "tier": "generic"}],
                              "verdict": "ok", "absolutes_clear": True})
    monkeypatch.setattr(ganti_api, "_run", run)
    r = authed(client).post("/api/ganti/score", json={"text": "my secret draft"})
    assert r.status_code == 200
    assert seen["args"] == ["score", "-", "--json", "--no-log"]
    assert seen["stdin"] == "my secret draft" and "my secret draft" not in " ".join(seen["args"])
    assert [f["loudness"] for f in r.json()["findings"]] == [9, 1]


def test_score_falls_back_to_pure_call_when_cli_rejects_flag(client, monkeypatch):
    class Scoring:
        @staticmethod
        def score(text, target):
            return {"loudness": 3, "findings": [], "verdict": "close", "absolutes_clear": True}
    (ganti_api._dir() / "data/target-application.json").write_text("{}")
    monkeypatch.setattr(ganti_api, "_run", lambda args, stdin=None: (2, ""))
    monkeypatch.setattr(ganti_api, "_ganti", lambda name: Scoring if name == "ganti.score" else None)
    assert authed(client).post("/api/ganti/score", json={"text": "hi"}).json()["loudness"] == 3


def test_score_rejects_empty_and_huge_text(client):
    authed(client)
    assert client.post("/api/ganti/score", json={"text": "   "}).status_code == 400
    assert client.post("/api/ganti/score", json={"text": "a" * 60_001}).status_code == 413


def test_score_without_ganti_is_503(client):
    assert authed(client).post("/api/ganti/score", json={"text": "hello there"}).status_code == 503
