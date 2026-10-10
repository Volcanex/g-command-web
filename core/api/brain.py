"""Brain proxy, mounted at /api/brain. The brain's REST API answers only its
own hosts, so browser pages reach it through here: same origin, behind the
admin cookie. BRAIN_API (compile time) points pages at this prefix by default;
BRAIN_UPSTREAM is where the brain listens.

The site-wide page gate in server.py does not cover /api/*, so the route
checks the cookie inline (same pattern as pages/photos/api.py).
"""
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from core.auth import ADMIN_COOKIE, ADMIN_VALUE

router = APIRouter(tags=["brain"])

UPSTREAM = os.environ.get("BRAIN_UPSTREAM", "http://127.0.0.1:8766").rstrip("/")
FORWARD = ("accept", "content-type")


def _send(method, url, body, headers):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.headers.get("Content-Type"), e.read()


@router.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
async def proxy(path: str, request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")
    url = f"{UPSTREAM}/api/{urllib.parse.quote(path)}"
    if request.url.query:
        url += "?" + request.url.query
    body = await request.body() or None
    headers = {k: v for k, v in request.headers.items() if k in FORWARD}
    try:
        status, ctype, content = await run_in_threadpool(_send, request.method, url, body, headers)
    except urllib.error.URLError:
        raise HTTPException(502, "brain unreachable")
    return Response(content, status_code=status, media_type=ctype)
