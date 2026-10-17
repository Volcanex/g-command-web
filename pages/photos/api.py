"""Photos panel API, mounted at /api/photos. Admin-gated proxy in front of
photo-sync-server (127.0.0.1:5656), which has no auth of its own; nginx blocks
non-GET/POST from outside, so this gated proxy is the only delete path. The
site-wide page gate in server.py does not cover /api/*, so each route
re-checks the cookie inline (same pattern as pages/projects/api.py).

Listing comes from /files/all, cached in-process: the store is 11k+ objects
and the R2 listing behind it takes ~25s, which left the page on "Loading"
for half a minute. So the listing is fetched once at import, a cache older
than REFRESH_S is served as-is while a background thread refreshes it, and
/stats is counted from the same cached listing instead of walking R2 a
second time. Only a cold cache (first call after a failed warm-up) waits on
R2. Thumbnails stream through unbuffered. DELETE forwards the shared PHOTO_DELETE_TOKEN (instance passport) that
photo-sync-server requires.
"""
import json
import threading
import os
import re
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from core.auth import ADMIN_COOKIE, ADMIN_VALUE

router = APIRouter()

UPSTREAM = "http://127.0.0.1:5656"
DELETE_TOKEN = os.environ.get("PHOTO_DELETE_TOKEN", "")

CATS = ("raw", "masters", "compressed")
FN_RE = re.compile(r"^[^/\\\x00]{1,255}$")

REFRESH_S = 300
_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()
_fetch_lock = threading.Lock()
_refreshing = threading.Event()


def _gate(request: Request):
    if request.cookies.get(ADMIN_COOKIE) != ADMIN_VALUE:
        raise HTTPException(401, "unauthorized")


def _fetch(path, method="GET", headers=None, timeout=30):
    req = urllib.request.Request(UPSTREAM + path, method=method,
                                 headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout)


def _refresh():
    # One R2 walk at a time: a cold call that lands while the warm-up is in
    # flight waits for it and takes its result instead of starting another.
    asked = time.time()
    with _fetch_lock:
        with _lock:
            if _cache["data"] is not None and _cache["at"] >= asked:
                return _cache["data"]
        with _fetch("/files/all", timeout=90) as r:
            data = json.load(r)
        with _lock:
            _cache["data"] = data
            _cache["at"] = time.time()
        return data


def _refresh_bg():
    if _refreshing.is_set():
        return
    _refreshing.set()

    def run():
        try:
            _refresh()
        except Exception:
            pass  # keep serving the last good listing; the next call retries
        finally:
            _refreshing.clear()

    threading.Thread(target=run, daemon=True).start()


def _listing():
    with _lock:
        data, at = _cache["data"], _cache["at"]
    if data is None:
        return _refresh()
    if time.time() - at > REFRESH_S:
        _refresh_bg()
    return data


_refresh_bg()  # warm the cache at startup so the first visit does not wait


@router.get("/list")
def list_photos(request: Request):
    _gate(request)
    d = _listing()
    out = {}
    for cat in CATS:
        files = d.get(cat, {}).get("files", [])
        out[cat] = sorted(files, key=lambda f: f.get("modified") or "",
                          reverse=True)
    return out


@router.get("/stats")
def stats(request: Request):
    _gate(request)
    d = _listing()
    counts = {c: len(d.get(c, {}).get("files", [])) for c in CATS}
    totals = {c: sum(f.get("size_bytes") or 0 for f in d.get(c, {}).get("files", []))
              for c in CATS}
    return {"counts": counts, "bytes": totals,
            "total_count": sum(counts.values()),
            "total_bytes": sum(totals.values())}


@router.get("/thumb/{cat}/{filename}")
def thumb(cat: str, filename: str, request: Request, size: str = "small"):
    _gate(request)
    if cat not in CATS or not FN_RE.match(filename):
        raise HTTPException(404)
    if size not in ("tiny", "small", "medium", "large", "huge"):
        size = "small"
    q = urllib.parse.quote(filename)
    try:
        with _fetch(f"/thumbnail/{cat}/{q}?size={size}", timeout=60) as r:
            return Response(r.read(),
                            media_type=r.headers.get("Content-Type", "image/jpeg"),
                            headers={"Cache-Control": "private, max-age=86400"})
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code)


@router.get("/full/{cat}/{filename}")
def full(cat: str, filename: str, request: Request):
    _gate(request)
    if cat not in CATS or not FN_RE.match(filename):
        raise HTTPException(404)
    q = urllib.parse.quote(filename)
    # photo-sync 302s to a public R2 URL when configured; pass that through as
    # JSON so the client can open it, else stream (raw files can be 30MB+, so
    # cap what we proxy inline).
    req = urllib.request.Request(f"{UPSTREAM}/photo/{cat}/{q}")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=120) as r:
            return Response(r.read(),
                            media_type=r.headers.get("Content-Type",
                                                     "application/octet-stream"))
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307):
            return {"redirect": e.headers.get("Location")}
        raise HTTPException(e.code)


@router.delete("/{cat}/{filename}")
def delete(cat: str, filename: str, request: Request):
    _gate(request)
    if cat not in ("raw", "masters") or not FN_RE.match(filename):
        raise HTTPException(404, "only raw/masters can be deleted")
    q = urllib.parse.quote(filename)
    try:
        with _fetch(f"/{cat}/{q}", method="DELETE",
                    headers={"X-Delete-Token": DELETE_TOKEN}) as r:
            out = json.load(r)
        # Drop the file from the cached listing now: the stale-while-refresh
        # cache would otherwise show it again until the next refresh lands.
        with _lock:
            d = _cache["data"] or {}
            entry = d.get(cat) or {}
            entry["files"] = [f for f in entry.get("files", [])
                              if f.get("name") != filename]
            entry["count"] = len(entry["files"])
        _refresh_bg()
        return out
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code, e.read().decode(errors="replace")[:200])
