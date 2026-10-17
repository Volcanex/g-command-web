"""upload page API, mounted at /api/upload.

A plain dropbox: files land in UPLOAD_DIR (default var/uploads here)
and nothing else in the system reads that directory. Deliberately not a
brain/g-site proxy: the point is getting bytes onto the box fast.

The page gate in server.py does not cover /api/* routers, so the admin
cookie is enforced here inline (same as pages/blog/api.py).

Filenames from the browser are untrusted: every name is reduced to its
basename, stripped of anything outside [A-Za-z0-9._-], and the resolved
path is re-checked against UPLOAD_DIR before any write or read.
"""
import os
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from core.auth import cookie_ok
from core.instance import ROOT

router = APIRouter()

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR") or ROOT / "var" / "uploads")

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _gate(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "unauthorized")


def _safe_name(raw: str) -> str:
    name = _UNSAFE.sub("_", Path(raw or "").name).strip("._")[:180]
    if not name:
        raise HTTPException(400, "unusable filename")
    return name


def _resolve(name: str) -> Path:
    """Resolve a stored file inside UPLOAD_DIR, or 404/400."""
    root = UPLOAD_DIR.resolve()
    target = (root / _safe_name(name)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(400, "bad path")
    if not target.is_file():
        raise HTTPException(404, "not found")
    return target


def _free_path(name: str) -> Path:
    """Never overwrite: foo.zip -> foo-1.zip -> foo-2.zip."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    base = UPLOAD_DIR / name
    if not base.exists():
        return base
    stem, suffix = base.stem, base.suffix
    for n in range(1, 1000):
        candidate = UPLOAD_DIR / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(409, "too many collisions")


def _entry(p: Path) -> dict:
    st = p.stat()
    return {"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime)}


@router.post("/files")
async def upload(request: Request, files: list[UploadFile]):
    _gate(request)
    saved = []
    for f in files:
        dest = _free_path(_safe_name(f.filename))
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out, 1024 * 1024)
        await f.close()
        saved.append(_entry(dest))
    return {"saved": saved, "dir": str(UPLOAD_DIR)}


@router.get("/list")
async def listing(request: Request):
    _gate(request)
    if not UPLOAD_DIR.is_dir():
        return {"files": [], "dir": str(UPLOAD_DIR), "free_bytes": None}
    files = sorted(
        (_entry(p) for p in UPLOAD_DIR.iterdir() if p.is_file()),
        key=lambda e: e["mtime"],
        reverse=True,
    )
    usage = shutil.disk_usage(UPLOAD_DIR)
    return {"files": files, "dir": str(UPLOAD_DIR), "free_bytes": usage.free}


@router.get("/file/{name}")
async def download(name: str, request: Request):
    _gate(request)
    target = _resolve(name)
    return FileResponse(target, filename=target.name, media_type="application/octet-stream")


@router.delete("/file/{name}")
async def delete(name: str, request: Request):
    _gate(request)
    _resolve(name).unlink()
    return {"deleted": name}
