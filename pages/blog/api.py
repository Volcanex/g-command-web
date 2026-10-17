"""blog page API, mounted at /api/blog.

Browser -> /api/blog/proxy/{path} (this, admin-gated) -> g-site admin API
(http://127.0.0.1:8096/api/admin/{path}), attaching X-Admin-Token. Same
pattern as pages/voice/api.py. The page gate in server.py does not cover
/api/* routers, so the admin cookie is enforced here inline.

g-site is not publicly exposed; we reach it over localhost. GSITE_ADMIN_TOKEN
lives in the instance passport and is loaded into this process's env by a
systemd drop-in (an EnvironmentFile line for the passport). It is never printed.
"""
import mimetypes
import os
import urllib.error
import urllib.request
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from core.auth import cookie_ok

router = APIRouter()

GSITE_URL = os.environ.get("GSITE_URL", "http://127.0.0.1:8096").rstrip("/")
GSITE_ADMIN_TOKEN = os.environ.get("GSITE_ADMIN_TOKEN", "")

# Preview/publish compile a full edition. Give them more room than the
# usual CRUD round-trip.
_LONG_PATHS = ("preview", "publish")


def _gate(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _timeout_for(path: str) -> int:
    return 60 if any(p in path for p in _LONG_PATHS) else 10


@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    _gate(request)
    body = await request.body()
    url = f"{GSITE_URL}/api/admin/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    headers = {"X-Admin-Token": GSITE_ADMIN_TOKEN}
    if body:
        headers["Content-Type"] = request.headers.get("content-type", "application/json")
    req = urllib.request.Request(url, data=body or None, headers=headers, method=request.method)
    try:
        with urllib.request.urlopen(req, timeout=_timeout_for(path)) as resp:
            return Response(
                content=resp.read(),
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type", "application/json"),
            )
    except urllib.error.HTTPError as e:
        return Response(
            content=e.read(),
            status_code=e.code,
            media_type=e.headers.get("Content-Type", "application/json"),
        )
    except urllib.error.URLError as e:
        raise HTTPException(502, f"g-site unreachable: {getattr(e, 'reason', e)}")


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    _gate(request)
    data = await file.read()
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file.filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{GSITE_URL}/api/admin/media",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Admin-Token": GSITE_ADMIN_TOKEN,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return Response(
                content=resp.read(),
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type", "application/json"),
            )
    except urllib.error.HTTPError as e:
        return Response(
            content=e.read(),
            status_code=e.code,
            media_type=e.headers.get("Content-Type", "application/json"),
        )
    except urllib.error.URLError as e:
        raise HTTPException(502, f"g-site unreachable: {getattr(e, 'reason', e)}")
