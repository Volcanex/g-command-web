"""voice page API, mounted at /api/voice.

Browser or app → /api/voice/* (this, cookie-gated) → localhost Voice service.
The page gate in server.py does not cover /api/* routers, so the cookie is
enforced here inline (same pattern as pages/gcore/api.py). The Voice service is
not publicly exposed (nginx serves only its /webhook); we reach it over localhost.

  POST /api/voice/chat         {message, session, budget?, attachments?} → {reply}
                               (web) or {reply, blocks} (app)
  POST /api/voice/chat/stream  same body, app session only: NDJSON delta/tool/done
  POST /api/voice/upload       raw body, Content-Type the file's, X-Filename → upload
  GET  /api/voice/files/{id}   an upload, behind the same cookie
  GET  /api/voice/history      {session, turns: [{ts, role, text, blocks?, attachments?}]}
  POST /api/voice/talk, /tts   spoken turns (the native app reads /tts)
  WS   /api/voice/live         a live call, frames relayed both ways unchanged
                               to the Voice service's /live (contract in
                               g-brain voice/CLAUDE.md, "Live call")

Reply blocks follow core/panels/CLAUDE.md. A `panel` block from Voice is a
reference; `expand` replaces it with the live panel built by core/panels, so
the chat shows exactly what the dash shows.
"""
import asyncio
import base64
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.auth import cookie_ok

router = APIRouter()

VOICE_URL = os.environ.get("VOICE_URL", "http://127.0.0.1:8077")
# Voice reads agent activity back from this server over localhost.
# The live call's upstream; tests point it at a fake server.
VOICE_LIVE_URL = os.environ.get("VOICE_LIVE_URL", "ws://127.0.0.1:8077/live")
LOCAL_URL = os.environ.get("GCOMMAND_LOCAL_URL", f"http://127.0.0.1:{os.environ.get('PORT', '8089')}")


# The app keeps its own conversation ("app") so it never interleaves with the
# web page's ("web") or WhatsApp's. Both phone and Mac share it.
Session = Literal["web", "app"]

# The Voice service writes one JSONL transcript per session here (brain-tools
# voice/transcript.py, g_config.VOICE_TRANSCRIPT_DIR). It has no history route,
# so this reads the file it already keeps: {"ts", "role", "text"} per line, plus
# `blocks` on app replies and `attachments` on app user turns.
TRANSCRIPT_DIR = Path(os.environ.get(
    "VOICE_TRANSCRIPT_DIR",
    Path(os.environ.get("BRAIN_ROOT", "/home/gabriel/brain")) / ".pulse" / "state" / "voice"))

# Uploads live in gitignored var/, which compile.py never wipes. One file per
# upload, named by a random id, beside a .json with its name and type.
UPLOAD_DIR = Path(os.environ.get("VOICE_UPLOAD_DIR", "")
                  or Path(__file__).resolve().parent.parent.parent / "var" / "voice-uploads")
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
TEXT_TYPES = {"text/plain": ".txt", "text/markdown": ".md", "text/csv": ".csv", "application/json": ".json"}
FILE_TYPES = {**TEXT_TYPES, "application/pdf": ".pdf"}
MAX_IMAGE = 8 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
MAX_ATTACHMENTS = 4
_ID = re.compile(r"^[0-9a-f]{32}$")


