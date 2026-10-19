from datetime import date

from core.panels import builder
from core.panels.helpers import chip, day, note, plain, row_id, sort_text


@builder("money")
def build(ctx):
    data = ctx.get("/api/todos?status=open")
    today = ctx.now.date().isoformat()
    items = [item for item in (data if isinstance(data, list) else []) if item.get("category") in ("finance", "bill")]
    items.sort(key=lambda item: (not bool(item.get("due")), item.get("due") or "",
                                 sort_text(item.get("priority")), sort_text(item.get("title"))))
    late = sum(bool(item.get("due") and item["due"] < today) for item in items)
    meta = f"{len(items)} open" + (f", {late} late" if late else "")
    if not items:
        return {"meta": meta, "state": "empty", "message": "Nothing owed or to sort."}
    rows = []
    for item in items:
        row = {"id": row_id(item), "title": plain(item.get("title")), "link": note(item)}
        due = item.get("due")
        if due and due < today:
            days = (date.fromisoformat(today) - date.fromisoformat(due)).days
            row["trail"] = chip("1 day late" if days == 1 else f"{days} days late", "danger")
        elif due == today:
            row["trail"] = chip("Today", "warn")
        elif due:
            row["trail"] = chip(day(due), "muted")
        rows.append(row)
    return {"meta": meta, "blocks": [{"type": "rows", "rows": rows}]}
