"""Projects gallery API, mounted at /api/projects. Admin-gated.

Serves the screenshot + git-metadata sidecar produced by
`scripts/refresh_projects.py` into `var/`, a sibling of `output/`, which
`compile.py` wipes on every restart. Thumbnails go through this gated route
rather than a public StaticFiles mount so they stay behind the site password
(cookies ride along with same-origin <img> requests). The site-wide page gate
in server.py does not cover /api/*, so each route re-checks the cookie inline
(same pattern as pages/gcore/api.py).
"""
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.auth import ADMIN_COOKIE, ADMIN_VALUE

router = APIRouter()

GCOMMAND = Path(__file__).resolve().parent.parent.parent
VAR = GCOMMAND / "var"
SHOTS = VAR / "shots"
META = VAR / "projects-meta.json"

# Project ids are lowercase/digits/hyphen (e.g. photo-sync-server). Anchored so
# nothing with a slash or dot reaches the filesystem join below.
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _gate(request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")


@router.get("/meta")
def meta(request: Request):
    _gate(request)
    if META.is_file():
        try:
            return json.loads(META.read_text())
        except Exception:
            pass
    return {"generated_at": None, "projects": {}}


@router.get("/shot/{pid}")
def shot(pid: str, request: Request):
    _gate(request)
    if not ID_RE.match(pid):
        raise HTTPException(404)
    f = SHOTS / f"{pid}.jpg"
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/jpeg")
