"""Alerts, mounted at /api/alerts: the ntfy spine, read server-side.

The spine's topic is a secret (on ntfy.sh knowing it is enough to read and
publish), so the apps never hold it. This route polls `NTFY_URL` (from the
instance .env, the unit's EnvironmentFile) and returns the messages with a
tone and the command page each one opens. Routing used to live in each
client (g-command-mac routes.js, the iPhone app's copy of it): it lives here
now, so a sender that changes its titles is fixed in one place.

  GET /api/alerts?since=<cursor>   newest first, the last 12 hours without since
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core.auth import cookie_ok

router = APIRouter(tags=["alerts"])

WINDOW = "12h"
_CURSOR = re.compile(r"^[A-Za-z0-9]{1,32}$")

# What the spine's senders emit today: g-brain outlets/remind.py titles its
# pings "Reminder", "Vital reminder" and "Catching up (n)", brain_status.py
# titles them with the service id and tags them warning or rotating_light.
ROUTES = (
    ("title", re.compile(r"^(vital reminder|reminder|catching up)", re.I), "/calendar"),
    ("title", re.compile(r"ticket", re.I), "/tickets"),
    ("tags", re.compile(r"rotating_light|warning", re.I), "/system"),
)


def _topic_url():
    url = os.environ.get("NTFY_URL", "").strip().rstrip("/")
    return url if url.startswith("https://") else ""


def _poll(url, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def _link(msg, origin):
    click = msg.get("click") or ""
    if click.startswith("/"):
        return click
    if origin and click.startswith(origin + "/"):
        return click[len(origin):]
    fields = {"title": msg.get("title") or "", "tags": ",".join(msg.get("tags") or [])}
    for field, pattern, path in ROUTES:
        if pattern.search(fields[field]):
            return path
    return "/"


def _tone(msg):
    tags = set(msg.get("tags") or [])
    priority = msg.get("priority") or 3
    if "rotating_light" in tags or priority >= 5:
        return "danger"
    if "warning" in tags or priority == 4:
        return "warn"
    if msg.get("title", "").lower().startswith("vital"):
        return "accent"
    return "plain"


def parse(text, origin=""):
    alerts = []
    for line in text.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict) or msg.get("event") != "message" or not msg.get("id"):
            continue
        alerts.append({
            "id": str(msg["id"]),
            "time": int(msg.get("time") or 0),
            "title": str(msg.get("title") or "Alert"),
            "message": str(msg.get("message") or ""),
            "tone": _tone(msg),
            "link": _link(msg, origin),
        })
    alerts.sort(key=lambda a: a["time"], reverse=True)
    return alerts


@router.get("")
async def alerts(request: Request, since: str = ""):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")
    if since and not _CURSOR.match(since):
        raise HTTPException(400, "bad cursor")
    base = _topic_url()
    if not base:
        raise HTTPException(503, "alerts are not configured")
    url = f"{base}/json?" + urllib.parse.urlencode({"poll": "1", "since": since or WINDOW})
    try:
        text = await run_in_threadpool(_poll, url, os.environ.get("NTFY_TOKEN", ""))
    except (urllib.error.URLError, OSError):
        raise HTTPException(502, "alerts unreachable")
    host = os.environ.get("PUBLIC_HOST", "").strip().strip("/").removeprefix("https://")
    items = parse(text, f"https://{host}" if host else "")
    return {"v": 1, "alerts": items, "cursor": items[0]["id"] if items else since}
