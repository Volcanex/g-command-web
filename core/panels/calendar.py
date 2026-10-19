from datetime import timedelta

from core.panels import builder
from core.panels.helpers import chip, day, encoded, note, plain, row_id, sort_text


CAT_TONES = {
    "study": "accent", "deadline": "accent", "finance": "accent", "bill": "accent",
    "family": "ok", "social": "ok", "health": "warn", "chore": "warn",
    "work": "danger", "travel": "ok", "errand": "ok", "personal": "ok",
}


def chronological(item):
    return not bool(item.get("time")), item.get("time") or "", sort_text(item.get("title"))


def triage(item):
    return (not bool(item.get("urgent")), not bool(item.get("vital")),
            not bool(item.get("late_days")), *chronological(item))


def row(item, today):
    done = bool(item.get("done"))
    routine = item.get("recurring") and not item.get("vital") and not item.get("urgent")
    title_tone = "muted" if routine else "ok" if done else "danger" if today and item.get("failed") else "plain"
    result = {"id": row_id(item) + ":" + item["date"], "title": plain(item.get("title")),
              "link": note(item), "done": done,
              "struck": done or (today and bool(item.get("failed"))),
              "accent": CAT_TONES.get(item.get("category"), "muted"), "title_tone": title_tone}
    if item.get("time"):
        result["lead"] = chip(item["time"], "muted")
    if item.get("vital"):
        result["marks"] = [chip("!", "danger", tip="Vital")]
    if today and item.get("late_days"):
        days = item["late_days"]
        result["trail"] = chip("1 day late" if days == 1 else f"{days} days late", "warn")
    if today:
        if item.get("recurring"):
            body = {"undone_date": item["date"], "unfailed_date": item["date"]} if done else {"done_date": item["date"]}
        else:
            body = {"status": "open" if done else "done"}
        result["action"] = {"label": "Mark not done" if done else "Mark done", "method": "PATCH",
                            "path": "/api/brain/api/todos/" + encoded(item["slug"]), "body": body,
                            "error": {"title": "Not saved", "desc": "The brain did not accept the change. Try again from the calendar."}}
    return result


@builder("calendar")
def build(ctx):
    today = ctx.now.date()
    end = today + timedelta(days=6)
    data = ctx.get(f"/api/todos/calendar?date_from={today.isoformat()}&date_to={end.isoformat()}")
    items = data if isinstance(data, list) else []
    todays = [item for item in items if item.get("date") == today.isoformat() and not item.get("dropped")]
    own = sorted((item for item in todays if not item.get("late_days")), key=chronological)
    carried = sorted((item for item in todays if item.get("late_days")), key=triage)
    opened = sum(not item.get("done") and not item.get("failed") for item in todays)
    carried_open = sum(not item.get("done") for item in carried)
    blocks = []
    if not todays:
        blocks.append({"type": "rows", "title": "Today", "empty": "Nothing on today.", "rows": []})
    for label, group in (("Today", own), ("Carried over", carried)):
        if group:
            blocks.append({"type": "rows", "title": f"{label} {len(group)}",
                           "rows": [row(item, True) for item in group]})
    for offset in range(1, 7):
        date = (today + timedelta(days=offset)).isoformat()
        group = sorted((item for item in items if item.get("date") == date and not item.get("dropped")), key=chronological)
        blocks.append({"type": "rows", "title": day(date), "empty": "Nothing planned",
                       "rows": [row(item, False) for item in group]})
    return {"title": "Today, " + day(today.isoformat()),
            "meta": f"{opened} open today, {carried_open} carried over", "blocks": blocks}
