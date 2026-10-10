#!/usr/bin/env python3
"""Autonomic project-gallery refresh: screenshots + git metadata.

Driven by the gcommand-projects.timer (6-hourly + on boot), run as root
(Chromium lives in /root/.cache/ms-playwright and g-command-web itself runs as
root). The project list is derived from the instance manifest, so a new manifest
entry needs no code change here.

Writes atomically into g-command-web/var/, a sibling of output/, which compile.py
wipes on every restart, so these survive a recompile and update live without a
restart of the gcommand unit:
  - var/shots/<id>.png        one above-the-fold thumbnail per reachable site
  - var/projects-meta.json    {generated_at, projects:{<id>:{shot,depends,last_commit}}}

Best-effort: one project failing (unreachable, auth-gated, render error,
non-repo dir) is logged and never aborts the batch.

Run by hand:  /usr/bin/python3 scripts/refresh_projects.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover (py<3.11)
    tomllib = None

GCOMMAND = Path(__file__).resolve().parent.parent
# Manifest repos are named relative to the directory this checkout sits in,
# and the instance is a checkout there too. Same lookup as core/instance.py,
# copied because the timer runs this file without the app on sys.path.
HOME = GCOMMAND.parent
MANIFEST = Path(os.environ.get("GCORE_DIR")
                or next((HOME / n for n in ("gp-core", "gcore") if (HOME / n).is_dir()),
                        HOME / "gp-core")) / "manifest.json"
VAR = GCOMMAND / "var"
SHOTS = VAR / "shots"
META = VAR / "projects-meta.json"

VIEWPORT = {"width": 1280, "height": 800}
NAV_TIMEOUT_MS = 20000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Don't follow redirects: an auth gate (302 → /login) must read as
    unreachable, not as a 200 login page we'd screenshot."""

    def redirect_request(self, *a, **k):
        return None


def reachable(url):
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        r = opener.open(
            urllib.request.Request(url, method="GET", headers={"User-Agent": "gcommand-shot/1"}),
            timeout=10,
        )
        ctype = (r.headers.get("Content-Type") or "").lower()
        # 2xx + HTML only: an app-level login gate (302 → /login) trips the
        # no-redirect handler, and JSON/health APIs are filtered out so we
        # never screenshot a raw payload.
        return 200 <= r.status < 300 and "html" in ctype
    except Exception:
        # HTTPError (302/401/403/…), timeout, DNS, TLS: all "don't shoot".
        return False


def git_meta(repo):
    d = HOME / repo
    if not (d / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(d), "log", "-1", "--format=%h%x1f%cs%x1f%s"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        h, date, subject = out.stdout.strip().split("\x1f", 2)
        return {"hash": h, "date": date, "subject": subject}
    except Exception:
        return None


def depends(repo):
    if tomllib is None:
        return []
    f = HOME / repo / "pyproject.toml"
    if not f.is_file():
        return []
    try:
        data = tomllib.loads(f.read_text())
        return list((data.get("tool", {}).get("g-core") or data.get("tool", {}).get("gcore", {})).get("depends", []) or [])
    except Exception:
        return []


def screenshot(url, dest, pw):
    browser = pw.chromium.launch()
    try:
        page = browser.new_page(viewport=VIEWPORT)
        # "load" not "networkidle": analytics / long-poll sites never go idle
        # (one live site timed out on networkidle). A short settle lets
        # above-the-fold content paint.
        page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(1200)
        tmp = dest.with_suffix(".tmp.jpg")
        # JPEG, not PNG: thumbnails are decorative and /api/* is no-store, so
        # they re-download every page load: a photo-heavy PNG ran to ~2 MB.
        page.screenshot(path=str(tmp), type="jpeg", quality=72)  # above-the-fold
        os.replace(tmp, dest)
        return True
    finally:
        browser.close()


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text())
    projects = manifest.get("projects", [])
    svc_by_repo = {}
    for s in manifest.get("services", []):
        svc_by_repo.setdefault(s.get("repo"), []).append(s)

    from playwright.sync_api import sync_playwright

    out = {}
    with sync_playwright() as pw:
        for p in projects:
            pid = p.get("id")
            if not pid:
                continue
            entry = {"shot": False, "depends": depends(pid), "last_commit": git_meta(pid)}
            svcs = svc_by_repo.get(pid, [])
            domain = next((s.get("domain") for s in svcs if s.get("domain")), None)
            port = next((s.get("port") for s in svcs if s.get("port")), None)
            # Prefer the public domain (best fidelity); fall back to the internal
            # port, which bypasses nginx basic-auth since this job runs on the
            # host. App-level login gates (302 → /login) fail the no-redirect
            # reachability check and correctly fall through to a placeholder.
            candidates = []
            if domain:
                candidates.append(f"https://{domain}")
            if port:
                candidates.append(f"http://127.0.0.1:{port}")
            for url in candidates:
                if not reachable(url):
                    continue
                try:
                    entry["shot"] = screenshot(url, SHOTS / f"{pid}.jpg", pw)
                    print(f"  shot {pid:<24} {url}")
                    break
                except Exception as e:
                    print(f"  FAIL {pid:<24} {url}  {e}", file=sys.stderr)
            if not entry["shot"]:
                why = "no domain/port" if not candidates else "unreachable / auth-gated"
                print(f"  skip {pid:<24} ({why})")
            out[pid] = entry

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "projects": out}
    tmp = META.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, META)
    shot_count = sum(1 for e in out.values() if e["shot"])
    print(f"wrote {META} ({len(out)} projects, {shot_count} thumbnails)")


if __name__ == "__main__":
    main()
