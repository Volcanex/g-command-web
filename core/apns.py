"""Apple push for the G-Command apps: token auth (.p8), HTTP/2 via httpx, JWT via PyJWT.

Config is read from the environment, which the unit fills from the root-only
/etc/g-secrets/gcommand-apns.env (drop-in zz-apns.conf), never from git:

  APNS_KEY_FILE   path to the AuthKey_XXXXXXXXXX.p8 (root-only, e.g. /etc/g-secrets/gcommand-apns.p8)
  APNS_KEY_ID     the key's 10-character id
  APNS_TEAM_ID    the Apple developer team id
  APNS_BUNDLE_IOS / APNS_BUNDLE_MACOS   optional, default com.gabrielpenman.gcommand(.mac)

Until all three of the first are set, send_all is a no-op that logs
"apns not configured" once per process. Each token carries its own
environment (sandbox for a debug build, production for TestFlight and the
store), so one alert can reach both kinds of build.
"""

import os
import sys
import threading
import time
from pathlib import Path

from core import push_tokens

HOSTS = {"sandbox": "https://api.sandbox.push.apple.com", "production": "https://api.push.apple.com"}
DEFAULT_BUNDLES = {"ios": "com.gabrielpenman.gcommand", "macos": "com.gabrielpenman.gcommand.mac"}
# critical would need Apple's critical-alert entitlement, so it maps to time-sensitive.
INTERRUPTION = {"critical": "time-sensitive", "error": "active", "warn": "active", "info": "active", "brief": "passive"}
DEAD = {"BadDeviceToken", "Unregistered"}  # not DeviceTokenNotForTopic: that is our bundle id being wrong
JWT_TTL = 45 * 60  # Apple refuses tokens older than an hour and throttles refreshes under 20 minutes.

_jwt = {"token": None, "at": 0.0, "key": None}
_jwt_lock = threading.Lock()
_warned = {"unconfigured": False}


def _log(msg: str) -> None:
    print(f"[apns] {msg}", file=sys.stderr, flush=True)


def config() -> dict | None:
    key_file = os.environ.get("APNS_KEY_FILE", "").strip()
    key_id = os.environ.get("APNS_KEY_ID", "").strip()
    team_id = os.environ.get("APNS_TEAM_ID", "").strip()
    if not (key_file and key_id and team_id and Path(key_file).is_file()):
        return None
    return {
        "key_file": key_file, "key_id": key_id, "team_id": team_id,
        "bundles": {
            "ios": os.environ.get("APNS_BUNDLE_IOS", "").strip() or DEFAULT_BUNDLES["ios"],
            "macos": os.environ.get("APNS_BUNDLE_MACOS", "").strip() or DEFAULT_BUNDLES["macos"],
        },
    }


def payload(level: str, source: str, msg: str, link: str) -> dict:
    level = (level or "info").lower()
    aps = {
        "alert": {"title": source or level.capitalize(), "body": msg},
        "sound": "default",
        "thread-id": source or level,
        "interruption-level": INTERRUPTION.get(level, "active"),
    }
    if aps["interruption-level"] == "passive":
        del aps["sound"]
    return {"aps": aps, "link": link, "level": level}


def _bearer(cfg: dict) -> str:
    import jwt
    with _jwt_lock:
        fresh = _jwt["token"] and _jwt["key"] == cfg["key_id"] and time.time() - _jwt["at"] < JWT_TTL
        if not fresh:
            secret = Path(cfg["key_file"]).read_text()
            now = int(time.time())
            _jwt.update(token=jwt.encode({"iss": cfg["team_id"], "iat": now}, secret, algorithm="ES256",
                                         headers={"kid": cfg["key_id"]}),
                        at=now, key=cfg["key_id"])
        return _jwt["token"]


def _post(client, url: str, headers: dict, body: dict):
    return client.post(url, headers=headers, json=body)


def send_all(level: str, source: str, msg: str, link: str, client=None) -> dict:
    """Push one alert to every paired device's token. Never raises."""
    cfg = config()
    if cfg is None:
        if not _warned["unconfigured"]:
            _warned["unconfigured"] = True
            _log("apns not configured")
        return {"configured": False, "sent": 0}
    try:
        tokens = push_tokens.live()
    except Exception as e:  # noqa: BLE001
        _log(f"token registry unreadable: {e!r}")
        return {"configured": True, "sent": 0, "failed": 0}
    if not tokens:
        return {"configured": True, "sent": 0, "failed": 0}
    body = payload(level, source, msg, link)
    passive = body["aps"]["interruption-level"] == "passive"
    sent = failed = dropped = 0
    own = client is None
    try:
        if own:
            import httpx
            client = httpx.Client(http2=True, timeout=10)
        bearer = _bearer(cfg)
        for t in tokens:
            headers = {
                "authorization": f"bearer {bearer}",
                "apns-topic": cfg["bundles"].get(t["platform"], DEFAULT_BUNDLES["ios"]),
                "apns-push-type": "alert",
                "apns-priority": "5" if passive else "10",
            }
            url = f"{HOSTS.get(t['environment'], HOSTS['production'])}/3/device/{t['token']}"
            try:
                r = _post(client, url, headers, body)
            except Exception as e:  # noqa: BLE001
                failed += 1
                _log(f"push to device {t['device_id']} failed: {e!r}")
                continue
            if r.status_code == 200:
                sent += 1
                continue
            failed += 1
            try:
                reason = (r.json() or {}).get("reason", "")
            except Exception:  # noqa: BLE001
                reason = ""
            if r.status_code == 410 or reason in DEAD:
                push_tokens.drop_token(t["token"])
                dropped += 1
            _log(f"push to device {t['device_id']} refused: {r.status_code} {reason}")
    except Exception as e:  # noqa: BLE001
        _log(f"push failed: {e!r}")
    finally:
        if own and client is not None:
            client.close()
    return {"configured": True, "sent": sent, "failed": failed, "dropped": dropped}
