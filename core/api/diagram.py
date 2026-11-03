"""G-System diagram data, mounted at /api/diagram. Read only.

`GET /api/diagram` returns gcore's graph (`gcore_graph.graph()`, imported from the gcore checkout
the way pages/levels/api.py imports glevels.export) with its seams filled from live sources:

  health   every node, from the brain's L5 status snapshot (`/api/status`, what /system shows)
           and, for repos, the nerves map (`/api/nerves`, what /nerves shows). Read server-side
           from BRAIN_UPSTREAM, the same upstream core/api/brain.py proxies.
  clients  the project:g-studio node, from Studio's `GET /api/gadmin/blocks` with the
           `X-Gadmin-Token` this server already holds (GADMIN_TOKEN); it never reaches the browser.
  live     each declared http/sse/websocket connects edge: "down" when the target's service (or
           dependency) is down, "up" when all of them are up, else null.

Nothing here 500s on a dead source: a seam left null carries its reason in `sources`.
gcore's assembly walks every checkout (30 s cold, about 1 s warm), so it is cached for
GRAPH_TTL_S and refreshed in the background once stale; the live overlay for LIVE_TTL_S.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core.auth import cookie_ok
from core.instance import gcore_dir

router = APIRouter()
log = logging.getLogger(__name__)

GRAPH_TTL_S = 120
LIVE_TTL_S = 20
TIMEOUT_S = 5
LIVE_VIAS = ("http", "sse", "websocket")
RANK = {"down": 4, "warn": 3, "unknown": 2, "paused": 1, "up": 0}

_lock = threading.Lock()
_graph: dict = {"at": 0.0, "value": None, "error": None, "refreshing": False, "took_s": None}
_live: dict = {"at": 0.0, "value": None}


def _brain_upstream() -> str:
    return os.environ.get("BRAIN_UPSTREAM", "http://127.0.0.1:8766").rstrip("/")


def _studio_base() -> str | None:
    """Studio's raw port (nginx 404s /api/gadmin on the studio host): STUDIO_GADMIN_URL, else the
    manifest's g-studio service port."""
    if os.environ.get("STUDIO_GADMIN_URL"):
        return os.environ["STUDIO_GADMIN_URL"].rstrip("/")
    try:
        manifest = json.loads((gcore_dir() / "manifest.json").read_text())
    except (OSError, ValueError):
        return None
    svcs = manifest.get("services") or []
    port = next((s.get("port") for s in svcs if s.get("id") == "g-studio" and s.get("port")), None)
    return f"http://127.0.0.1:{port}" if port else None


