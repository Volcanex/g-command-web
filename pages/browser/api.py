"""g-browser proxy, mounted at /api/browser.

The /browser page drives the always-on g-browser (port 8098 on this host):
its status, activity feed, mode switch, restart and the noVNC live view. The
browser panel has its own password and cookie; this router signs in for the
visitor by adding g-browser's admin cookie server-side, behind this site's own
gate. The cookie value never reaches the client, so a paired iPhone or Mac
drives the browser with nothing but its device token.

Env:
  GBROWSER_LOCAL_URL     upstream base, default http://127.0.0.1:8098
  GBROWSER_COOKIE        g-browser's cookie name, default gbrowser_admin
  GBROWSER_COOKIE_VALUE  g-browser's admin session secret (gbrowser-admin.env)
"""
from __future__ import annotations

import asyncio
import os

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, Response, StreamingResponse

from core.auth import cookie_ok

router = APIRouter(tags=["browser"])

# Hop-by-hop and framing headers the proxy must not copy across.
_DROP = {"content-length", "content-encoding", "transfer-encoding", "connection", "set-cookie"}


def _base() -> str:
    return (os.environ.get("GBROWSER_LOCAL_URL") or "http://127.0.0.1:8098").rstrip("/")


def _cookies() -> dict:
    value = os.environ.get("GBROWSER_COOKIE_VALUE", "")
    if not value:
        raise HTTPException(503, "GBROWSER_COOKIE_VALUE is not set for g-command")
    return {os.environ.get("GBROWSER_COOKIE", "gbrowser_admin"): value}


def _gate(request: Request) -> None:
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "admin only")


async def _forward(request: Request, path: str, timeout: float = 30) -> Response:
    _gate(request)
    body = await request.body()
    headers = {}
    if ctype := request.headers.get("content-type"):
        headers["content-type"] = ctype
    try:
        async with httpx.AsyncClient(timeout=timeout, cookies=_cookies()) as c:
            up = await c.request(request.method, f"{_base()}/{path}",
                                 params=dict(request.query_params), content=body, headers=headers)
    except httpx.HTTPError as exc:
        return JSONResponse({"ok": False, "error": f"g-browser is not answering: {type(exc).__name__}"}, 502)
    out = {k: v for k, v in up.headers.items() if k.lower() not in _DROP}
    return Response(up.content, status_code=up.status_code, headers=out)


@router.get("/status")
async def status(request: Request):
    return await _forward(request, "api/status", timeout=5)


@router.get("/egress")
async def egress(request: Request):
    return await _forward(request, "api/egress", timeout=60)


@router.get("/activity")
async def activity(request: Request):
    return await _forward(request, "api/activity", timeout=5)


@router.post("/restart")
async def restart(request: Request):
    return await _forward(request, "api/browser/restart", timeout=120)


@router.post("/reseed")
async def reseed(request: Request):
    return await _forward(request, "api/browser/reseed", timeout=300)


@router.get("/shots/{name}")
async def shot(name: str, request: Request):
    if "/" in name or ".." in name:
        raise HTTPException(400, "bad name")
    return await _forward(request, f"shots/{name}")


@router.get("/activity/stream")
async def activity_stream(request: Request):
    _gate(request)
    client = httpx.AsyncClient(timeout=httpx.Timeout(10, read=None), cookies=_cookies())
    try:
        up = await client.send(client.build_request("GET", f"{_base()}/api/activity/stream"), stream=True)
    except httpx.HTTPError:
        await client.aclose()
        return JSONResponse({"ok": False, "error": "g-browser is not answering"}, 502)

    async def gen():
        try:
            async for chunk in up.aiter_raw():
                yield chunk
        finally:
            await up.aclose()
            await client.aclose()

    return StreamingResponse(gen(), status_code=up.status_code, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# noVNC: the static client and its RFB socket, both through g-browser's own
# gated /vnc/ proxy, so websockify stays loopback-only twice over.

@router.get("/vnc/{path:path}")
async def vnc_static(path: str, request: Request):
    return await _forward(request, f"vnc/{path}")


@router.websocket("/vnc/websockify")
async def vnc_socket(ws: WebSocket):
    if not cookie_ok(ws.cookies) or not os.environ.get("GBROWSER_COOKIE_VALUE"):
        await ws.close(code=1008)
        return
    # Echo a subprotocol only when the client offered one: noVNC offers none, and
    # an unrequested one makes the browser drop the socket after the handshake.
    offered = ws.scope.get("subprotocols") or []
    subp = "binary" if "binary" in offered else None
    await ws.accept(subprotocol=subp)
    cookie = "; ".join(f"{k}={v}" for k, v in _cookies().items())
    url = _base().replace("http", "ws", 1) + "/vnc/websockify"
    try:
        up = await websockets.connect(url, subprotocols=["binary"] if subp else None,
                                      additional_headers={"Cookie": cookie},
                                      max_size=None, open_timeout=10, compression=None)
    except Exception:
        await ws.close(code=1011)
        return

    async def client_to_up():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                await up.send(msg["bytes"])
            elif msg.get("text") is not None:
                await up.send(msg["text"])

    async def up_to_client():
        async for frame in up:
            if isinstance(frame, bytes):
                await ws.send_bytes(frame)
            else:
                await ws.send_text(frame)

    tasks = [asyncio.create_task(client_to_up()), asyncio.create_task(up_to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await up.close()
        try:
            await ws.close()
        except Exception:
            pass
