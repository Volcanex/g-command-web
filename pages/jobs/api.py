"""Read g-jobs through its existing archive readers, behind Command's gate."""
import json
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

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
    if view not in {"roster", "applications", "letters", "questions", "runs"}:
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
