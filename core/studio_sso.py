"""Signing in to Command with Studio. Studio is the identity provider; Command only checks.

When a page request has no admin cookie, the gate in server.py sends the browser to
/auth/studio/start. That makes a random state, keeps it (with the page to return to) in a
short-lived host-only cookie, and redirects to Studio's GET /sso/command. Studio signs Gabriel
in if needed and redirects back to /auth/studio/callback with an Ed25519-signed assertion.
Command verifies it with Studio's PUBLIC key only, so nothing on this host can mint one, and
sets the same admin cookie the password sign-in sets.

The assertion is accepted only when: the signature checks, aud is this origin, the nonce is
the state in this browser's cookie (then spent), it has not expired, adm is true and sub is
the one Studio user who is Command's admin (STUDIO_ADMIN_USER_ID, user 29).

Break-glass: /login keeps the password sign-in. Studio being down, unconfigured or refusing
never locks Command: every failure here lands on /login with a reason.

Configuration (env):
  STUDIO_ORIGIN           Studio's origin, e.g. https://studio.gabrielpenman.com
  STUDIO_IDP_PUBLIC_KEY   base64 of Studio's 32-byte Ed25519 public key (/etc/g-secrets)
  STUDIO_ADMIN_USER_ID    the Studio user id that is Command's admin (default 29)
Without the first two, the gate sends everyone to /login as before.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
from urllib.parse import quote, unquote, urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from core import auth

router = APIRouter()

STATE_COOKIE = "gc_studio_sso"
STATE_TTL = 600
CALLBACK_PATH = "/auth/studio/callback"
SKEW = 30
_NEXT_RE = re.compile(r"/(?!/)[^\s\\]*")


def studio_origin() -> str:
    return (os.environ.get("STUDIO_ORIGIN") or "").rstrip("/")


def public_key() -> Ed25519PublicKey | None:
    raw = (os.environ.get("STUDIO_IDP_PUBLIC_KEY") or "").strip()
    if not raw:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw))
    except Exception:
        return None


def admin_user_id() -> str:
    return (os.environ.get("STUDIO_ADMIN_USER_ID") or "29").strip()


def enabled() -> bool:
    return bool(studio_origin()) and public_key() is not None


def safe_next(n: str) -> str:
    return n if n and _NEXT_RE.fullmatch(n) else "/"


def _secure() -> bool:
    return os.environ.get("ADMIN_COOKIE_SECURE", "1").lower() not in ("0", "false", "no")


def own_origin(request: Request) -> str:
    """This origin as the browser sees it (nginx terminates TLS)."""
    host = request.headers.get("host", "")
    scheme = "https" if _secure() else request.url.scheme
    return f"{scheme}://{host}"


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify(token: str, *, aud: str, nonce: str, now: float | None = None) -> dict | None:
    """The claims when the assertion is good for Command's admin here, else None."""
    key = public_key()
    if key is None or not token or token.count(".") != 1 or len(token) > 4096:
        return None
    body, sig = token.split(".")
    try:
        key.verify(_b64(sig), body.encode())
        c = json.loads(_b64(body))
    except (InvalidSignature, ValueError):
        return None
    now = time.time() if now is None else now
    if not isinstance(c, dict):
        return None
    ok = (c.get("aud") == aud
          and isinstance(nonce, str) and len(nonce) >= 16 and secrets.compare_digest(str(c.get("nonce", "")), nonce)
          and c.get("iss") == studio_origin()
          and isinstance(c.get("exp"), int) and isinstance(c.get("iat"), int)
          and c["iat"] - SKEW <= now < c["exp"] + SKEW and c["exp"] - c["iat"] <= 300
          and c.get("adm") is True and str(c.get("sub")) == admin_user_id())
    return c if ok else None


def _to_login(reason: str) -> RedirectResponse:
    r = RedirectResponse("/login?" + urlencode({"studio": reason}), status_code=302)
    r.delete_cookie(STATE_COOKIE, path="/auth/studio")
    r.headers["Cache-Control"] = "no-store"
    return r


def _studio_up() -> bool:
    """A short probe so a Studio outage lands on the password sign-in, not a 502."""
    try:
        r = httpx.get(studio_origin() + "/api/auth/config", timeout=2.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/auth/studio/start", include_in_schema=False)
async def start(request: Request, next: str = "/"):
    if not enabled():
        return _to_login("off")
    if not await run_in_threadpool(_studio_up):
        return _to_login("down")
    state = secrets.token_urlsafe(24)
    q = urlencode({"return_to": own_origin(request) + CALLBACK_PATH, "state": state})
    r = RedirectResponse(f"{studio_origin()}/sso/command?{q}", status_code=302)
    r.set_cookie(STATE_COOKIE, state + "|" + quote(safe_next(next), safe="/"), max_age=STATE_TTL,
                 path="/auth/studio", httponly=True, samesite="lax", secure=_secure())
    r.headers["Cache-Control"] = "no-store"
    return r


@router.get(CALLBACK_PATH, include_in_schema=False)
async def callback(request: Request, state: str = "", assertion: str = "", error: str = ""):
    kept = request.cookies.get(STATE_COOKIE, "")
    want, _, nxt = kept.partition("|")
    if not want or not secrets.compare_digest(state, want):
        return _to_login("expired")
    if error:
        return _to_login("not_admin" if error == "not_admin" else "refused")
    if verify(assertion, aud=own_origin(request), nonce=want) is None:
        return _to_login("refused")
    r = RedirectResponse(safe_next(unquote(nxt)), status_code=302)
    r.delete_cookie(STATE_COOKIE, path="/auth/studio")
    r.set_cookie(auth.ADMIN_COOKIE, auth.ADMIN_VALUE, max_age=60 * 60 * 24 * 30, httponly=True,
                 samesite="lax", secure=_secure(), path="/")
    r.headers["Cache-Control"] = "no-store"
    return r
