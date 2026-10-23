"""voice page API, mounted at /api/voice.

Browser → /api/voice/chat (this, admin-gated) → localhost Voice service /chat.
The page gate in server.py does not cover /api/* routers, so the admin cookie is
enforced here inline (same pattern as pages/gcore/api.py). The Voice service is
not publicly exposed (nginx serves only its /webhook); we reach it over localhost.
"""
import json
import os
from pathlib import Path
from typing import Literal
import urllib.error
import urllib.request

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.auth import cookie_ok

router = APIRouter()

VOICE_URL = os.environ.get("VOICE_URL", "http://127.0.0.1:8077")


# The app keeps its own conversation ("app") so it never interleaves with the
# web page's ("web") or WhatsApp's. Both phone and Mac share it.
Session = Literal["web", "app"]

# The Voice service writes one JSONL transcript per session here (brain-tools
# voice/transcript.py, g_config.VOICE_TRANSCRIPT_DIR). It has no history route,
# so this reads the file it already keeps: {"ts", "role", "text"} per line.
TRANSCRIPT_DIR = Path(os.environ.get(
    "VOICE_TRANSCRIPT_DIR",
    Path(os.environ.get("BRAIN_ROOT", "/home/gabriel/brain")) / ".pulse" / "state" / "voice"))


class ChatIn(BaseModel):
    message: str
    session: Session = "web"


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    payload = json.dumps({"message": body.message, "session": body.session}).encode()
    req = urllib.request.Request(
        f"{VOICE_URL}/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise HTTPException(502, f"voice service unreachable: {getattr(e, 'reason', e)}")


@router.get("/history")
def history(request: Request, session: Session = "app", limit: int = 100):
    """The last `limit` turns of one session, oldest first, as {ts, role, text}."""
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
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
                    turns.append({"ts": obj.get("ts", ""), "role": obj["role"], "text": obj["text"]})
    except FileNotFoundError:
        pass
    return {"session": session, "turns": turns[-limit:]}


class TalkIn(BaseModel):
    message: str


@router.post("/talk")
async def talk(body: TalkIn, request: Request):
    """Spoken turn: relays the Voice service's NDJSON sentence stream as it arrives."""
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
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
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{VOICE_URL}/tts", json={"text": body.text[:400]})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"voice service unreachable: {type(e).__name__}")
    if r.status_code != 200:
        raise HTTPException(502, f"tts {r.status_code}")
    return Response(content=r.content, media_type="audio/wav",
                    headers={"Cache-Control": "no-store", "X-Synth-Ms": r.headers.get("x-synth-ms", "")})
