"""calendar API — mounted at /api/calendar.

The calendar for machines that are not a browser: the Pi's TV dashboard
(gabetv on host gabepi) reads today and tomorrow from here. Same data as the
/calendar page, because it is the same feed: the brain's `/api/todos/calendar`,
recurrence already expanded there. This route holds no calendar logic of its
own for the same reason the page does not (see the gcommand CLAUDE.md): a
second copy of the rrule or overdue rules would drift from the reminders.

Fetched over localhost (127.0.0.1:8766, the brain API behind
api.brain.gabrielpenman.com), so it keeps working if that public vhost is
ever locked down.

Admin-gated inline — the page gate in server.py does not cover /api/*.
Two ways in: the admin cookie, or `X-Calendar-Token` matching CALENDAR_TOKEN
(the gcore passport). The token is read-only by construction: this router
has no write routes.
"""
import datetime
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["calendar"])

BRAIN_API = os.environ.get("BRAIN_API_URL", "http://127.0.0.1:8766")
ADMIN_COOKIE = os.environ.get("ADMIN_COOKIE", "seed_admin")
ADMIN_VALUE = os.environ.get("ADMIN_COOKIE_VALUE", "")
MAX_DAYS = 62  # a TV wants two days; the page's month view about six weeks


def _allowed(request: Request) -> bool:
    if ADMIN_VALUE and hmac.compare_digest(request.cookies.get(ADMIN_COOKIE, "").encode(), ADMIN_VALUE.encode()):
        return True
    expected = os.environ.get("CALENDAR_TOKEN")
    supplied = request.headers.get("x-calendar-token")
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


@router.get("/days")
def days(request: Request,
         date_from: datetime.date = Query(...),
         date_to: datetime.date = Query(...)):
    """Every todo occurrence from date_from to date_to inclusive, exactly as the
    brain returns it (date, time or all_day, vital, urgent, done, failed,
    late_days, ...)."""
    if not _allowed(request):
        raise HTTPException(401, "admin cookie or X-Calendar-Token required")
    if date_to < date_from or (date_to - date_from).days > MAX_DAYS:
        raise HTTPException(400, f"date_to must be within {MAX_DAYS} days after date_from")
    qs = urllib.parse.urlencode({"date_from": date_from.isoformat(), "date_to": date_to.isoformat()})
    try:
        with urllib.request.urlopen(f"{BRAIN_API}/api/todos/calendar?{qs}", timeout=10) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise HTTPException(502, f"brain API did not answer: {e}")