def _get_json(url: str, headers: dict | None = None):
    """(payload, None) or (None, reason). Never raises."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=TIMEOUT_S) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        e.close()
        return None, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        return None, f"unreachable: {getattr(e, 'reason', e)}"
    except ValueError:
        return None, "not JSON"


# ---- gcore graph (cached, refreshed in the background) ------------------------------------------

def _assemble() -> dict:
    path = str(gcore_dir())
    if path not in sys.path:
        sys.path.insert(0, path)
    mod = importlib.import_module("gcore_graph")
    # root: the checkouts beside the gcore checkout, unless GCORE_GRAPH_ROOT says otherwise
    return mod.graph()


def _refresh_graph() -> None:
    t = time.monotonic()
    try:
        value, error = _assemble(), None
    except Exception as e:  # a broken checkout must not take the route down
        log.warning("gcore graph failed", exc_info=True)
        value, error = None, f"{type(e).__name__}: {e}"
    with _lock:
        if value is not None or _graph["value"] is None:
            _graph["value"] = value
        _graph.update(at=time.time(), error=error, refreshing=False, took_s=round(time.monotonic() - t, 2))


def _gcore_graph() -> tuple[dict | None, dict]:
    with _lock:
        fresh = _graph["value"] is not None and time.time() - _graph["at"] < GRAPH_TTL_S
        stale = _graph["value"] is not None and not fresh
        start_bg = stale and not _graph["refreshing"]
        if start_bg:
            _graph["refreshing"] = True
    if start_bg:
        threading.Thread(target=_refresh_graph, daemon=True).start()
    elif _graph["value"] is None:
        _refresh_graph()
    with _lock:
        meta = {"assembled_at": _graph["at"], "took_s": _graph["took_s"], "error": _graph["error"],
                "stale": time.time() - _graph["at"] >= GRAPH_TTL_S}
        return _graph["value"], meta


# ---- live sources -----------------------------------------------------------------------------

def _fetch_live() -> dict:
    token = os.environ.get("GADMIN_TOKEN") or ""
    studio = _studio_base()
    jobs = {
        "status": lambda: _get_json(_brain_upstream() + "/api/status"),
        "nerves": lambda: _get_json(_brain_upstream() + "/api/nerves"),
        "clients": (lambda: _get_json(studio + "/api/gadmin/blocks", {"X-Gadmin-Token": token}))
        if token and studio else (lambda: (None, "GADMIN_TOKEN or the g-studio port is not configured")),
    }
    with ThreadPoolExecutor(len(jobs)) as pool:
        futures = {k: pool.submit(f) for k, f in jobs.items()}
        out = {k: f.result() for k, f in futures.items()}
    clients, why = out["clients"]
    if clients is not None and not isinstance(clients.get("projects"), list):
        out["clients"] = (None, "Studio answered without a projects list")
    return out


def _live_sources() -> dict:
    with _lock:
        if _live["value"] is not None and time.time() - _live["at"] < LIVE_TTL_S:
            return _live["value"]
    value = _fetch_live()
    with _lock:
        _live.update(at=time.time(), value=value)
    return value


# ---- overlay ----------------------------------------------------------------------------------

def _worst(states):
    states = [s for s in states if s]
    return max(states, key=lambda s: RANK.get(s, 2)) if states else None


def _overlay(base: dict, live: dict) -> dict:
    g = json.loads(json.dumps(base))   # never mutate the cached graph
    nodes = {n["id"]: n for n in g["nodes"]}
    status, status_why = live["status"]
    nerves, nerves_why = live["nerves"]
    clients, clients_why = live["clients"]

    if status:
        svc = {s["id"]: s for s in status.get("services") or []}
        dep = {d["id"]: d for d in status.get("dependencies") or []}
        for nid, n in nodes.items():
            src = svc if n["kind"] == "service" else dep if n["kind"] == "dependency" else None
            s = src.get(n["name"]) if src is not None else None
            if s:
                n["health"] = {"state": s.get("state") or "unknown", "detail": s.get("detail"),
                               "source": "brain /api/status"}
        owned: dict[str, list[str]] = {}
        on_host: dict[str, list[str]] = {}
        for e in g["edges"]:
            if e["kind"] == "has_service":
                owned.setdefault(e["from"], []).append(e["to"])
            elif e["kind"] == "runs_on":
                on_host.setdefault(e["to"], []).append(e["from"])
        for groups in (owned, on_host):
            for nid, sids in groups.items():
                states = {sid.split(":", 1)[1]: (nodes[sid].get("health") or {}).get("state") for sid in sids}
                if nid in nodes and any(states.values()):
                    nodes[nid]["health"] = {"state": _worst(states.values()), "services": states,
                                            "source": "brain /api/status"}
        # live check on declared request/stream edges
        for e in g["edges"]:
            if e["kind"] != "connects":
                continue
            e["live"] = None
            if "declared" not in e.get("sources", []) or e.get("via") not in LIVE_VIAS:
                continue
            t = nodes.get(e["to"]) or {}
            if t.get("kind") in ("service", "dependency"):
                states = [(t.get("health") or {}).get("state")]
            else:
                states = [(nodes[s].get("health") or {}).get("state") for s in owned.get(e["to"], [])]
            states = [s for s in states if s]
            if "down" in states:
                e["live"] = "down"
            elif states and all(s == "up" for s in states):
                e["live"] = "up"

    if nerves:
        by_repo = {}
        for n in nerves.get("nodes") or []:
            if n.get("type") == "repo":
                by_repo[n.get("repo")] = {"pair": n.get("pair"), "nerve_dirs": n.get("nerve_dirs"),
                                          "compliant": n.get("compliant")}
        for n in nodes.values():
            if n["kind"] in ("project", "repo"):
                found = by_repo.get(n["name"]) or by_repo.get(os.path.basename(n.get("path") or ""))
                if found:
                    n["health"] = {**(n.get("health") or {"state": None}), "nerves": found}

    studio = nodes.get("project:g-studio")
    if studio is not None:
        studio["clients"] = None
        if clients:
            studio["clients"] = clients.get("projects")
            studio["blocks"] = clients.get("blocks")
            studio["blocks_totals"] = clients.get("totals")

    g["sources"] = {
        "status": {"ok": status is not None, "reason": status_why,
                   "checked_at": (status or {}).get("checked_at")},
        "nerves": {"ok": nerves is not None, "reason": nerves_why},
        "clients": {"ok": clients is not None, "reason": clients_why,
                    "count": len(clients["projects"]) if clients else None},
    }
    g["summary"] = {
        "nodes": len(g["nodes"]), "edges": len(g["edges"]),
        "drift": sum(1 for e in g["edges"] if e.get("drift")),
        "live_down": sum(1 for e in g["edges"] if e.get("live") == "down"),
        "clients": g["sources"]["clients"]["count"],
    }
    return g


def build() -> dict:
    base, meta = _gcore_graph()
    if base is None:
        return {"nodes": [], "edges": [], "problems": [], "graph": meta,
                "sources": {"gcore": {"ok": False, "reason": meta["error"]}}}
    out = _overlay(base, _live_sources())
    out["graph"] = meta
    return out


@router.get("")
async def diagram(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    return await run_in_threadpool(build)