def _require(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


class Budget(BaseModel):
    lines: int = Field(ge=1, le=400)
    chars_per_line: int = Field(ge=8, le=400)


class ChatIn(BaseModel):
    message: str = Field(max_length=8000)
    session: Session = "web"
    budget: Budget | None = None
    attachments: list[str] = Field(default=[], max_length=MAX_ATTACHMENTS)


# --- uploads -----------------------------------------------------------------

def _meta(upload_id: str) -> dict | None:
    if not _ID.match(upload_id or ""):
        return None
    try:
        return json.loads((UPLOAD_DIR / f"{upload_id}.json").read_text())
    except (OSError, ValueError):
        return None


def _public(meta: dict) -> dict:
    return {k: meta[k] for k in ("id", "kind", "name", "content_type", "size", "url")}


@router.post("/upload")
async def upload(request: Request):
    """Raw body upload. Content-Type is the file's own (JPEG, PNG, WebP, GIF,
    PDF, plain text, Markdown, CSV, JSON); X-Filename names it (URL-encoded)."""
    _require(request)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in IMAGE_TYPES and ctype not in FILE_TYPES:
        raise HTTPException(415, "unsupported type")
    kind = "image" if ctype in IMAGE_TYPES else "file"
    limit = MAX_IMAGE if kind == "image" else MAX_FILE
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "too large")
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise HTTPException(413, "too large")
    if not data:
        raise HTTPException(400, "empty")
    raw_name = urllib.parse.unquote(request.headers.get("x-filename", "")) or f"upload{(IMAGE_TYPES | FILE_TYPES)[ctype]}"
    name = re.sub(r"[^\w.\- ()]", "_", os.path.basename(raw_name))[:120] or "upload"
    upload_id = secrets.token_hex(16)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    ext = (IMAGE_TYPES | FILE_TYPES)[ctype]
    fd = os.open(UPLOAD_DIR / f"{upload_id}{ext}", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    meta = {"id": upload_id, "kind": kind, "name": name, "content_type": ctype, "size": len(data),
            "url": f"/api/voice/files/{upload_id}", "file": f"{upload_id}{ext}", "created": int(time.time())}
    fd = os.open(UPLOAD_DIR / f"{upload_id}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(meta, fh)
    return _public(meta)


@router.get("/files/{upload_id}")
def files(upload_id: str, request: Request):
    _require(request)
    meta = _meta(upload_id)
    if meta is None:
        raise HTTPException(404, "not found")
    path = UPLOAD_DIR / meta["file"]
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type=meta["content_type"],
                        headers={"Cache-Control": "private, max-age=86400"})


def _attachments(ids: list[str]) -> tuple[list, list, list]:
    """(images for the model, files for the model, metadata for history)."""
    images, docs, meta_out = [], [], []
    for upload_id in ids:
        meta = _meta(upload_id)
        if meta is None:
            raise HTTPException(400, f"unknown attachment {upload_id[:40]}")
        data = (UPLOAD_DIR / meta["file"]).read_bytes()
        meta_out.append(_public(meta))
        if meta["kind"] == "image":
            images.append({"content_type": meta["content_type"], "data": base64.b64encode(data).decode()})
        elif meta["content_type"] in TEXT_TYPES:
            docs.append({"name": meta["name"], "content_type": meta["content_type"],
                         "text": data.decode("utf-8", "replace")[:MAX_TEXT_CHARS]})
        else:
            docs.append({"name": meta["name"], "content_type": meta["content_type"], "text": None})
    return images, docs, meta_out


# --- blocks ------------------------------------------------------------------

def expand(blocks, request, live=True):
    """Replace each `panel` reference with the panel itself (core/panels), or,
    for history (live=False), with a one-row link: an old message must not
    show today's data as if it were what Voice said back then."""
    from core.panels import PANELS, build
    from core.panels.context import Context
    out = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "fold":
            b = {**b, "blocks": expand(b.get("blocks"), request, live)}
        if b.get("type") == "panel" and b.get("name") in PANELS:
            if live:
                p = build(b["name"], Context(request))
                b = {"type": "panel", "name": b["name"],
                     **{k: p.get(k) for k in ("title", "icon", "link", "link_label", "meta", "state", "message", "blocks")}}
            else:
                title, icon, link, label = PANELS[b["name"]][:4]
                b = {"type": "rows", "rows": [{"id": f"panel-{b['name']}", "title": title,
                                               "detail": "Live panel, open it for the current view",
                                               "lead": {"text": "", "icon": icon, "tone": "muted"}, "link": link}]}
        out.append(b)
    return out


# --- chat --------------------------------------------------------------------

def _voice_payload(body: ChatIn) -> dict:
    payload = {"message": body.message, "session": body.session}
    if body.session == "app":
        from pages.sessions.api import activity_grant
        images, docs, meta = _attachments(body.attachments)
        payload.update(images=images, files=docs, attachments=meta,
                       activity={"url": f"{LOCAL_URL}/api/sessions/activity", "grant": activity_grant()})
        if body.budget:
            payload["budget"] = body.budget.model_dump()
    elif body.attachments:
        raise HTTPException(400, "attachments are for the app session")
    return payload


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    _require(request)
    payload = json.dumps(_voice_payload(body)).encode()
    req = urllib.request.Request(
        f"{VOICE_URL}/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise HTTPException(502, f"voice service unreachable: {getattr(e, 'reason', e)}")
    if body.session == "app":
        out["blocks"] = expand(out.get("blocks"), request)
    return out


@router.post("/chat/stream")
async def chat_stream(body: ChatIn, request: Request):
    """App session turn, NDJSON relayed line by line; the done line's blocks
    are expanded here exactly as /chat expands them."""
    _require(request)
    if body.session != "app":
        raise HTTPException(400, "streaming is for the app session")
    payload = _voice_payload(body)
    client = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5))
    try:
        upstream = await client.send(client.build_request("POST", f"{VOICE_URL}/chat/stream", json=payload),
                                     stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(502, f"voice service unreachable: {type(e).__name__}")

    async def relay():
        try:
            async for line in upstream.aiter_lines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("t") == "done":
                    try:
                        ev["blocks"] = await asyncio.to_thread(expand, ev.get("blocks"), request)
                    except Exception:
                        ev["blocks"] = []
                yield json.dumps(ev) + "\n"
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(relay(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/history")
def history(request: Request, session: Session = "app", limit: int = 100):
    """The last `limit` turns of one session, oldest first, as {ts, role, text},
    with `blocks` on rich replies and `attachments` on turns that sent files."""
    _require(request)
    limit = max(1, min(limit, 500))
    turns = []
    try:
        with open(TRANSCRIPT_DIR / f"{session}.jsonl") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("role") in ("user", "assistant") and isinstance(obj.get("text"), str):
                    turn = {"ts": obj.get("ts", ""), "role": obj["role"], "text": obj["text"]}
                    if isinstance(obj.get("blocks"), list) and obj["blocks"]:
                        turn["blocks"] = obj["blocks"]
                    if isinstance(obj.get("attachments"), list) and obj["attachments"]:
                        turn["attachments"] = obj["attachments"]
                    turns.append(turn)
    except FileNotFoundError:
        pass
    turns = turns[-limit:]
    for t in turns:
        if "blocks" in t:
            t["blocks"] = expand(t["blocks"], request, live=False)
    return {"session": session, "turns": turns}


class TalkIn(BaseModel):
    message: str


@router.post("/talk")
async def talk(body: TalkIn, request: Request):
    """Spoken turn: relays the Voice service's NDJSON sentence stream as it arrives."""
    _require(request)
    client = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=5))
    try:
        req = client.build_request("POST", f"{VOICE_URL}/talk",
                                   json={"message": body.message[:2000], "session": "talk"})
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(502, f"voice service unreachable: {type(e).__name__}")

    async def relay():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(relay(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


class TtsIn(BaseModel):
    text: str


@router.post("/tts")
async def tts(body: TtsIn, request: Request):
    """One sentence to WAV (warm Kokoro on h, behind the Voice service)."""
    _require(request)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{VOICE_URL}/tts", json={"text": body.text[:400]})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"voice service unreachable: {type(e).__name__}")
    if r.status_code != 200:
        raise HTTPException(502, f"tts {r.status_code}")
    return Response(content=r.content, media_type="audio/wav",
                    headers={"Cache-Control": "no-store", "X-Synth-Ms": r.headers.get("x-synth-ms", "")})


# --- live call ---------------------------------------------------------------

@router.websocket("/live")
async def live(ws: WebSocket):
    """One call: every frame goes through as it arrives, text and binary, with
    nothing buffered here, and either side closing closes the other."""
    await ws.accept()
    # Accepted first so the client gets a readable close code, not a bare 403.
    if not cookie_ok(ws.cookies):
        await ws.close(code=4401, reason="unauthorized")
        return
    try:
        up = await websockets.connect(VOICE_LIVE_URL, max_size=None, open_timeout=5,
                                      ping_interval=None, compression=None)
    except Exception:
        await ws.send_text(json.dumps({"type": "error", "message": "The voice service is not answering."}))
        await ws.close(code=1011)
        return

    closed_by_client = {}

    async def client_to_up():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                closed_by_client["code"] = msg.get("code") or 1000
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
        await asyncio.gather(*tasks, return_exceptions=True)
        if closed_by_client:
            code = closed_by_client["code"]
            await up.close(code=code if 1000 <= code < 5000 and code not in (1005, 1006) else 1000)
            return
        code = up.close_code or 1000
        await up.close()
        try:
            await ws.close(code=code if code != 1006 else 1011)
        except Exception:
            pass
