from core.panels import builder
from core.panels.helpers import chip, plain, rel, rounded


@builder("health")
def build(ctx):
    data = ctx.get("/api/status")
    rank = {"down": 0, "warn": 1}
    bad = []
    hosts = {}
    for kind, where in (("services", "host"), ("dependencies", "criticality")):
        for item in data.get(kind) or []:
            if item.get("state") in rank:
                bad.append((kind, where, item))
            if kind == "services" and item.get("state") != "paused":
                host = hosts.setdefault(item.get("host") or "undefined", [0, 0])
                host[0] += item.get("state") == "up"
                host[1] += 1
    bad.sort(key=lambda entry: rank[entry[2]["state"]])
    summary = data.get("summary") or {}
    up = summary.get("up") or 0
    paused = summary.get("paused") or 0
    blocks = []
    if bad:
        rows = []
        for kind, where, item in bad:
            state = item["state"]
            rows.append({"id": kind + ":" + str(item["id"]), "title": plain(item["id"]),
                         "detail": plain(item.get("detail") or item.get(where) or ""),
                         "lead": chip("Down" if state == "down" else "Warn", "danger" if state == "down" else "warn", True)})
        blocks.append({"type": "rows", "rows": rows})
        facts = [chip(f"{up} of {(summary.get('total') or 0) - paused} up", "muted")]
    else:
        facts = [chip(f"All {up} services up", "ok", True)]
    if paused:
        facts.append(chip(f"{paused} paused", "muted"))
    facts.extend(chip(f"{host} {hosts[host][0]}/{hosts[host][1]}", "muted") for host in sorted(hosts))
    blocks.append({"type": "line", "items": facts})
    disk = data.get("disk")
    if disk and disk.get("used_pct") is not None:
        used = rounded(disk["used_pct"])
        blocks.append({"type": "meter", "label": "Disk", "value": used, "max": 100,
                       "warn_at": 85, "danger_at": 95,
                       "text": f"{used}% used, {rounded(disk['free_gb'])} GB free"})
    return {"meta": "Checked " + rel(data["checked_at"], ctx.now) if data.get("checked_at") else "", "blocks": blocks}
