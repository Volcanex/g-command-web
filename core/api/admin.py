"""Admin auth: single-user, password-gated.

Pair with `_admin_gated()` in `server.py` (which redirects unauthenticated
requests under `/admin/*` to `/admin/login`). This module provides the
matching endpoints:

  POST /api/admin/login: set the admin cookie if the password matches
  POST /api/admin/logout: clear the cookie
  GET  /api/admin/verify: `{admin: bool}` for client-side conditionals
  POST /api/admin/tests/run: run pytest from the browser, admin-gated

Security model: single-user gate. A correct password sets the cookie to
`ADMIN_COOKIE_VALUE`, a second secret, so holding the cookie is being
logged in. There is no default for it: it used to be the constant "ok",
which let anyone forge the cookie, and `core/auth.py` now stops the
server starting without it. Every session shares the one value, so
rotating it logs everyone out. Multi-user or per-session auth needs real
sessions.

Hardening included by default:
- Login is rate-limited (5 failures per IP per 60s).
- Cookie is `Secure` by default; set `ADMIN_COOKIE_SECURE=0` to opt out.
- Password compared with `hmac.compare_digest` (constant time).
- Login is refused (503) while `ADMIN_PASSWORD` is unset or "change-me",
  and module load logs a loud WARNING saying so.

Configure via env vars (the first two are read in `core/auth.py`):

  ADMIN_COOKIE         cookie name             (default: "seed_admin")
  ADMIN_COOKIE_VALUE   cookie value, secret    (required, no default)
  ADMIN_COOKIE_SECURE  1/0; cookie Secure flag (default: "1")
  ADMIN_PASSWORD       required to log in      (no default; login off until set)
"""

from __future__ import annotations

import hmac
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

# Reach project root when this module is auto-mounted by importlib:
# it's loaded by file path, not as a package, so relative imports won't
# work. Adding the project root to sys.path lets us import sibling
# packages (e.g. `core.db`) the same way as a normal `python -m` run.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from core.auth import ADMIN_COOKIE, ADMIN_VALUE

router = APIRouter(tags=["admin"])

# Per-IP login rate limit. In-memory sliding window. It closes brute force
# without pulling in a real auth dependency. Successful login clears
# the bucket so legit usage isn't penalised.
_RATE_WINDOW = 60.0   # seconds
_RATE_LIMIT = 5       # failures per window per IP
_LOGIN_ATTEMPTS: dict[str, deque] = {}

# The whole gate is the password, so an unset one or the old public
# placeholder "change-me" fails closed: login() refuses every attempt.
# Warn once at startup so the operator knows why.
_UNSET_PASSWORDS = ("", "change-me")
if os.environ.get("ADMIN_PASSWORD", "") in _UNSET_PASSWORDS:
    print(
        "WARNING: ADMIN_PASSWORD unset or still 'change-me'. Admin "
        "login is disabled until you set ADMIN_PASSWORD in your "
        "environment.",
        file=sys.stderr,
    )


def _admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "")


def _admin_cookie_secure() -> bool:
    """Cookie `Secure` flag: defaults to True so a deploy that ever
    skips TLS doesn't leak the admin cookie. Set `ADMIN_COOKIE_SECURE=0`
    only for HTTP-only deploys (rare; usually means missing TLS)."""
    return os.environ.get("ADMIN_COOKIE_SECURE", "1").lower() not in ("0", "false", "no")


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting. Trusts X-Forwarded-For
    because the typical seed deploy is behind nginx/Caddy. Make sure
    your proxy strips this header from external requests (nginx and
    Caddy both do by default)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many_failures(ip: str) -> bool:
    bucket = _LOGIN_ATTEMPTS.get(ip)
    if not bucket:
        return False
    cutoff = time.monotonic() - _RATE_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    return len(bucket) >= _RATE_LIMIT


def _record_login_failure(ip: str) -> None:
    bucket = _LOGIN_ATTEMPTS.setdefault(ip, deque())
    bucket.append(time.monotonic())


def is_admin(request: Request) -> bool:
    """Public helper: other API modules can import this to gate endpoints."""
    return request.cookies.get(ADMIN_COOKIE) == ADMIN_VALUE


def require_admin(request: Request) -> None:
    """Raise 401 if the request isn't authenticated. For use in endpoints
    that should be admin-only (declare `request: Request` and call this)."""
    if not is_admin(request):
        raise HTTPException(401, "admin only")


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    ip = _client_ip(request)
    if _too_many_failures(ip):
        raise HTTPException(429, "too many attempts; slow down")
    if _admin_password() in _UNSET_PASSWORDS:
        raise HTTPException(503, "Login is disabled until ADMIN_PASSWORD is set.")
    # Constant-time comparison so a remote attacker can't lift the
    # password byte-by-byte off response timing. Trivial cost, real win.
    if not hmac.compare_digest(req.password, _admin_password()):
        _record_login_failure(ip)
        raise HTTPException(401, "wrong password")
    # Successful login: clear the bucket so legit usage isn't penalised.
    _LOGIN_ATTEMPTS.pop(ip, None)
    response.set_cookie(
        ADMIN_COOKIE,
        ADMIN_VALUE,
        max_age=60 * 60 * 24 * 30,  # 30 days
        httponly=True,
        samesite="lax",
        secure=_admin_cookie_secure(),
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"ok": True}


@router.get("/verify")
def verify(request: Request):
    return {"admin": is_admin(request)}


# ---------- Test runner ---------------------------------------------------
#
# Useful in production: lets you re-run the suite from the admin UI after
# pushing a hotfix. Synchronous (pytest takes a few seconds). Returns
# exit code, full output, and duration. Tests should isolate their state
# (e.g. tmp DBs in conftest.py) so this is safe to run against a live
# container.


@router.post("/tests/run")
def run_tests(request: Request):
    require_admin(request)

    project_root = Path(__file__).resolve().parent.parent.parent
    started = time.time()
    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-v", "--tb=short", "--color=no"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": -1,
            "duration_seconds": time.time() - started,
            "output": (exc.stdout or "") + "\n--- TIMEOUT ---\n" + (exc.stderr or ""),
        }

    duration = time.time() - started
    output = proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else "")
    return {
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 2),
        "output": output,
    }
