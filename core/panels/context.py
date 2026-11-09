import json
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Lock
from time import monotonic

from core.panels.helpers import TZ


TTL = 5
MAX_STALE = 60
_LOCK = Lock()
_CACHE = {}
_PENDING = {}
_READS = ThreadPoolExecutor(max_workers=8, thread_name_prefix="panel-read")


def invalidate():
    with _LOCK:
        _CACHE.clear()
        _PENDING.clear()


def _refresh(key, future, load):
    try:
        value = load()
        with _LOCK:
            if _PENDING.get(key) is future:
                _CACHE[key] = {"value": value, "at": monotonic(), "retry_at": monotonic() + TTL}
        future.set_result(value)
    except Exception as exc:
        with _LOCK:
            if _PENDING.get(key) is future and key in _CACHE:
                _CACHE[key]["retry_at"] = monotonic() + TTL
        future.set_exception(exc)
    finally:
        with _LOCK:
            if _PENDING.get(key) is future:
                del _PENDING[key]


def _snapshot(key, load):
    with _LOCK:
        cached = _CACHE.get(key)
        now = monotonic()
        usable = cached is not None and now - cached["at"] < MAX_STALE
        if usable and now < cached["retry_at"]:
            return deepcopy(cached["value"])
        future = _PENDING.get(key)
        owner = future is None
        if owner:
            future = _PENDING[key] = Future()
        if usable:
            if owner:
                _READS.submit(_refresh, key, future, load)
            return deepcopy(cached["value"])
    if owner:
        _refresh(key, future, load)
    return deepcopy(future.result())


class Context:
    def __init__(self, request, now=None):
        self.request = request
        self.now = (now or datetime.now(TZ)).astimezone(TZ)

    def prefetch(self, *paths):
        for path in paths:
            _READS.submit(self.get, path)

    def get(self, path):
        from core.api.brain import UPSTREAM
        return _snapshot((UPSTREAM, path), lambda: self._load(path))

    def _load(self, path):
        if path in ("/api/compute/pace", "/api/compute/state"):
            from pages.compute import api
            return getattr(api, path.rsplit("/", 1)[1])(self.request)
        if path == "/api/crons/list":
            from pages.crons.api import listing
            return listing(self.request)
        if path == "/api/gadmin_panel/tickets?status=open":
            from core.api.gadmin_panel import list_tickets
            return list_tickets(self.request, status="open", project=None, severity=None)
        from core.api.brain import UPSTREAM
        req = urllib.request.Request(UPSTREAM + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
