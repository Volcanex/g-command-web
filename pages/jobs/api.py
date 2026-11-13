"""Read g-jobs through its existing archive readers, behind Command's gate."""
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from core.auth import cookie_ok

router = APIRouter(tags=["jobs"])

# Use the Jobs service's interpreter and checkout. Its readers hold the joins,
# outcome labels and pacing rules; none of them change the archive.
_READER = """
import datetime, json, sys
from gjobs.site import data as D
view = sys.argv[1]
if view == 'cv':
    result = D.pdf_path(sys.argv[2])
else:
    state = D.state()
    result = {
        'summary': state,
        'read_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if view == 'roster':
        result['items'] = D.tap_roster()
    elif view == 'applications':
        result['items'] = D.applications()
        result['groups'] = [
            {'status': status, 'label': label, 'tone': tone, 'gloss': gloss,
             'items': rows}
            for status, label, tone, gloss, rows in D.by_status(result['items'])
        ]
    elif view == 'letters':
        result['items'] = D.letters()
    elif view == 'questions':
        result['items'] = D.questions()
    elif view == 'runs':
        result['items'] = D.runs()
        result['budget'] = D.budget_state()
    elif view == 'interviews':
        from gjobs import interviews
        result.update(interviews.view())
print(json.dumps(result, default=str))
"""


def _root():
    return Path(os.environ.get("GJOBS_DIR") or Path(__file__).resolve().parents[3] / "g-jobs")


def _read(view, stem=""):
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "-c", _READER, view, stem],
            cwd=_root(), capture_output=True, text=True, timeout=20, check=True,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise HTTPException(502, "Jobs records could not be read. Try again.") from None


def _require_admin(request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "admin only")


@router.get("")
def index(request: Request, view: str = "roster"):
    _require_admin(request)
    if view not in {"interviews", "roster", "applications", "letters", "questions", "runs"}:
        raise HTTPException(400, "unknown Jobs view")
    return _read(view)


@router.get("/cv/{stem}.pdf")
def cv(stem: str, request: Request):
    _require_admin(request)
    path = _read("cv", stem)
    if not path:
        raise HTTPException(404, "No archived CV matches this record.")
    resolved = Path(path).resolve()
    if resolved.parent != (_root() / "out/variants").resolve() or not resolved.is_file():
        raise HTTPException(404, "No archived CV matches this record.")
    return FileResponse(resolved, media_type="application/pdf", filename=resolved.name)


# The one write: an interview's status, next step or a note. It goes through
# `gjobs interview set`, so the log line is the one the CLI would write, and is
# committed so the change has a history; gsync pushes it. Both run as gabriel,
# who owns the checkout, so no root-owned file or git object is left behind.
_FIELDS = {"status": "--status", "next": "--next", "salary": "--salary", "note": "--note"}


@router.post("/interviews/{key}")
async def change_interview(key: str, request: Request):
    _require_admin(request)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", key):
        raise HTTPException(404, "No interview has that id.")
    origin = request.headers.get("Origin")
    if origin is not None and urlsplit(origin).netloc.lower() != request.headers.get("Host", "").lower():
        raise HTTPException(403, "cross-origin write")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Send the change as JSON.") from None
    # An empty next step clears it; every other empty field is left alone.
    given = {k: body[k].strip()[:600] for k in _FIELDS
             if isinstance(body, dict) and isinstance(body.get(k), str) and (body[k].strip() or k == "next")}
    if not given:
        raise HTTPException(400, "Nothing to change.")
    args = ["runuser", "-u", "gabriel", "--", "/usr/bin/python3", "-m", "gjobs.cli", "interview", "set", key]
    args += [f"{_FIELDS[k]}={v}" for k, v in given.items()]
    return await run_in_threadpool(_change, key, args)


def _change(key, args):
    try:
        done = subprocess.run(args, cwd=_root(), capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        raise HTTPException(502, "Jobs did not answer, so nothing changed. Try again.") from None
    if done.returncode:
        why = done.stderr.strip().splitlines()[-1] if done.stderr.strip() else "no reason given"
        raise HTTPException(400, f"Jobs refused the change: {why}")
    subprocess.run(["runuser", "-u", "gabriel", "--", "git", "commit", "-q", "-m",
                    f"Record an interview change for {key}", "--", "data/interviews.yaml"],
                   cwd=_root(), capture_output=True, timeout=20)
    return _read("interviews")
