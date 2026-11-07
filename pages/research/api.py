"""Research API, mounted at /api/research.

A renderer over research checkouts beside this one (core.instance.sibling): the
registry in areas.json names each area, the folder it reads and its sub-views.
Every file is read from disk on each request, nothing is copied in. The areas
include a private repo (ANS) and a folder with private raw data (the dissertation),
so every route checks the admin cookie inline (the page gate in server.py does not
cover /api/*), and every file goes through `_safe`, which keeps reads inside the
area, out of its `exclude` folders and away from its `deny` names.
"""
import csv
import importlib
import io
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.auth import cookie_ok
from core.instance import sibling

router = APIRouter()

REGISTRY = Path(__file__).with_name("areas.json")
MAX_TEXT = 2_000_000
MAX_ROWS = 200
MAX_COLS = 24
IMAGE_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp"}


def _auth(request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["areas"]


def _area(aid):
    area = next((a for a in registry() if a["id"] == aid), None)
    if area is None:
        raise HTTPException(404, "No research area by that name")
    return area


def _root_of(name):
    """The checkout an area reads. RESEARCH_<NAME>_DIR overrides, as GLEVELS_DIR does."""
    env = os.environ.get(f"RESEARCH_{re.sub(r'[^A-Z0-9]', '_', name.upper())}_DIR")
    return Path(env) if env else sibling(name)


def area_root(area):
    return (_root_of(area["root"]) / area.get("path", "")).resolve()


def _safe(area, rel):
    """The resolved path for `rel` inside the area, or None when it is outside,
    hidden, in an excluded folder or carries a denied name."""
    root = area_root(area)
    try:
        path = (root / rel).resolve()
        parts = path.relative_to(root).parts
    except (ValueError, OSError):
        return None
    if not parts or any(p.startswith(".") for p in parts):
        return None
    if any(p in area.get("exclude", []) for p in parts[:-1]):
        return None
    if any(d in parts[-1].lower() for d in area.get("deny", [])):
        return None
    return path


def _matches(area, globs, skip=()):
    """Files the globs find, safe ones only, deduplicated, in glob then name order."""
    root = area_root(area)
    if not root.is_dir():
        return []
    seen, out = set(), []
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            if rel in seen or path.name in skip or not path.is_file() or _safe(area, rel) is None:
                continue
            seen.add(rel)
            out.append((rel, path))
    return out


def _mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def _read(path):
    if path.stat().st_size > MAX_TEXT:
        raise HTTPException(413, "This file is too large to show here")
    return path.read_text(encoding="utf-8", errors="replace")


def _title(text, fallback):
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback.replace("-", " ").replace("_", " ").capitalize()


def _missing(area, what):
    root = area_root(area)
    return {"missing": True, "reason": what, "source": str(root)}


# ---------------------------------------------------------------- kinds

def view_paper(area, view, request):
    path = _safe(area, view["file"])
    if path is None or not path.is_file():
        return _missing(area, f"{view['file']} is not written yet")
    text = _read(path)
    return {"title": _title(text, path.stem), "markdown": text, "file": view["file"], "mtime": _mtime(path)}


def view_docs(area, view, request):
    found = _matches(area, view.get("globs", []), set(view.get("skip", [])))
    docs = []
    for rel, path in found:
        text = _read(path)
        docs.append({"id": rel, "title": _title(text, path.stem), "mtime": _mtime(path),
                     "words": len(text.split()), "_text": text})
    out = {"docs": [{k: v for k, v in d.items() if k != "_text"} for d in docs]}
    if view.get("bib"):
        bib = _safe(area, view["bib"])
        if bib is not None and bib.is_file():
            out["bib"] = {"file": view["bib"], "entries": len(re.findall(r"^\s*@\w+\s*\{", _read(bib), re.M))}
    if not docs:
        return {**out, **_missing(area, "No documents here yet")}
    want = request.query_params.get("doc")
    doc = next((d for d in docs if d["id"] == want), docs[0])
    out["doc"] = {"id": doc["id"], "title": doc["title"], "mtime": doc["mtime"], "markdown": doc["_text"]}
    return out


def view_tables(area, view, request):
    tables = []
    for rel, path in _matches(area, view.get("globs", [])):
        text = _read(path)
        dialect = "excel-tab" if path.suffix == ".tsv" else "excel"
        rows = list(csv.reader(io.StringIO(text), dialect=dialect))
        if not rows:
            continue
        head, body = rows[0][:MAX_COLS], [r[:MAX_COLS] for r in rows[1:] if any(c.strip() for c in r)]
        tables.append({"id": rel, "title": path.stem.replace("-", " ").replace("_", " ").capitalize(),
                       "mtime": _mtime(path), "columns": head, "rows": body[:MAX_ROWS], "total": len(body)})
    if not tables:
        return {"tables": [], **_missing(area, "No tables yet")}
    return {"tables": tables}


def view_charts(area, view, request):
    charts = [{"id": rel, "title": path.stem.replace("-", " ").replace("_", " ").capitalize(), "mtime": _mtime(path),
               "url": f"/api/research/{area['id']}/file?path={rel}"}
              for rel, path in _matches(area, view.get("globs", [])) if path.suffix.lower() in IMAGE_TYPES]
    if not charts:
        return {"charts": [], **_missing(area, "No charts yet")}
    return {"charts": charts}


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)


