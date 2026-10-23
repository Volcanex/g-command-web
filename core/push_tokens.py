"""APNs device tokens, one per paired device, in var/push-tokens.json.

Keyed by the device id from core/auth.py's registry, so a token belongs to a
paired device and nothing else. Revoking a device drops its token (app.py
calls forget), and live() also skips and prunes any token whose device is no
longer paired, so a revocation by any other path can never leave a phone
still receiving pushes.

The file is 0600, like var/devices.json. An APNs token is not a credential on
its own (sending needs the team's .p8 key) but it identifies a phone.
"""

import json
import os
import threading
import time
from pathlib import Path

from core import auth

TOKENS_FILE = Path(os.environ.get("GCOMMAND_PUSH_TOKENS", "") or Path(__file__).resolve().parent.parent / "var" / "push-tokens.json")
PLATFORMS = ("ios", "macos")
ENVIRONMENTS = ("sandbox", "production")
_lock = threading.Lock()


def _load() -> dict:
    try:
        data = json.loads(TOKENS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    tokens = data.get("tokens") if isinstance(data, dict) else None
    return tokens if isinstance(tokens, dict) else {}


def _save(tokens: dict) -> None:
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKENS_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"tokens": tokens}, f, indent=2)
    os.replace(tmp, TOKENS_FILE)


def register(device_id: str, token: str, platform: str, environment: str) -> dict:
    entry = {"token": token, "platform": platform, "environment": environment, "updated": int(time.time())}
    with _lock:
        tokens = _load()
        # One phone, one row: a token re-registered under a new pairing moves.
        tokens = {d: e for d, e in tokens.items() if e.get("token") != token}
        tokens[device_id] = entry
        _save(tokens)
    return entry


def forget(device_id: str) -> bool:
    with _lock:
        tokens = _load()
        if device_id not in tokens:
            return False
        del tokens[device_id]
        _save(tokens)
    return True


def drop_token(token: str) -> None:
    """Remove a token APNs reported dead (410 or BadDeviceToken)."""
    with _lock:
        tokens = _load()
        kept = {d: e for d, e in tokens.items() if e.get("token") != token}
        if len(kept) != len(tokens):
            _save(kept)


def live() -> list[dict]:
    """Every token whose device is still paired, as {device_id, token, platform, environment}."""
    paired = {d["id"] for d in auth.list_devices()}
    with _lock:
        tokens = _load()
        kept = {d: e for d, e in tokens.items() if d in paired}
        if len(kept) != len(tokens):
            _save(kept)
    return [{"device_id": d, **e} for d, e in kept.items()]
