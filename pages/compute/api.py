"""compute page API, mounted at /api/compute.

Serves compute caches and g-env's temperature overrides. Providers (Claude, Codex,
OpenRouter, Jev) are never called from the request path: `compute-usage.timer`
runs `compute-usage --refresh` every 15 minutes and this route only reads what
it wrote, so a slow or dead provider cannot slow or break the page. Staleness
is derived at read time from each row's own fetched_at, which means a stopped
timer shows up as stale rows with their age instead of as quietly old numbers.

The row contract is owned by g-env's bin/compute-usage (`--json`); this route
imports that script rather than re-parsing the cache, so the two cannot drift.

Auth is checked inline, the page gate in server.py does not cover /api/*.
"""
import datetime as dt
import hmac
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from core.auth import ADMIN_COOKIE, ADMIN_VALUE
from core.instance import sibling

router = APIRouter()

G_ENV = sibling("g-env", "genv")
BIN = os.environ.get("COMPUTE_USAGE_BIN") or str(G_ENV / "bin/compute-usage")
PACE_BIN = os.environ.get("COMPUTE_PACE_BIN") or str(G_ENV / "bin/compute-pace")


def _module(name="compute_usage", path=None):
    loader = importlib.machinery.SourceFileLoader(name, path or BIN)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _bearer_ok(request):
    token = os.environ.get("COMPUTE_READ_TOKEN")
    scheme, _, supplied = request.headers.get("Authorization", "").partition(" ")
    return bool(token and scheme.lower() == "bearer"
                and hmac.compare_digest(supplied.encode(), token.encode()))


def _optional(read):
    try:
        return read()
    except (OSError, ImportError, SyntaxError, ValueError, TypeError, AttributeError, KeyError):
        return None


def _read_json(path):
    return _optional(lambda: json.loads(path.read_text()))


def _temperature_path():
    return Path(os.environ.get("COMPUTE_TEMPERATURE_PY") or G_ENV / "context/temperature.py")


def _mode_state(temperature):
    return {"temps": {name: _optional(lambda: temperature.state(name))
                      for name in ("claude", "codex")},
            "overrides": _optional(lambda: temperature.overrides())}


