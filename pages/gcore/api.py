"""gcore passport API, mounted at /api/gcore.

Admin-gated: the instance passport holds secrets. The site's page gate
(server.py) does not cover /api/* routers, so the cookie check is enforced
here, inline, so it does not depend on importing the admin module.
ADMIN_COOKIE_VALUE has no default; core/auth.py stops the server without it.

GET returns the passport's key names and whether each is set, never a value.
A value leaves only through POST /reveal, one key per request, when someone
asks for it on the page.
"""
import json

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from core.auth import cookie_ok
from core.instance import gcore_dir

router = APIRouter()

GCORE = gcore_dir()


def _parse_env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _gate(request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _passport():
    env_f = GCORE / ".env"
    return _parse_env(env_f.read_text()) if env_f.exists() else {}


@router.get("")
def gcore(request: Request):
    _gate(request)
    manifest_f = GCORE / "manifest.json"
    conv_f = GCORE / "conventions.md"
    return {
        "manifest": json.loads(manifest_f.read_text()) if manifest_f.exists() else None,
        "conventions": conv_f.read_text() if conv_f.exists() else "",
        "env": {key: bool(value) for key, value in _passport().items()},
        "source": str(GCORE),
    }


class RevealRequest(BaseModel):
    key: str


@router.post("/reveal")
def reveal(req: RevealRequest, request: Request, response: Response):
    _gate(request)
    env = _passport()
    if req.key not in env:
        raise HTTPException(404, "no such key")
    response.headers["Cache-Control"] = "no-store"
    return {"key": req.key, "value": env[req.key]}
