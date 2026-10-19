from fastapi import APIRouter, HTTPException, Request

from core.auth import cookie_ok
from core.panels import PANELS, build
from core.panels.context import Context


router = APIRouter(tags=["panels"])


@router.get("/{name}")
def get_panel(name: str, request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    if name not in PANELS:
        raise HTTPException(404, "unknown panel")
    return build(name, Context(request))
