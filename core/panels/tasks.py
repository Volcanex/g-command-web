from core.panels import builder
from core.panels.helpers import chip, note, plain, row_id


PRIORITY_TONES = {"P0": "danger", "P1": "warn", "P2": "accent", "P3": "muted"}


@builder("tasks")
def build(ctx):
    data = ctx.get("/api/todos?status=open")
    todos = [item for item in (data if isinstance(data, list) else [])
             if not item.get("due") and not item.get("start") and item.get("category") not in ("finance", "bill")]
    meta = f"{len(todos)} undated"
    if not todos:
        return {"meta": meta, "state": "empty", "message": "No undated tasks."}
    blocks = []
    priorities = ("P0", "P1", "P2", "P3")
    for priority in priorities:
        items = [item for item in todos if (item.get("priority") if item.get("priority") in priorities else "P3") == priority]
        if not items:
            continue
        rows = []
        for item in items:
            row = {"id": row_id(item), "title": plain(item.get("title") or item.get("slug")),
                   "link": note(item), "accent": PRIORITY_TONES[priority]}
            if item.get("vital"):
                row["marks"] = [chip("Vital", "danger")]
            rows.append(row)
        blocks.append({"type": "rows", "title": f"{priority} {len(items)}", "rows": rows})
    return {"meta": meta, "blocks": blocks}
