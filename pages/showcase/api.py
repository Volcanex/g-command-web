"""g-content proxy, mounted at /api/showcase.

Showcase reads g-content's recipes and pieces and posts Gabriel's ratings, only
through g-content's HTTP API. g-content wants its token on every /api/* call, so
the browser asks here and this router adds `Authorization: Bearer <token>`
server-side. The token never leaves this process: responses carry only the
upstream body, and errors name the missing setting, never its value.

Env, read at call time like core/api/runners.py:
  G_CONTENT_URL         upstream base, default http://127.0.0.1:8180
  G_CONTENT_TOKEN       the token, else the file below
  G_CONTENT_TOKEN_FILE  default /etc/g-content/token

JSON routes answer an unreachable or unconfigured upstream with 200 and
`{"error": {"code", "message"}}`, so the page can say what happened. Upstream
4xx JSON errors pass through with their status. Piece files stream with Range
both ways so video seeks. Agent-made html and svg get a sandbox CSP, so they
never run in this origin even when opened directly. URLs inside responses stay
g-content paths: the page rewrites them (app.js `px`), the one place that does.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from core.auth import cookie_ok

router = APIRouter(tags=["showcase"])

TIMEOUT_S = 5
RECIPE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PIECE_ID = re.compile(r"^[a-z0-9-]+-[0-9]{8}-[0-9a-f]{6}$")
FILE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VENDOR_PATH = re.compile(r"^(build|examples/jsm)/[A-Za-z0-9._/-]+$")
STATUSES = {"unjudged", "candidate", "rejected"}
# Passed back on a file, so a seek works and the browser knows what it holds.
_FILE_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges",
                 "etag", "last-modified", "cache-control")
_SANDBOXED = ("text/html", "image/svg+xml")


def _base() -> str:
    return (os.environ.get("G_CONTENT_URL") or "http://127.0.0.1:8180").rstrip("/")


def _token() -> str | None:
    tok = (os.environ.get("G_CONTENT_TOKEN") or "").strip()
    if tok:
        return tok
    path = Path(os.environ.get("G_CONTENT_TOKEN_FILE") or "/etc/g-content/token")
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def _error(code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}})


NO_TOKEN = ("no_token", "No g-content token is set. Set G_CONTENT_TOKEN or put the token in "
            "G_CONTENT_TOKEN_FILE (default /etc/g-content/token), then restart gcommand.")
DOWN = ("unreachable", "g-content is not answering on loopback. Start it with "
        "`systemctl start g-content` on h, then try again.")


def _gate(request: Request) -> None:
    # The site-wide page gate in server.py does not cover /api/*.
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_S)


async def _json(method: str, path: str, params: dict | None = None, body: dict | None = None):
    token = _token()
    if not token:
        return _error(*NO_TOKEN)
    try:
        async with _client() as c:
            up = await c.request(method, _base() + path, params=params, json=body,
                                 headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        return _error(*DOWN)
    if up.status_code in (401, 403):
        return _error("rejected", f"g-content refused the token ({up.status_code}). "
                      "Check it matches CONTENT_TOKEN on g-content.")
    try:
        data = up.json()
    except ValueError:
        if up.status_code >= 400:
            return _error("upstream", f"g-content answered {up.status_code}.")
        return _error("bad_payload", "g-content answered with something that is not JSON.")
    if 400 <= up.status_code < 500:
        return JSONResponse(data, status_code=up.status_code)
    if up.status_code >= 500:
        return _error("upstream", f"g-content answered {up.status_code}.")
    return JSONResponse(data)


async def _stream(path: str, request: Request, sandbox: bool):
    token = _token()
    if not token:
        raise HTTPException(503, NO_TOKEN[1])
    headers = {"Authorization": f"Bearer {token}"}
    for h in ("range", "if-range", "if-none-match", "if-modified-since"):
        if v := request.headers.get(h):
            headers[h] = v
    client = _client()
    try:
        up = await client.send(client.build_request("GET", _base() + path, headers=headers), stream=True)
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(502, DOWN[1])

    async def close():
        await up.aclose()
        await client.aclose()

    if up.status_code >= 400 and up.status_code not in (416,):
        body = await up.aread()
        await close()
        if up.status_code in (401, 403):
            raise HTTPException(502, "g-content refused the token.")
        return Response(body, status_code=up.status_code,
                        media_type=up.headers.get("content-type", "application/json"))
    out = {k: v for k, v in up.headers.items() if k.lower() in _FILE_HEADERS}
    ctype = up.headers.get("content-type", "").split(";")[0].strip().lower()
    out["X-Content-Type-Options"] = "nosniff"
    if sandbox and ctype in _SANDBOXED:
        out["Content-Security-Policy"] = "sandbox allow-scripts"
    return StreamingResponse(up.aiter_raw(), status_code=up.status_code, headers=out,
                             background=BackgroundTask(close))


def _need(pattern: re.Pattern, value: str, what: str) -> None:
    if not pattern.match(value):
        raise HTTPException(400, f"bad {what}")


@router.get("/recipes")
async def recipes(request: Request):
    _gate(request)
    return await _json("GET", "/api/recipes")


@router.get("/recipes/{recipe_id}")
async def recipe(recipe_id: str, request: Request):
    _gate(request)
    _need(RECIPE_ID, recipe_id, "recipe id")
    return await _json("GET", f"/api/recipes/{recipe_id}")


@router.get("/pieces")
async def pieces(request: Request, recipe: str = "", status: str = ""):
    _gate(request)
    params = {}
    if recipe:
        _need(RECIPE_ID, recipe, "recipe id")
        params["recipe"] = recipe
    if status:
        if status not in STATUSES:
            raise HTTPException(400, "bad status")
        params["status"] = status
    return await _json("GET", "/api/pieces", params=params)


@router.get("/pieces/{piece_id}")
async def piece(piece_id: str, request: Request):
    _gate(request)
    _need(PIECE_ID, piece_id, "piece id")
    return await _json("GET", f"/api/pieces/{piece_id}")


@router.get("/pieces/{piece_id}/files/{name}")
async def piece_file(piece_id: str, name: str, request: Request):
    _gate(request)
    _need(PIECE_ID, piece_id, "piece id")
    _need(FILE_NAME, name, "file name")
    return await _stream(f"/api/pieces/{piece_id}/files/{name}", request, sandbox=True)


@router.post("/pieces/{piece_id}/rating")
async def rate(piece_id: str, request: Request):
    _gate(request)
    _need(PIECE_ID, piece_id, "piece id")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "send JSON")
    score, note = (body or {}).get("score"), (body or {}).get("note", "")
    if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 10:
        raise HTTPException(400, "score must be a whole number from 1 to 10")
    if not isinstance(note, str) or len(note) > 500:
        raise HTTPException(400, "note must be text of at most 500 characters")
    return await _json("POST", f"/api/pieces/{piece_id}/rating", body={"score": score, "note": note})


@router.get("/calibration")
async def calibration(request: Request):
    _gate(request)
    return await _json("GET", "/api/calibration")


@router.get("/runners")
async def runners(request: Request):
    _gate(request)
    return await _json("GET", "/api/runners")


@router.get("/vendor/three/{path:path}")
async def vendor_three(path: str, request: Request):
    _gate(request)
    if ".." in path or "//" in path or not VENDOR_PATH.match(path):
        raise HTTPException(400, "bad vendor path")
    return await _stream(f"/vendor/three/{path}", request, sandbox=False)
