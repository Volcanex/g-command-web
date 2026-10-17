"""voice page API, mounted at /api/voice.

Browser → /api/voice/chat (this, admin-gated) → localhost Voice service /chat.
The page gate in server.py does not cover /api/* routers, so the admin cookie is
enforced here inline (same pattern as pages/gcore/api.py). The Voice service is
not publicly exposed (nginx serves only its /webhook); we reach it over localhost.
"""
import json
import os
import urllib.error
import urllib.request

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.auth import cookie_ok

router = APIRouter()

VOICE_URL = os.environ.get("VOICE_URL", "http://127.0.0.1:8077")


class ChatIn(BaseModel):
    message: str


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    payload = json.dumps({"message": body.message, "session": "web"}).encode()
    req = urllib.request.Request(
        f"{VOICE_URL}/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise HTTPException(502, f"voice service unreachable: {getattr(e, 'reason', e)}")


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
