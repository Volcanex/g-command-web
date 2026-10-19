from datetime import datetime

from core.panels import builder
from core.panels.helpers import TZ, chip, plain


@builder("crons")
def build(ctx):
    data = ctx.get("/api/crons/list")
    jobs = data.get("jobs") or []
    problems = data.get("problems") or []
    down = [host for host in data.get("hosts") or [] if host.get("status") != "ok"]
    blocks = []
    if problems or down:
        rows = [{"id": "host:" + str(host["id"]), "title": plain(host["id"]),
                 "lead": chip("Host", "danger", True), "detail": "Unreachable"} for host in down]
        rows.extend({"id": str(problem["host"]) + ":" + str(problem["name"]),
                     "title": plain(problem["name"]), "detail": plain(problem.get("problem")),
                     "lead": chip(problem["host"], "danger" if "fail" in str(problem.get("problem") or "") else "warn", True)} for problem in problems)
        blocks.append({"type": "rows", "title": f"Problems {len(rows)}", "rows": rows})
    else:
        blocks.append({"type": "line", "items": [chip(f"All {len(jobs)} jobs ok", "ok", True)]})
    soon = sorted((job for job in jobs if job.get("next")), key=lambda job: job["next"])[:12]
    if soon:
        rows = [{"id": str(job.get("host") or "") + ":" + str(job.get("id") or job.get("name") or ""),
                 "title": plain(job.get("name")), "detail": plain(job.get("host")),
                 "trail": chip(datetime.fromtimestamp(job["next"], TZ).strftime("%H:%M"), "muted")} for job in soon]
        blocks.append({"type": "rows", "title": "Next", "rows": rows})
    return {"meta": f"{len(jobs)} jobs" + (", stale" if data.get("stale") else ""), "blocks": blocks}
