"""Writing voice page API, mounted at /api/ganti.

Reads the g-anti-ai checkout beside this one (core.instance.sibling, GANTI_DIR to
override). Everything here is a renderer over what ganti already computes:

- `snapshot()` prefers `ganti.dash.snapshot()` in-process, then `ganti dash --json`
  as a subprocess, then the bare style card with an honest "no score log yet" flag.
- `score` runs `ganti score - --json --no-log` with the text on stdin, falling back to
  the pure `ganti.score.score()` call when the installed ganti predates `--no-log`.
  Pasted text is never written anywhere, never put on argv and never logged here.
- The corpus is private diaries. Only source names, registers and word counts leave this
  module, and there is no route that returns corpus text.

Auth is checked inline, the page gate in server.py does not cover /api/*.
"""
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import cookie_ok
from core.instance import sibling

router = APIRouter()

MAX_TEXT = 60_000
DEFAULT_LOW = 15
SUBPROCESS_TIMEOUT = 30
_RUNNER = "import sys\nfrom ganti.cli import main\nsys.exit(main(sys.argv[1:]))"


def _dir():
    return Path(os.environ.get("GANTI_DIR") or sibling("g-anti-ai"))


def _auth(request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _ganti(name):
    """Import ganti (or a submodule) from the sibling checkout; None when it is not there."""
    path = str(_dir())
    if path not in sys.path:
        sys.path.insert(0, path)
    importlib.invalidate_caches()
    try:
        return importlib.import_module(name)
    except (ImportError, SyntaxError):
        return None


def _run(args, stdin=None):
    """Run the ganti CLI from the sibling checkout. Returns (returncode, stdout) or None."""
    env = {**os.environ, "PYTHONPATH": str(_dir())}
    try:
        done = subprocess.run([sys.executable, "-c", _RUNNER, *args], input=stdin,
                              capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT,
                              env=env, cwd=str(_dir()))
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode, done.stdout


def _json(raw):
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _card_file():
    return _json((_dir() / "data/style-card.json").read_text()) if (_dir() / "data/style-card.json").is_file() else None


def _from_card(card):
    """The degraded snapshot: card sections only, derived frequencies, no log and no thresholds."""
    words = (card.get("overall") or {}).get("words") or 0
    top = ((card.get("vocabulary") or {}).get("top")) or {}
    per10k = lambda n: round(n / words * 10000, 2) if words else 0
    ranked = sorted(top.items(), key=lambda kv: -kv[1])
    rules = _ganti("ganti.rules")
    ai = sorted(set().union(*(getattr(rules, t, set()) for t in ("TIER1", "TIER2", "TIER3")))) if rules else []
    ai_words = [[w, per10k(top.get(w, 0)), top.get(w, 0) == 0] for w in ai]
    ai_words.sort(key=lambda r: (-r[1], r[0]))
    return {"card": {"version": card.get("card_version"), "sources": card.get("sources") or [],
                     "overall": card.get("overall") or {}, "by_register": card.get("by_register") or {}},
            "thresholds": None,
            "freq": {"top": [[w, per10k(n)] for w, n in ranked[:200]], "ai_words": ai_words},
            "absolutes": [], "recent": [], "source": "card"}


def snapshot():
    mod = _ganti("ganti.dash")
    if mod is not None and hasattr(mod, "snapshot"):
        try:
            data = mod.snapshot()
            if isinstance(data, dict):
                return {**data, "source": "dash"}
        except Exception:  # noqa: BLE001 - a half-built dash must fall through, not 500 the page
            pass
    ran = _run(["dash", "--json"])
    data = _json(ran[1]) if ran and ran[0] == 0 else None
    if data:
        return {**data, "source": "cli"}
    card = _card_file()
    if card:
        return _from_card(card)
    return None


def _clean_snapshot(snap):
    """Whitelist what leaves the box: names, registers and counts, never any corpus text."""
    card = snap.get("card") or {}
    sources = [{"name": re.sub(r"\d{6,}", "", str(s.get("name", ""))), "register": str(s.get("register", "")),
                "words": int(s.get("words") or 0)} for s in card.get("sources") or []]
    recent = [{k: r.get(k) for k in ("ts", "words", "loudness", "absolutes", "tiers", "verdict", "label", "source", "sha")}
              for r in snap.get("recent") or [] if isinstance(r, dict)]
    freq = snap.get("freq") or {}
    return {"source": snap.get("source"),
            "card": {"version": card.get("version"), "sources": sources,
                     "overall": card.get("overall") or {}, "by_register": card.get("by_register") or {}},
            "thresholds": snap.get("thresholds"),
            "freq": {"top": freq.get("top") or [], "ai_words": freq.get("ai_words") or []},
            "absolutes": snap.get("absolutes") or [],
            "recent": recent}


@router.get("/snapshot")
def get_snapshot(request: Request):
    _auth(request)
    snap = snapshot()
    if snap is None:
        raise HTTPException(503, "g-anti-ai is not installed on this host")
    return _clean_snapshot(snap)


class ScoreIn(BaseModel):
    text: str


def _score_pure(text):
    """Score in-process without touching any log, for a ganti that has no --no-log yet."""
    scoring = _ganti("ganti.score")
    if scoring is None:
        return None
    path = _dir() / "data/target-application.json"
    if not path.is_file():
        return None
    return scoring.score(text, json.loads(path.read_text()))


@router.post("/score")
def score(body: ScoreIn, request: Request):
    _auth(request)
    text = body.text
    if not text.strip():
        raise HTTPException(400, "paste some text to score")
    if len(text) > MAX_TEXT:
        raise HTTPException(413, f"text is over {MAX_TEXT:,} characters")
    ran = _run(["score", "-", "--json", "--no-log"], stdin=text)
    result = _json(ran[1]) if ran and ran[0] in (0, 2) else None
    if result is None:
        result = _score_pure(text)
    if result is None:
        raise HTTPException(503, "g-anti-ai could not score the text on this host")
    result["findings"] = sorted(result.get("findings") or [], key=lambda f: -(f.get("loudness") or 0))
    return result