def view_ans_runs(area, view, request):
    """Aggregates only: one row per run and per sweep. Items, prompts and trajectories stay on disk."""
    db = _safe(area, view["db"])
    if db is None or not db.is_file():
        return _missing(area, "No run database yet")
    con = _ro(db)
    try:
        con.row_factory = sqlite3.Row
        runs = []
        for r in con.execute(
            "SELECT r.run_id, r.suite, r.status, r.n_items, r.seed, r.started_at, r.finished_at, c.config_json,"
            " (SELECT COUNT(*) FROM items i WHERE i.run_id = r.run_id) AS done,"
            " (SELECT COALESCE(SUM(passed), 0) FROM items i WHERE i.run_id = r.run_id) AS passed,"
            " m.gen_tps, m.peak_rss_mb, m.load_s"
            " FROM runs r JOIN configs c USING (config_id) LEFT JOIN run_metrics m USING (run_id)"
            " ORDER BY r.started_at"):
            cfg = json.loads(r["config_json"] or "{}")
            runs.append({"run": r["run_id"], "suite": r["suite"], "status": r["status"], "n": r["n_items"],
                         "done": r["done"], "passed": r["passed"], "seed": r["seed"], "started": r["started_at"],
                         "finished": r["finished_at"], "model": cfg.get("model"), "harness": cfg.get("harness"),
                         "weights": cfg.get("weights"), "ctx": cfg.get("ctx_size"), "steps": cfg.get("step_limit"),
                         "gen_tps": r["gen_tps"], "peak_mb": r["peak_rss_mb"]})
        sweeps = [{"sweep": s["sweep_id"], "status": s["status"], "started": s["started_at"],
                   "finished": s["finished_at"], "runs": s["n"]}
                  for s in con.execute("SELECT s.sweep_id, s.status, s.started_at, s.finished_at,"
                                       " (SELECT COUNT(*) FROM sweep_runs w WHERE w.sweep_id = s.sweep_id) AS n"
                                       " FROM sweeps s ORDER BY s.started_at")]
    except sqlite3.Error:
        return _missing(area, "The run database could not be read")
    finally:
        con.close()
    return {"runs": runs, "sweeps": sweeps, "mtime": _mtime(db), "file": view["db"]}


def view_ans_atlas(area, view, request):
    """The observed atlas bundles that scripts/build_atlas.py wrote. Synthetic demo data is left out."""
    folder = _safe(area, view["dir"])
    manifest = folder / "manifest.json" if folder else None
    if manifest is None or not manifest.is_file():
        return _missing(area, "The atlas has not been built yet")
    datasets = []
    for d in json.loads(_read(manifest)).get("datasets", []):
        if d.get("kind") != "observed":
            continue
        path = _safe(area, f"{view['dir']}/{d.get('bundle', '')}")
        if path is None or not path.is_file():
            continue
        b = json.loads(_read(path))
        cfgs = {c["config_id"]: c for c in b.get("configs", [])}
        meta = b.get("meta", {})
        rates = []
        for p in b.get("pass_rates", []):
            c = cfgs.get(p["config_id"], {})
            rates.append({"model": c.get("model"), "harness": c.get("harness"), "weights": c.get("weights"),
                          "n": p.get("n"), "successes": p.get("successes"), "rate": p.get("pass_rate"),
                          "low": p.get("ci_low"), "high": p.get("ci_high"), "wall_s": p.get("wall_s"),
                          "mem_gb": p.get("peak_mem_gb")})
        datasets.append({"id": d.get("id"), "label": d.get("label"), "suite": meta.get("suite", d.get("suite")),
                         "host": meta.get("host", d.get("host")), "generated": meta.get("generated_at"),
                         "n_items": meta.get("n_items"), "n_configs": meta.get("n_configs"),
                         "n_tasks": meta.get("n_tasks"), "varying": meta.get("varying", []), "rates": rates,
                         "sensitivity": b.get("sensitivity", []), "caveat": b.get("sensitivity_caveat"),
                         "dividend": b.get("dividend", [])})
    if not datasets:
        return {"datasets": [], **_missing(area, "No observed datasets in the atlas yet")}
    return {"datasets": datasets, "mtime": _mtime(manifest)}


