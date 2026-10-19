"""Native apps: pairing, devices and the navigation manifest, at /api/app.

The iPhone and Mac apps (g-command-apple) talk to this server and nothing
else. A device pairs once and keeps its own token (core/auth.py), sent as the
admin cookie, so it never stores the password, a Brain key or an ntfy topic.

  POST   /api/app/pair/code     signed in: a one-time code, its gcommand://
                                link and the link as a QR (SVG), for Setup
  POST   /api/app/pair          {code} or {password}, plus name and platform:
                                a device token
  GET    /api/app/devices       signed in: paired devices
  DELETE /api/app/devices/{id}  signed in: revoke one
  GET    /api/app/manifest      signed in: sections, entries and panel pages

Codes live in memory for five minutes and work once. A wrong code counts as a
failed login in the same per-IP limit as the password.
"""
import hmac
import os
import secrets
import sys
import threading
import time
import urllib.parse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import auth
from core.api.admin import _UNSET_PASSWORDS, _admin_password, _client_ip, _record_login_failure, _too_many_failures

router = APIRouter(tags=["app"])

CODE_TTL = 300
_codes: dict[str, float] = {}
# One lock across code lookup and consumption, and across the limiter's
# check, the compare and the failure record, so two requests in the thread
# pool can neither redeem one code twice nor both slip under the limit.
_lock = threading.Lock()


def _require(request: Request) -> None:
    if not auth.cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _origin(request: Request) -> str:
    host = os.environ.get("PUBLIC_HOST", "").strip().strip("/") or request.headers.get("host", "")
    host = host.removeprefix("https://").removeprefix("http://")
    return f"https://{host}"


def _take_code(code: str) -> bool:
    now = time.monotonic()
    for c, expires in list(_codes.items()):
        if expires < now:
            _codes.pop(c, None)
    match = next((c for c in _codes if hmac.compare_digest(c.encode(), code.encode())), None)
    if match is None:
        return False
    _codes.pop(match, None)
    return True


@router.post("/pair/code")
def pair_code(request: Request):
    _require(request)
    code = secrets.token_urlsafe(18)
    with _lock:
        _codes[code] = time.monotonic() + CODE_TTL
    link = "gcommand://pair?" + urllib.parse.urlencode({"server": _origin(request), "code": code})
    try:
        import segno
        qr = segno.make(link, error="m").svg_inline(scale=6, border=2, dark="#000", light="#fff")
    except ImportError:
        qr = ""
    return {"code": code, "url": link, "qr_svg": qr, "expires_in": CODE_TTL}


class PairRequest(BaseModel):
    code: str = ""
    password: str = ""
    name: str = ""
    platform: str = ""


@router.post("/pair")
def pair(req: PairRequest, request: Request):
    ip = _client_ip(request)
    with _lock:
        if _too_many_failures(ip):
            raise HTTPException(429, "too many attempts; slow down")
        if req.code:
            ok = _take_code(req.code)
        elif req.password:
            if _admin_password() in _UNSET_PASSWORDS:
                raise HTTPException(503, "Login is disabled until ADMIN_PASSWORD is set.")
            ok = hmac.compare_digest(req.password.encode(), _admin_password().encode())
        else:
            ok = False
        if not ok:
            _record_login_failure(ip)
            raise HTTPException(401, "wrong code or password")
    token, device = auth.add_device(req.name, req.platform)
    return {"token": token, "device_id": device["id"], "cookie_name": auth.ADMIN_COOKIE}


@router.get("/devices")
def devices(request: Request):
    _require(request)
    current = auth.device_for(request.cookies.get(auth.ADMIN_COOKIE, ""))
    rows = auth.list_devices()
    for d in rows:
        d["current"] = bool(current) and d["id"] == current["id"]
    return {"devices": rows}


@router.delete("/devices/{device_id}")
def revoke(device_id: str, request: Request):
    _require(request)
    if not auth.revoke_device(device_id):
        raise HTTPException(404, "no such device")
    return {"ok": True}


@router.get("/manifest")
def manifest(request: Request):
    _require(request)
    from core.panels.manifest import build_manifest
    return build_manifest(_ROOT / "pages")
