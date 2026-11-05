"""g-content takes proxy, mounted at /api/recorder.

The Recorder keeps cursor takes (schema gs-cursor-take/1) in g-content as
pieces of the cursor-take recipe. Same gate, token and error shapes as
Showcase: the helpers are imported from pages.showcase.api, so a change to how
Command talks to g-content lands in one place. A take is forwarded raw, since
g-content validates it and names the first bad field itself. Posters stream
through this router's own file route, so the page needs nothing of Showcase.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pages.showcase.api import FILE_NAME, PIECE_ID, _gate, _json, _need, _stream

router = APIRouter(tags=["recorder"])

MAX_TAKE = 4 * 1024 * 1024
SAVE_TIMEOUT_S = 60  # g-content makes the piece before it answers
KINDS = {"gabriel", "you", "agent"}


@router.get("/takes")
async def takes(request: Request, events: str = "", kind: str = "", min_owner: str = ""):
    _gate(request)
    params = {}
    if events:
        if events not in ("0", "1"):
            raise HTTPException(400, "events must be 0 or 1")
        params["events"] = events
    if kind:
        if kind not in KINDS:
            raise HTTPException(400, "kind must be gabriel, you or agent")
        params["kind"] = kind
    if min_owner:
        if not min_owner.isdigit() or not 1 <= int(min_owner) <= 10:
            raise HTTPException(400, "min_owner must be a whole number from 1 to 10")
        params["min_owner"] = min_owner
    return await _json("GET", "/api/takes", params=params)


@router.get("/takes/{piece_id}")
async def take(piece_id: str, request: Request):
    _gate(request)
    _need(PIECE_ID, piece_id, "piece id")
    return await _json("GET", f"/api/takes/{piece_id}")


@router.post("/takes")
async def save(request: Request):
    _gate(request)
    size = request.headers.get("content-length", "")
    if size.isdigit() and int(size) > MAX_TAKE:
        raise HTTPException(413, "the take is over 4 MB")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_TAKE:
            raise HTTPException(413, "the take is over 4 MB")
    if not body:
        raise HTTPException(400, "send the take as JSON")
    return await _json("POST", "/api/takes", content=body, timeout=SAVE_TIMEOUT_S)


@router.delete("/takes/{piece_id}")
async def delete(piece_id: str, request: Request):
    _gate(request)
    _need(PIECE_ID, piece_id, "piece id")
    return await _json("DELETE", f"/api/takes/{piece_id}")


@router.get("/pieces/{piece_id}/files/{name}")
async def piece_file(piece_id: str, name: str, request: Request):
    _gate(request)
    _need(PIECE_ID, piece_id, "piece id")
    _need(FILE_NAME, name, "file name")
    return await _stream(f"/api/pieces/{piece_id}/files/{name}", request, sandbox=True)
