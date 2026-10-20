"""Levels page API, mounted at /api/levels.

A renderer over the g-levels checkout beside this one (core.instance.sibling,
GLEVELS_DIR to override). Every read goes through `glevels.export`, which reads the
registry, the results log, the backlog and the level summary fresh on each request.
The backlog quotes Gabriel's own prompts, so nothing here is public: all
routes check the admin cookie inline, because the page gate in server.py does not
cover /api/*.

Grading never writes the log from here. It runs `glevels grade <id> agree|disagree`,
the same command Gabriel would type, so the CLI stays the one writer.
"""
import importlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import cookie_ok
from core.instance import gcore_dir, sibling

router = APIRouter()
log = logging.getLogger(__name__)

_ID = re.compile(r"^[0-9a-f]{8}$")
_PROJECT = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")  # the manifest id pattern pages/projects/api.py checks
_RUNNER = "import sys\nfrom glevels.cli import main\nsys.exit(main())"


def _dir():
    return Path(os.environ.get("GLEVELS_DIR") or sibling("g-levels"))


def _auth(request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _export():
    path = str(_dir())
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        return importlib.import_module("glevels.export")
    except ImportError as exc:
        raise HTTPException(503, f"g-levels is not readable at {path}: {type(exc).__name__}")


def _projects():
    manifest = json.loads((gcore_dir() / "manifest.json").read_text())
    projects = {}
    for project in manifest.get("projects", []):
        names = [project["id"]]
        repo = Path((project.get("url") or "").rstrip("/")).name.removesuffix(".git")
        if repo and repo not in names:
            names.append(repo)
        projects[project["id"]] = names
    return projects


@router.get("/snapshot")
def snapshot(request: Request):
    _auth(request)
    return _export().snapshot()


@router.get("/sample")
def sample(request: Request, n: int = 6):
    _auth(request)
    return _export().sample(max(1, min(n, 20)))


@router.get("/projects")
def projects(request: Request):
    _auth(request)
    return {"projects": _export().projects_view(_projects())}


@router.get("/project/{pid}")
def project(pid: str, request: Request):
    _auth(request)
    if not _PROJECT.fullmatch(pid):
        raise HTTPException(404)
    names = _projects().get(pid)
    if names is None:
        raise HTTPException(404)
    return {**_export().project_view(names), "id": pid}


class Grade(BaseModel):
    id: str
    verdict: str
    note: str | None = None


@router.post("/grade")
def grade(request: Request, body: Grade):
    _auth(request)
    if not _ID.fullmatch(body.id) or body.verdict not in ("agree", "disagree"):
        raise HTTPException(400, "A grade takes an 8 character result id and agree or disagree")
    args = [sys.executable, "-c", _RUNNER, "grade", body.id, body.verdict]
    note = " ".join((body.note or "").replace("\x00", " ").split())[:500]
    if note:
        args.append(f"--note={note}")  # one token, so a note starting with "-" is not read as a flag
    try:
        proc = subprocess.run(args, cwd=_dir(), capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "glevels grade did not finish in 20 seconds. The grade may not be saved, so check the sample again.")
    except OSError:
        raise HTTPException(503, "glevels could not be started on this host. Nothing was saved.")
    if proc.returncode != 0:
        if "no result" in proc.stderr:
            raise HTTPException(404, f"No result {body.id} in the log, so nothing was saved.")
        log.warning("glevels grade %s failed: %s", body.id, (proc.stderr or proc.stdout).strip()[-2000:])
        raise HTTPException(500, "glevels grade failed and nothing was saved. The server log has the detail.")
    return {"ok": True, "id": body.id, "verdict": body.verdict}
