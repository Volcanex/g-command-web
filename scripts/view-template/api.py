"""__TITLE__ API, mounted at /api/__SLUG__. Admin-gated inline (the page gate in
server.py does not cover /api/*). Replace the body with the view's real data."""
from fastapi import APIRouter, HTTPException, Request

from core.auth import cookie_ok

router = APIRouter()


@router.get("")
async def index(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    return {"items": []}
