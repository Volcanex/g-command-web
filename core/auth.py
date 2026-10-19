"""The admin session secret, read in one place for every router.

ADMIN_COOKIE_VALUE is the session secret: holding it is being logged in.
It used to default to "ok", which anyone could forge, and each router read
it for itself, so one missed copy reopened the hole. Everything now imports
it from here, and importing this module without it stops the process.
server.py imports it before mounting any router, so the server refuses to
start rather than serve a gate that a constant opens. cookie_ok is the one
compare, constant time and on bytes so a non-ASCII cookie is a refusal, not
a TypeError.

Paired devices (the iPhone and Mac apps) each hold their own token instead of
the shared secret, sent as the same cookie. Only its sha256 is kept, in
var/devices.json, so revoking one device leaves the rest signed in and a read
of the file signs nobody in.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

ADMIN_COOKIE = os.environ.get("ADMIN_COOKIE", "seed_admin")
ADMIN_VALUE = os.environ.get("ADMIN_COOKIE_VALUE", "")
if not ADMIN_VALUE:
    raise SystemExit(
        "refusing to start: ADMIN_COOKIE_VALUE is unset. It is the admin session "
        "secret; set it to a long random value, for example "
        "`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`."
    )


DEVICES_FILE = Path(os.environ.get("GCOMMAND_DEVICES", "") or Path(__file__).resolve().parent.parent / "var" / "devices.json")
TOKEN_PREFIX = "gd_"
_SEEN_EVERY = 600
_lock = threading.Lock()
_cache = {"key": None, "devices": []}


def cookie_ok(cookies) -> bool:
    value = cookies.get(ADMIN_COOKIE, "")
    if hmac.compare_digest(value.encode(), ADMIN_VALUE.encode()):
        return True
    return device_for(value) is not None


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load() -> list:
    try:
        st = DEVICES_FILE.stat()
    except FileNotFoundError:
        _cache.update(key=None, devices=[])
        return _cache["devices"]
    key = (st.st_mtime_ns, st.st_size)
    if _cache["key"] != key:
        try:
            data = json.loads(DEVICES_FILE.read_text())
        except (OSError, ValueError):
            data = {}
        _cache.update(key=key, devices=data.get("devices", []) if isinstance(data, dict) else [])
    return _cache["devices"]


def _save(devices: list) -> None:
    DEVICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEVICES_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"devices": devices}, f, indent=2)
    os.replace(tmp, DEVICES_FILE)
    _cache["key"] = None


def device_for(token: str):
    if not token.startswith(TOKEN_PREFIX):
        return None
    digest = _digest(token)
    with _lock:
        devices = _load()
        device = next((d for d in devices if hmac.compare_digest(d.get("sha256", ""), digest)), None)
        if device is not None and time.time() - device.get("last_seen", 0) > _SEEN_EVERY:
            device["last_seen"] = int(time.time())
            _save(devices)
    return device


def add_device(name: str, platform: str) -> tuple[str, dict]:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = int(time.time())
    device = {
        "id": secrets.token_hex(6),
        "name": name.strip()[:60] or "Device",
        "platform": platform if platform in ("ios", "macos") else "other",
        "sha256": _digest(token),
        "created": now,
        "last_seen": now,
    }
    with _lock:
        devices = list(_load())
        devices.append(device)
        _save(devices)
    return token, device


def list_devices() -> list:
    with _lock:
        return [{k: v for k, v in d.items() if k != "sha256"} for d in _load()]


def revoke_device(device_id: str) -> bool:
    with _lock:
        devices = _load()
        kept = [d for d in devices if d.get("id") != device_id]
        if len(kept) == len(devices):
            return False
        _save(kept)
    return True
