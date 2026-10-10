"""g-admin tickets panel: cross-project aggregation, mounted at
`/api/gadmin_panel`.

Every project that speaks the g-admin contract
(`agents/g-admin-contract.md` in the g-design repo) holds its own
tickets; this router does not. It proxies list/get/brief/patch-status
calls to each project's `/api/gadmin` using the machine token
(`X-Gadmin-Token`, `GADMIN_TOKEN` env var from the instance passport) so the
browser never holds it, the same "live reads, no local store" pattern as
`/system`'s service health.

Roster discovery: group the instance `manifest.json` services by `repo`, then
probe each project's `{base}/api/gadmin/tickets?status=open` with the
token. A 200 means "speaks the contract": `/api/gadmin/verify` is
deliberately cookie-only (see the reference server in
`core/api/gadmin.py`), so it can't be used to detect a machine-only
reader. The roster is cached in-process for `ROSTER_TTL_S` and rebuilt
lazily the next time it's read past that age (never on every render).

Every downstream call has a short timeout: one dead project degrades
that project to an empty/labelled result, never a failure for the whole
panel. Same rule for aggregation as for a single project lookup: a
proxy 502 only happens when the caller asked for that one project by
name and it didn't answer.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from core.instance import gcore_dir

router = APIRouter()

REQUEST_TIMEOUT_S = 3
ROSTER_TTL_S = 600
POOL_WORKERS = 8

_roster_cache: dict = {"built_at": 0.0, "roster": {}}


# Every env var below is read at call time, not at import time, so a
# systemd restart (or a test monkeypatching os.environ) always sees the
# current value, and nothing here has to be reloaded to pick up a change.


def _gate(request: Request) -> None:
    cookie = os.environ.get("ADMIN_COOKIE", "seed_admin")
    value = os.environ.get("ADMIN_COOKIE_VALUE")
    if not value or request.cookies.get(cookie) != value:
        raise HTTPException(401, "unauthorized")


def _token() -> str | None:
    return os.environ.get("GADMIN_TOKEN") or None


def _manifest_path() -> Path:
    return gcore_dir() / "manifest.json"


def _load_manifest() -> dict:
    try:
        return json.loads(_manifest_path().read_text())
    except Exception:
        return {}


def _candidate_bases() -> dict[str, list[str]]:
    """Project id -> ordered base URLs to try. Public domain first (best
    fidelity through nginx/TLS), internal port second, the same fallback
    order as scripts/refresh_projects.py, which bypasses nginx basic-auth
    since both this job and that one run on-host."""
    manifest = _load_manifest()
    by_repo: dict[str, list[dict]] = {}
    for s in manifest.get("services", []):
        repo = s.get("repo")
        if repo:
            by_repo.setdefault(repo, []).append(s)
    out: dict[str, list[str]] = {}
    for repo, svcs in by_repo.items():
        bases = []
        domain = next((s.get("domain") for s in svcs if s.get("domain")), None)
        port = next((s.get("port") for s in svcs if s.get("port")), None)
        if domain:
            bases.append(f"https://{domain}")
        if port:
            bases.append(f"http://127.0.0.1:{port}")
        if bases:
            out[repo] = bases
    return out


def _http(method: str, url: str, *, params: dict | None = None, body: dict | None = None):
    """One request, token attached. Returns (status, payload, error) and
    never raises: every caller treats a network failure the same as a
    project that spoke false: "down right now", not an exception to
    propagate to the whole page."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    token = _token()
    if token:
        headers["X-Gadmin-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            payload = json.loads(raw) if "json" in ctype else raw.decode("utf-8", "replace")
            return resp.status, payload, None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw.decode("utf-8", "replace") if raw else None
        return e.code, payload, None
    except Exception as e:
        return None, None, str(e)


def _probe(base: str) -> bool:
    # A 200 alone isn't enough: a project without a real /api/gadmin route
    # can still 200 here off a catch-all SPA route that serves index.html
    # for any unmatched path (seen live against gdesign). Require the
    # actual ticket-list shape, the same check list_tickets uses per call.
    status, data, _ = _http("GET", f"{base}/api/gadmin/tickets", params={"status": "open"})
    return status == 200 and isinstance(data, dict) and isinstance(data.get("tickets"), list)


def _build_roster() -> dict[str, str]:
    candidates = _candidate_bases()
    roster: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=POOL_WORKERS) as pool:
        futures = {}
        for pid, bases in candidates.items():
            for base in bases:
                futures[pool.submit(_probe, base)] = (pid, base)
        for fut, (pid, base) in futures.items():
            if pid in roster:
                continue
            try:
                if fut.result():
                    roster[pid] = base
            except Exception:
                continue
    return roster


