from core.panels import builder
from core.panels.helpers import day, plain


@builder("brief")
def build(ctx):
    data = ctx.get("/api/pulse/brief") or {}
    meta = day(data["date"]) if data.get("date") else ""
    bullets = []
    asks = 0
    for line in str(data.get("body") or "").split("\n"):
        if line.startswith("## "):
            break
        if not line.strip() or line.startswith("#"):
            continue
        line = plain(line[2:] if line.startswith("- ") else line).strip()
        if line.startswith("Services:"):
            continue
        if line.startswith("Promote to brain?"):
            asks += 1
            continue
        cut = line.find(":")
        if 0 < cut < 40:
            bullets.append({"label": line[:cut], "text": line[cut + 1:].strip()})
        else:
            bullets.append({"text": line})
    if not bullets:
        return {"meta": meta, "state": "empty", "message": "No brief yet today."}
    if asks:
        count = "1 note" if asks == 1 else f"{asks} notes"
        bullets.append({"text": count + " waiting to go into the brain", "link": "/pulse"})
    return {"meta": meta, "blocks": [{"type": "bullets", "items": bullets}]}
