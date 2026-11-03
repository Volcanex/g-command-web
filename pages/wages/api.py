"""g-wages proxy, mounted at /api/wages.

The /wages page is g-wages' ledger editor, drawn here. g-wages keeps its own
process, data and maths (port 8093 on this host); this router forwards
`/api/wages/<path>` to its `/api/ledger/<path>` over loopback, behind this
site's gate. g-wages has no auth of its own on loopback (its public vhost
used nginx basic-auth), so this gate is the only thing between the internet
and the ledger: never mount it without `cookie_ok`.

This is the money-shaped surface the Hours page deliberately is not
(pages/hours/CLAUDE.md): Hours still forwards activity fields only.

Env:
  WAGES_URL  upstream base, default http://127.0.0.1:8093 (shared with Hours)
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from core.auth import cookie_ok

router = APIRouter(tags=["wages"])

_DROP = {"content-length", "content-encoding", "transfer-encoding", "connection", "set-cookie"}
# The generate route calls GitHub and a classifier for every commit in a week.
_SLOW = 180


def _base() -> str:
    return (os.environ.get("WAGES_URL") or "http://127.0.0.1:8093").rstrip("/")


@router.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def forward(path: str, request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "admin only")
    if ".." in path.split("/"):
        raise HTTPException(400, "bad path")
    headers = {}
    if ctype := request.headers.get("content-type"):
        headers["content-type"] = ctype
    try:
        async with httpx.AsyncClient(timeout=_SLOW) as c:
            up = await c.request(request.method, f"{_base()}/api/ledger/{path}",
                                 params=dict(request.query_params),
                                 content=await request.body(), headers=headers)
    except httpx.HTTPError as exc:
        return JSONResponse({"detail": f"g-wages is not answering ({type(exc).__name__})"}, 502)
    out = {k: v for k, v in up.headers.items() if k.lower() not in _DROP}
    return Response(up.content, status_code=up.status_code, headers=out)
