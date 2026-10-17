"""hours API, mounted at /api/hours.

Pure proxy. The Hours page is an **activity tracker**: it shows where the week
went. A separate time-tracking service computes the session snapshot, and this
route fetches it over localhost from `WAGES_URL`.

`TRACKER_FIELDS` is the boundary: only these keys are forwarded, so anything
else the service keeps never reaches g-command-web. Widen it only for activity
data, and add a route to the service for anything else.

Admin-gated inline: the page gate in server.py does not cover /api/*.
"""
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request

from core.auth import cookie_ok

router = APIRouter()

WAGES_URL = os.environ.get("WAGES_URL", "http://127.0.0.1:8093")

# Activity only: everything else in the snapshot stays in the service.
TRACKER_FIELDS = (
    "week_start", "days", "projects", "presence", "presence_total",
    "agent_total", "turns_total", "tokens", "ctx_total", "models",
    "blocks", "errors", "generated_at",
)


@router.get("/week")
def week(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    url = f"{WAGES_URL}/api/ledger/sessions/week"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            snap = json.loads(r.read().decode("utf-8"))
        return {k: snap[k] for k in TRACKER_FIELDS if k in snap}
    except urllib.error.HTTPError as exc:
        # 503 from the service means it has not produced a snapshot yet;
        # forward that meaning rather than flattening it to a generic failure.
        raise HTTPException(exc.code if exc.code in (503, 404) else 502, f"time tracker: {exc.reason}")
    except Exception as exc:
        raise HTTPException(503, f"time tracker unreachable: {type(exc).__name__}")