@router.get("/usage")
def usage(request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")
    try:
        mod = _module()
    except (OSError, ImportError, SyntaxError):
        raise HTTPException(503, "compute-usage is not installed on this host")
    rows = mod.load()
    if rows is None:
        raise HTTPException(503, "no usage snapshot yet, compute-usage.timer has not run")
    return {"rows": rows, "stale_after_seconds": mod.ROW_STALE_AFTER}


@router.get("/pace")
def pace(request: Request):
    """Quota burn against working hours, from compute-pace's cache (never computed here)."""
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")
    try:
        mod = _module("compute_pace", PACE_BIN)
    except (OSError, ImportError, SyntaxError):
        raise HTTPException(503, "compute-pace is not installed on this host")
    data = mod.load()
    if data is None:
        raise HTTPException(503, "no pace snapshot yet, compute-pace.timer has not run")
    return data


@router.get("/state")
def state(request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE and not _bearer_ok(request):
        raise HTTPException(401, "unauthorized")
    path = _temperature_path()
    temperature = _optional(lambda: _module("compute_temperature", str(path)))
    providers = _read_json(path.parent / "providers.json")
    return {"pace": _optional(lambda: _module("compute_pace", PACE_BIN).load()),
            **_mode_state(temperature),
            "spend": _read_json(Path.home() / ".cache/genv/compute-spend.json"),
            "models": _read_json(path.parent / "models.json"),
            "roles": {"order": _optional(lambda: providers["roles"]),
                      "base_effort": _optional(lambda: providers["effort"]),
                      "web": _optional(lambda: providers.get("web", {})),
                      "effective_codex_effort": _optional(lambda: {
                          role: temperature.codex_effort(base)
                          for role, base in providers["effort"].items()})},
            "levels": {"temps": _optional(lambda: list(temperature.WORDS)),
                       "speeds": _optional(lambda: list(temperature.SPEEDS))}}


def _value_module():
    """g-env's value.py, loaded fresh beside the temperature.py it imports by name."""
    context = str(_temperature_path().parent)
    sys.path.insert(0, context)
    try:
        sys.modules.pop("temperature", None)
        return _module("compute_value", str(Path(context) / "value.py"))
    finally:
        sys.path.remove(context)


def _preview(params, value):
    """`claude_temp`, `codex_speed` and so on, as value.py's overrides. Blank means live, `auto`
    is measured temperature and NORMAL is no speed change; nothing here is saved."""
    overrides = {}
    for provider in value.BASE:
        temp, speed = params.get(f"{provider}_temp", ""), params.get(f"{provider}_speed", "")
        o = {}
        if temp:
            o["temp"] = None if temp == "auto" else temp
        if speed:
            o["speed"] = None if speed == "NORMAL" else speed
        if o:
            overrides[provider] = o
    return overrides or None


@router.get("/value")
def value_map(request: Request, role: str = "build", stakes: str = "normal", domain: str = ""):
    """The value model for the page: snapshot() plus value.explain() and value.flips() for one job.

    Eligibility, ranking and flips stay in g-env, so the page shows exactly what g-pick picks.
    Query `claude_temp`, `claude_speed`, `codex_temp` and `codex_speed` preview a mode without
    saving it; the reply then carries the live grid and pick beside the previewed ones.
    """
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE and not _bearer_ok(request):
        raise HTTPException(401, "unauthorized")
    try:
        value = _value_module()
    except (OSError, ImportError, SyntaxError):
        raise HTTPException(503, "g-env value model is not installed on this host")
    domain = domain or None
    try:
        overrides = _preview(request.query_params, value)
        explained = value.explain(role, stakes, domain, overrides=overrides)
        flips = value.flips(role, stakes, domain, overrides=overrides)
        snap = value.snapshot(overrides=overrides)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    live = value.snapshot() if overrides else snap
    context = _temperature_path().parent
    return {**snap, "explain": explained, "flips": flips, "preview": overrides,
            "live": {"grid": live["grid"], "prices": live["prices"],
                     "pick": value.explain(role, stakes, domain)["pick"] if overrides else explained["pick"]},
            "tuning": {"base": value.BASE, "reserve": value.RESERVE, "ratios": value.RATIOS,
                       "files": {"roles": str(context / "providers.json"), "models": str(context / "models.json"),
                                 "prices": str(context / "value.py")}}}


@router.post("/mode")
async def mode(request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")
    origin = request.headers.get("Origin")
    if origin is not None:
        try:
            origin_host = urlsplit(origin).netloc
        except ValueError:
            origin_host = None
        if not origin_host or origin_host.lower() != request.headers.get("Host", "").lower():
            raise HTTPException(403, "cross-origin write")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "bad override")
    if not isinstance(body, dict):
        raise HTTPException(400, "bad override")
    try:
        temperature = _module("compute_temperature", str(_temperature_path()))
    except (OSError, ImportError, SyntaxError):
        raise HTTPException(503, "temperature is not installed on this host")
    provider, temp, speed = body.get("provider"), body.get("temp"), body.get("speed")
    try:
        if ((temp is not None and temp not in temperature.WORDS)
                or (speed is not None and speed not in temperature.SPEEDS)):
            raise ValueError("bad override")
        temperature.set_override(provider, temp, speed, by="gcommand")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    change = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(),
              "provider": provider, "temp": temp, "speed": speed,
              "ip": request.headers.get("X-Real-IP") or (request.client.host if request.client else None)}
    with (Path.home() / ".cache/genv/compute-mode.log").open("a") as log:
        log.write(json.dumps(change) + "\n")
    return _mode_state(temperature)


@router.get("/sync")
def sync(request: Request):
    if not _bearer_ok(request):
        raise HTTPException(401, "unauthorized")
    cache = Path.home() / ".cache/genv"
    return {"pace": _read_json(cache / "compute-pace.json"),
            "mode": _read_json(cache / "compute-mode.json")}
