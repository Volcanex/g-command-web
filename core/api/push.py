"""Push fan-out, mounted at /api/push: the alert spine's second destination.

g-brain's `send` posts every alert it pushes to ntfy here as well, and this
route sends it to every paired app over APNs (core/apns.py). g-brain knows a
URL and a shared token and nothing about devices, Apple or G-Command's
routes; this side owns the token registry, the payload and the link.

  POST /api/push   Authorization: Bearer $ALERT_PUSH_TOKEN
                   {level, source, msg, click?}  ->  202 {queued, devices}

It answers before talking to Apple (a background task), so a slow APNs can
never hold up the spine. With ALERT_PUSH_TOKEN unset the route is closed (503).
"""
import hmac
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from core import apns, push_tokens
from core.api import alerts

router = APIRouter(tags=["push"])

# The spine's level -> the ntfy tags it sets (g-brain g_spine/alerts.py _LEVELS),
# so the link is derived exactly as /api/alerts derives it from the ntfy message.
LEVEL_TAGS = {"critical": ["rotating_light"], "error": ["rotating_light"], "warn": ["warning"]}


class PushRequest(BaseModel):
    level: str = "info"
    source: str = ""
    msg: str = ""
    click: str = ""


def _origin() -> str:
    host = os.environ.get("PUBLIC_HOST", "").strip().strip("/").removeprefix("https://")
    return f"https://{host}" if host else ""


def link_for(level: str, source: str, click: str = "") -> str:
    msg = {"title": source, "tags": LEVEL_TAGS.get((level or "").lower(), []), "click": click}
    return alerts._link(msg, _origin())


def _authorised(request: Request) -> bool:
    expected = os.environ.get("ALERT_PUSH_TOKEN", "")
    if not expected:
        raise HTTPException(503, "push is not configured")
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(given.encode(), expected.encode())


@router.post("", status_code=202)
def push(req: PushRequest, request: Request, background: BackgroundTasks):
    if not _authorised(request):
        raise HTTPException(401, "unauthorized")
    link = link_for(req.level, req.source, req.click)
    background.add_task(apns.send_all, req.level, req.source, req.msg[:3500], link)
    return {"queued": True, "configured": apns.config() is not None, "devices": len(push_tokens.live())}
