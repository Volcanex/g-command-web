from core.panels import builder
from core.panels.helpers import chip, encoded, plain, rel


@builder("tickets")
def build(ctx):
    data = ctx.get("/api/gadmin_panel/tickets?status=open") or {}
    items = data.get("tickets") or []
    down = data.get("degraded") or []
    blocks = []
    if items:
        rows = []
        for item in items:
            page = item.get("page") or {}
            text = item.get("note") or page.get("title") or page.get("path") or item.get("scope") or ""
            severity = str(item.get("severity") or "open")
            age = rel(item.get("created_at"), ctx.now)
            project = plain(item["project"])
            rows.append({"id": str(item["project"]) + ":" + str(item["id"]), "title": plain(text),
                         "lead": chip(severity[:1].upper() + severity[1:], {"blocker": "danger", "major": "warn"}.get(severity, "plain"), True),
                         "detail": project, "trail": chip(age, "muted"),
                         "link": "/tickets?project=" + encoded(item["project"]) + "&id=" + encoded(item["id"])})
        blocks.append({"type": "rows", "rows": rows})
    elif not down:
        return {"meta": "0 open", "state": "empty", "message": "No open tickets."}
    else:
        blocks.append({"type": "rows", "empty": "No open tickets.", "rows": []})
    if down:
        count = "1 project" if len(down) == 1 else f"{len(down)} projects"
        blocks.append({"type": "line", "items": [chip(count + " did not answer", "muted")]})
    return {"meta": f"{len(items)} open", "blocks": blocks}