def _get_roster() -> dict[str, str]:
    now = time.time()
    if now - _roster_cache["built_at"] > ROSTER_TTL_S:
        _roster_cache["roster"] = _build_roster()
        _roster_cache["built_at"] = now
    return _roster_cache["roster"]


@router.get("/tickets")
def list_tickets(
    request: Request,
    status: Literal["open", "baked", "dismissed"] | None = Query(None),
    project: str | None = Query(None),
    severity: str | None = Query(None),
):
    _gate(request)
    roster = _get_roster()
    if project and project not in roster:
        raise HTTPException(404, f"{project} does not speak the g-admin contract")
    targets = {project: roster[project]} if project else roster

    tickets: list[dict] = []
    degraded: list[str] = []

    def fetch(item):
        pid, base = item
        params = {"status": status} if status else None
        code, data, err = _http("GET", f"{base}/api/gadmin/tickets", params=params)
        return pid, code, data, err

    if targets:
        with ThreadPoolExecutor(max_workers=POOL_WORKERS) as pool:
            for pid, code, data, err in pool.map(fetch, targets.items()):
                if code == 200 and isinstance(data, dict) and isinstance(data.get("tickets"), list):
                    for t in data["tickets"]:
                        t = dict(t)
                        t["project"] = pid
                        tickets.append(t)
                else:
                    degraded.append(pid)

    if severity:
        tickets = [t for t in tickets if t.get("severity") == severity]

    tickets.sort(key=lambda t: t.get("updated_at") or t.get("created_at") or "", reverse=True)

    return {
        "tickets": tickets,
        "projects": sorted(roster.keys()),
        "degraded": sorted(degraded),
        "roster_age_s": round(time.time() - _roster_cache["built_at"]),
    }


@router.get("/tickets/{project}/{ticket_id}")
def get_ticket(project: str, ticket_id: str, request: Request):
    _gate(request)
    base = _get_roster().get(project)
    if not base:
        raise HTTPException(404, f"{project} does not speak the g-admin contract")
    code, data, err = _http("GET", f"{base}/api/gadmin/tickets/{urllib.parse.quote(ticket_id)}")
    if code == 200:
        return data
    if err:
        raise HTTPException(502, f"{project} unreachable: {err}")
    raise HTTPException(code or 502, data if isinstance(data, (str, dict)) else "upstream error")


@router.get("/tickets/{project}/{ticket_id}/brief")
def get_brief(project: str, ticket_id: str, request: Request):
    _gate(request)
    base = _get_roster().get(project)
    if not base:
        raise HTTPException(404, f"{project} does not speak the g-admin contract")
    code, data, err = _http("GET", f"{base}/api/gadmin/tickets/{urllib.parse.quote(ticket_id)}/brief")
    if code == 200:
        text = data if isinstance(data, str) else json.dumps(data)
        return Response(content=text, media_type="text/markdown")
    if err:
        raise HTTPException(502, f"{project} unreachable: {err}")
    raise HTTPException(code or 502, "upstream error")


class TicketPatchBody(BaseModel):
    status: Literal["open", "baked", "dismissed"] | None = None
    reply: str | None = None


@router.patch("/tickets/{project}/{ticket_id}")
def patch_ticket(project: str, ticket_id: str, body: TicketPatchBody, request: Request):
    _gate(request)
    base = _get_roster().get(project)
    if not base:
        raise HTTPException(404, f"{project} does not speak the g-admin contract")
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(400, "nothing to update")
    code, data, err = _http(
        "PATCH", f"{base}/api/gadmin/tickets/{urllib.parse.quote(ticket_id)}", body=payload
    )
    if code is not None and 200 <= code < 300:
        return data
    if err:
        raise HTTPException(502, f"{project} unreachable: {err}")
    raise HTTPException(code or 502, data if isinstance(data, (str, dict)) else "upstream error")
