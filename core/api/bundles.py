"""Preact page bundles, at /api/bundles.

compile.py bundles every `pages/<slug>/app.js` with esbuild and records each
outcome in var/bundles/status.json: `built`, `stale` (the newest bundle failed,
the last good one is served) or `failed` (no bundle, the page serves its
content.html), with esbuild's error. This route only reads that file, so a
page or the System page can say which Preact pages are not on their newest
build. Admin-gated inline, the page gate in server.py does not cover /api/*.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from core.auth import cookie_ok

router = APIRouter()

STATUS = Path(__file__).resolve().parents[2] / "var" / "bundles" / "status.json"


@router.get("")
def bundles(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    try:
        pages = json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pages = {}
    return {"pages": pages, "failing": sorted(s for s, p in pages.items() if p.get("state") != "built")}
