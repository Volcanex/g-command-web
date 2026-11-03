"""The essentials: at most three plain lines, overdue first, then today,
bills of 50 pounds or more in the next seven days, then tomorrow.

The brain's `/api/todos/agenda` writes the lines. Until it answers, they are
worked out here from `/api/todos/calendar`, the feed the calendar page reads.
A failure is a line too ("Calendar unavailable: ..."), never a blank."""
import re
from datetime import date, timedelta

from core.panels import builder
from core.panels.helpers import WEEKDAYS, plain

AMOUNT = re.compile(r"£\s?(\d[\d,]*(?:\.\d+)?)")
BILL_MIN = 50
LIMIT = 3


def amount(item):
    if isinstance(item.get("amount"), (int, float)):
        return float(item["amount"])
    found = AMOUNT.search(str(item.get("title") or ""))
    return float(found.group(1).replace(",", "")) if found else None


def listing(items, limit=2):
    names = [plain(item.get("title")) for item in items]
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


def fallback(ctx):
    today = ctx.now.date()
    end = today + timedelta(days=7)
    data = ctx.get(f"/api/todos/calendar?date_from={today.isoformat()}&date_to={end.isoformat()}")
    items = [item for item in (data if isinstance(data, list) else [])
             if not item.get("done") and not item.get("failed") and not item.get("dropped")]
    finance = lambda item: item.get("category") in ("finance", "bill")
    # A daily habit is not a deadline; it would fill every line.
    counted = [item for item in items if finance(item) or item.get("vital") or not item.get("recurring")]
    on = lambda offset: (today + timedelta(days=offset)).isoformat()
    overdue = [item for item in counted if item.get("late_days")]
    todays = [item for item in counted if item.get("date") == on(0) and not item.get("late_days") and not finance(item)]
    tomorrow = [item for item in counted if item.get("date") == on(1) and not finance(item)]
    bills = sorted((item for item in counted if finance(item) and (amount(item) or 0) >= BILL_MIN),
                   key=lambda item: (item.get("date") or "", plain(item.get("title"))))
    lines = []
    if overdue:
        lines.append(f"Overdue: {listing(overdue)}")
    if todays:
        lines.append(f"Today: {listing(todays)}")
    if bills:
        def when(item):
            day = item.get("date") or ""
            if day == on(0):
                return "today"
            if day == on(1):
                return "tomorrow"
            return WEEKDAYS[date.fromisoformat(day).weekday()]
        lines.append("Bills: " + ", ".join(f"{plain(item.get('title'))} {when(item)}" for item in bills[:2])
                     + (f" and {len(bills) - 2} more" if len(bills) > 2 else ""))
    if tomorrow:
        lines.append(f"Tomorrow: {listing(tomorrow)}")
    return lines


def counts(data):
    """How many items the brain's agenda names: due today, overdue, and in the
    whole week its lines cover (today, overdue, tomorrow, the rest of the week
    less finance, which it names on the bills line instead, and those bills).
    Every count shown beside the calendar comes from here, so a head can never
    say "0 open today" while the agenda names something for today. None when
    the brain's agenda is not there to count."""
    if not isinstance(data, dict) or not isinstance(data.get("today"), list):
        return None
    named = lambda key: {item.get("slug") for item in data.get(key) or [] if isinstance(item, dict)}  # noqa: E731
    week = {item.get("slug") for item in data.get("week") or []
            if isinstance(item, dict) and str(item.get("category") or "").lower() != "finance"}
    return {"today": len(named("today")), "overdue": len(named("overdue")),
            "week": len(named("today") | named("overdue") | named("tomorrow") | week | named("bills"))}


def due_today(due):
    """The calendar head's count, in the agenda's words."""
    if not due:
        return ""
    if not due["today"] and not due["overdue"]:
        return "Nothing due today"
    return f"{due['today']} due today" + (f", {due['overdue']} overdue" if due["overdue"] else "")


def lines_for(ctx):
    try:
        data = ctx.get("/api/todos/agenda")
    except Exception:
        data = None
    if isinstance(data, dict) and isinstance(data.get("lines"), list):
        lines = [plain(line) for line in data["lines"]]
        return [line for line in lines if line][:LIMIT] or ["Nothing due this week."], "agenda", counts(data)
    try:
        lines = fallback(ctx)
    except Exception:
        return ["Calendar unavailable: the brain did not answer."], "error", None
    return lines[:LIMIT] or ["Nothing due this week."], "calendar", None


@builder("agenda")
def build(ctx):
    lines, source, due = lines_for(ctx)
    return {"meta": lines[0], "source": source, "due": due,
            "blocks": [{"type": "bullets", "items": [{"text": line} for line in lines]}]}
