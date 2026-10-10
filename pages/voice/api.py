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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import ADMIN_COOKIE, ADMIN_VALUE

router = APIRouter()

VOICE_URL = os.environ.get("VOICE_URL", "http://127.0.0.1:8077")


class ChatIn(BaseModel):
    message: str


@router.post("/chat")
def chat(body: ChatIn, request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
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
