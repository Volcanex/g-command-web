"""g-runner fleet proxy, mounted at /api/runners. Read only.

The /runners page renders g-runner's device fleet, queue and recent results.
g-runner wants its agent token on every read, so the browser asks here and
this router adds `Authorization: Bearer <token>` server-side. The token never
leaves this process: responses carry only the upstream JSON body, and errors
name the missing setting, never its value.

Env, read at call time like gadmin_panel.py:
  G_RUNNER_URL         upstream base, default http://127.0.0.1:8160
  G_RUNNER_TOKEN       the agent token, else the file below
  G_RUNNER_TOKEN_FILE  default /etc/g-runner/token

An unreachable or unconfigured upstream answers 200 with
`{"error": {"code", "message"}}`, so the page can say what happened rather
than show a failed fetch. No enqueue or cancel from here in this phase.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core.auth import cookie_ok

router = APIRouter(tags=["runners"])

REQUEST_TIMEOUT_S = 3
JOB_ID = re.compile(r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{6}$")


def _base() -> str:
    return (os.environ.get("G_RUNNER_URL") or "http://127.0.0.1:8160").rstrip("/")


def _token() -> str | None:
    tok = (os.environ.get("G_RUNNER_TOKEN") or "").strip()
    if tok:
        return tok
    path = Path(os.environ.get("G_RUNNER_TOKEN_FILE") or "/etc/g-runner/token")
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}, "upstream": _base()}


def _get(path: str) -> dict:
    token = _token()
    if not token:
        return _error(
            "no_token",
            "No g-runner token is set. Set G_RUNNER_TOKEN or put the token in "
            "G_RUNNER_TOKEN_FILE (default /etc/g-runner/token), then restart.",
        )
    req = urllib.request.Request(
        _base() + path,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        e.close()
        if e.code in (401, 403):
            return _error("rejected", f"g-runner refused the token ({e.code}). Check it matches RUNNER_TOKEN on g-runner.")
        if e.code == 404:
            return _error("not_found", "g-runner has no such record.")
        return _error("upstream", f"g-runner answered {e.code}.")
    except (urllib.error.URLError, TimeoutError, OSError):
        return _error("unreachable", "g-runner is not answering. The page tries again every 5 s.")
    except ValueError:
        return _error("bad_payload", "g-runner answered with something that is not JSON.")


def _gate(request: Request) -> None:
    # The site-wide page gate in server.py does not cover /api/*.
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


@router.get("/state")
async def state(request: Request):
    _gate(request)
    data = await run_in_threadpool(_get, "/api/state")
    if "error" not in data and not isinstance(data.get("devices"), list):
        return _error("bad_payload", "g-runner's state is missing its device list.")
    return data


@router.get("/jobs/{job_id}")
async def job(job_id: str, request: Request):
    _gate(request)
    if not JOB_ID.match(job_id):
        raise HTTPException(400, "bad job id")
    return await run_in_threadpool(_get, f"/api/jobs/{job_id}")