# ---------------------------------------------------------------- claims

def _glevels():
    path = str(Path(os.environ.get("GLEVELS_DIR") or sibling("g-levels")))
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("glevels.export")


def claims_from(text, section):
    """The status paragraphs (**Established:** ...) under the heading naming `section`, one claim per sentence."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and section.lower() in l.lower()), None)
    if start is None:
        return []
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    claims = []
    for para in "\n".join(body).split("\n\n"):
        m = re.match(r"\s*\*\*([^*:]+):?\*\*:?\s*(.*)", para, re.S)
        if not m:
            continue
        status = m.group(1).strip().rstrip(":")
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(m.group(2).split())):
            if sentence:
                claims.append({"status": status, "text": sentence})
    return claims


def _evidence(key, reg, res, view):
    then = view.get("then", {})
    gates, links, charters = reg["gates"], [l for l in reg["links"] if not l.get("waiver_only")], reg["charters"]
    by_gate = {g["gate"]: g for g in res["gates"]}
    t = res.get("totals", {})
    if key == "registry":
        design = sum(g["kind"] == "design" for g in gates)
        return {"label": "Registry now", "value": f"{len(gates)} gates, {len(charters)} charters",
                "detail": f"{design} of the gates are design gates. The paper counted {then.get('gates')} gates and "
                          f"{then.get('charters')} charters on {then.get('date')}."}
    if key == "hooks":
        hooks = [g for g in gates if g["sensor"] == "hook"]
        loud = sum(by_gate.get(g["id"], {}).get("counts", {}).get("impossible", 0) for g in hooks)
        return {"label": "Hook gates", "value": f"{len(hooks)} registered",
                "detail": f"{', '.join(g['id'] for g in hooks) or 'None'}. They log only when they break: "
                          f"{loud} impossible results so far."}
    if key in ("sensors", "review"):
        counts = {}
        for g in gates:
            counts[g["sensor"] or "none"] = counts.get(g["sensor"] or "none", 0) + 1
        if key == "review":
            return {"label": "Judged gates", "value": f"{counts.get('review', 0)} of {len(gates)}",
                    "detail": "Gates whose sensor is a review. Each needs examples it must pass, the claim says."}
        return {"label": "Sensors", "value": ", ".join(f"{n} {k}" for k, n in sorted(counts.items(), key=lambda x: -x[1])),
                "detail": "Every gate pairs guidance (its skill) with a sensor of one of these kinds."}
    if key == "blocking":
        block = sum(l["blocking"] for l in links)
        return {"label": "Blocking pins", "value": f"{block} of {len(links)}",
                "detail": f"Pins that block, across {sum(any(l['blocking'] and l['charter'] == c['id'] for l in links) for c in charters)} charters. The rest are recorded."}
    if key == "results":
        return {"label": "Results logged", "value": ", ".join(f"{t.get(k, 0)} {k}" for k in ("met", "attempted", "waived", "impossible")),
                "detail": f"{t.get('caught', 0)} caught along the way, {res.get('rows', 0)} rows in the log."}
    if key == "silent":
        silent = [g["gate"] for g in res["gates"] if g["silent"]]
        return {"label": "Silent gates", "value": f"{len(silent)} of {len(gates)}",
                "detail": "Pinned, meant to fire every run, and nothing in the log. Silence is the failure."}
    if key == "charters":
        return {"label": "Charters", "value": f"{len(charters)}",
                "detail": "Counts go up to each charter from the gates it pins. Notes stay at the gate."}
    if key == "design":
        design = [g for g in gates if g["kind"] == "design"]
        ran = [g for g in design if by_gate.get(g["id"], {}).get("total")]
        return {"label": "Design gates", "value": f"{len(design)} registered, {len(ran)} with results",
                "detail": ", ".join(g["id"] for g in design) or "None registered."}
    if key == "domain":
        dom = [g for g in gates if g["domain"] == view.get("domain")]
        pinned = {l["gate"] for l in links}
        return {"label": f"Gates on {view.get('domain')}", "value": f"{len(dom)} registered, {sum(g['id'] in pinned for g in dom)} pinned",
                "detail": "Gates whose domain is research, listed below with what they have logged."}
    return None


def view_claims(area, view, request):
    path = _safe(area, view["file"])
    if path is None or not path.is_file():
        return _missing(area, f"{view['file']} is not written yet")
    claims = claims_from(_read(path), view.get("section", "claims"))
    try:
        export = _glevels()
        reg = export.registry_view()
        res = export.results_view(reg)
    except Exception as exc:  # the paper still reads without g-levels
        return {"claims": claims, "live": None, "domain": [],
                "levels_error": f"g-levels could not be read ({type(exc).__name__}), so the live side is missing."}
    then = view.get("then", {})
    cache = {}
    for c in claims:
        keys = []
        for link in view.get("links", []):
            if link["match"].lower() in c["text"].lower():
                keys += [k for k in link["evidence"] if k not in keys]
        c["evidence"] = [cache.setdefault(k, _evidence(k, reg, res, view)) for k in keys]
        c["evidence"] = [e for e in c["evidence"] if e]
    by_gate = {g["gate"]: g for g in res["gates"]}
    pinned = {l["gate"] for l in reg["links"] if not l.get("waiver_only")}
    domain = [{"id": g["id"], "kind": g["kind"], "principle": g["principle"], "pinned": g["id"] in pinned,
               "counts": by_gate.get(g["id"], {}).get("counts", {}), "last": by_gate.get(g["id"], {}).get("last")}
              for g in reg["gates"] if g["domain"] == view.get("domain")]
    live = {"gates": len(reg["gates"]), "charters": len(reg["charters"]),
            "design": sum(g["kind"] == "design" for g in reg["gates"]),
            "silent": sum(g["silent"] for g in res["gates"]), "rows": res.get("rows", 0), "totals": res.get("totals", {})}
    return {"claims": claims, "live": live, "then": then, "domain": domain, "domain_name": view.get("domain"),
            "mtime": _mtime(path)}


KINDS = {"paper": view_paper, "docs": view_docs, "tables": view_tables, "charts": view_charts,
         "ans-runs": view_ans_runs, "ans-atlas": view_ans_atlas, "claims": view_claims}


# ---------------------------------------------------------------- routes

@router.get("")
def areas(request: Request):
    _auth(request)
    return {"areas": [{"id": a["id"], "title": a["title"], "sub": a.get("sub", ""),
                       "views": [{"id": v["id"], "title": v["title"], "kind": v["kind"]} for v in a["views"]]}
                      for a in registry()]}


@router.get("/{aid}/file")
def file(aid: str, path: str, request: Request):
    """A chart image, only when the area's charts view lists it."""
    _auth(request)
    area = _area(aid)
    listed = {rel for v in area["views"] if v["kind"] == "charts" for rel, _ in _matches(area, v.get("globs", []))}
    found = _safe(area, path) if path in listed else None
    if found is None or found.suffix.lower() not in IMAGE_TYPES:
        raise HTTPException(404, "No chart at that path")
    return FileResponse(found, media_type=IMAGE_TYPES[found.suffix.lower()], headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache"})


@router.get("/{aid}/{vid}")
def view(aid: str, vid: str, request: Request):
    _auth(request)
    area = _area(aid)
    v = next((v for v in area["views"] if v["id"] == vid), None)
    if v is None or v["kind"] not in KINDS:
        raise HTTPException(404, "No view by that name in this area")
    root = area_root(area)
    head = {"area": area["id"], "view": v["id"], "kind": v["kind"], "source": str(root)}
    if not root.is_dir():
        return {**head, **_missing(area, "The folder is not there yet")}
    return {**head, **KINDS[v["kind"]](area, v, request)}
