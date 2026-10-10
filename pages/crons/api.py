"""crons page API, mounted at /api/crons.

Serves the g-cron cache and the pulse model-job history, nothing else. Discovery
(ssh to every host, systemctl, crontabs) is never run from the request path:
`g-cron.timer` runs `g-cron --record` every 15 minutes and this route only reads
what it wrote, so an unreachable host cannot stall the page. Cache age is derived
at read time, so a stopped timer shows up as a stale snapshot with its age.

Admin-gated inline, the page gate in server.py does not cover /api/*.
"""
import json
import os
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from core.auth import ADMIN_COOKIE, ADMIN_VALUE
from core.instance import sibling

router = APIRouter()

STALE_AFTER = 45 * 60
RUNS_PER_JOB = 10


def _cache_path():
    return Path(os.environ.get("CRONS_CACHE") or Path.home() / ".cache/genv/g-cron.json")


def _runs_path():
    if os.environ.get("CRONS_RUNS"):
        return Path(os.environ["CRONS_RUNS"])
    brain = Path(os.environ.get("BRAIN_ROOT") or sibling("brain"))
    return brain / ".pulse/state/cron-runs.jsonl"


def _runs():
    by = defaultdict(list)
    try:
        lines = _runs_path().read_text().splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("name"):
            by[r["name"]].append(r)
    return {n: sorted(v, key=lambda r: r.get("started") or "", reverse=True)[:RUNS_PER_JOB]
            for n, v in by.items()}


@router.get("/list")
def listing(request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")
    try:
        data = json.loads(_cache_path().read_text())
    except (OSError, ValueError):
        raise HTTPException(503, "no cron snapshot yet, g-cron.timer has not run")
    age = max(0, int(time.time() - (data.get("generated_at") or 0)))
    data["jobs"] = [j for j in data.get("jobs", []) if not j.get("noise") or j.get("kind") == "pulse"]
    data["age_seconds"] = age
    data["stale"] = age > STALE_AFTER
    data["stale_after_seconds"] = STALE_AFTER
    data["runs"] = _runs()
    return data
