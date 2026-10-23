"""APNs fan-out: the device token registry, the payload mapping and the /api/push route."""
import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import apns, auth, push_tokens
from core.api import admin, app as app_api, push

TOKEN = "ab" * 32


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(auth, "ADMIN_VALUE", "ok")
    monkeypatch.setattr(auth, "DEVICES_FILE", tmp_path / "devices.json")
    monkeypatch.setattr(auth, "_cache", {"key": None, "devices": []})
    monkeypatch.setattr(push_tokens, "TOKENS_FILE", tmp_path / "push-tokens.json")
    monkeypatch.setattr(admin, "_LOGIN_ATTEMPTS", {})
    monkeypatch.setattr(apns, "_warned", {"unconfigured": False})
    monkeypatch.setattr(apns, "_jwt", {"token": None, "at": 0.0, "key": None})
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pw")
    monkeypatch.setenv("PUBLIC_HOST", "command.example.com")
    monkeypatch.setenv("ALERT_PUSH_TOKEN", "spine-secret")
    for k in ("APNS_KEY_FILE", "APNS_KEY_ID", "APNS_TEAM_ID"):
        monkeypatch.delenv(k, raising=False)
    a = FastAPI()
    a.include_router(app_api.router, prefix="/api/app")
    a.include_router(push.router, prefix="/api/push")
    return TestClient(a)


def paired(client, platform="ios"):
    body = client.post("/api/app/pair", json={"name": "Phone", "platform": platform, "password": "test-pw"}).json()
    return body["device_id"], {"seed_admin": body["token"]}


def register(client, cookies, token=TOKEN, platform="ios", environment="sandbox"):
    return client.post("/api/app/push-token", cookies=cookies,
                       json={"token": token, "platform": platform, "environment": environment})


# ------------------------------------------------------------ registry

def test_register_needs_a_paired_device(client):
    assert register(client, {}).status_code == 401
    assert register(client, {"seed_admin": "ok"}).status_code == 400  # browser cookie, no device


def test_register_validates(client):
    _, me = paired(client)
    assert register(client, me, token="not-hex").status_code == 400
    assert register(client, me, platform="android").status_code == 400
    assert register(client, me, environment="dev").status_code == 400


def test_register_stores_one_token_per_device_privately(client, tmp_path):
    dev, me = paired(client)
    assert register(client, me, token=TOKEN.upper()).json() == {"ok": True, "device_id": dev}
    assert register(client, me, token="cd" * 32, environment="production").status_code == 200
    rows = push_tokens.live()
    assert rows == [{"device_id": dev, "token": "cd" * 32, "platform": "ios",
                     "environment": "production", "updated": rows[0]["updated"]}]
    assert (tmp_path / "push-tokens.json").stat().st_mode & 0o777 == 0o600


def test_delete_and_revoke_forget_the_token(client):
    dev, me = paired(client)
    other_dev, other = paired(client, "macos")
    register(client, me)
    register(client, other, token="cd" * 32, platform="macos")
    assert client.request("DELETE", "/api/app/push-token", cookies=me).json() == {"ok": True, "removed": True}
    assert [t["device_id"] for t in push_tokens.live()] == [other_dev]
    assert client.delete(f"/api/app/devices/{other_dev}", cookies=me).status_code == 200
    assert push_tokens.live() == []


def test_tokens_of_devices_revoked_elsewhere_are_skipped_and_pruned(client):
    dev, me = paired(client)
    register(client, me)
    auth.revoke_device(dev)  # not through the route
    assert push_tokens.live() == []
    assert json.loads(push_tokens.TOKENS_FILE.read_text())["tokens"] == {}


# ------------------------------------------------------------ payload

def test_payload_mapping():
    p = apns.payload("critical", "brain-mcp", "down", "/system")
    assert p["aps"]["alert"] == {"title": "brain-mcp", "body": "down"}
    assert p["aps"]["thread-id"] == "brain-mcp"
    assert p["aps"]["interruption-level"] == "time-sensitive"
    assert p["link"] == "/system"
    assert apns.payload("warn", "", "x", "/")["aps"]["alert"]["title"] == "Warn"
    brief = apns.payload("brief", "Morning brief", "x", "/")["aps"]
    assert brief["interruption-level"] == "passive" and "sound" not in brief
    assert apns.payload("info", "Reminder", "x", "/")["aps"]["interruption-level"] == "active"


def test_link_matches_api_alerts_routing(monkeypatch):
    monkeypatch.setenv("PUBLIC_HOST", "command.example.com")
    assert push.link_for("critical", "brain-mcp") == "/system"
    assert push.link_for("warn", "calendar-sync") == "/system"
    assert push.link_for("critical", "Vital reminder") == "/calendar"
    assert push.link_for("info", "Catching up (3)") == "/calendar"
    assert push.link_for("info", "x", "https://command.example.com/tickets?id=1") == "/tickets?id=1"
    assert push.link_for("brief", "Morning brief") == "/"


# ------------------------------------------------------------ sender

class Resp:
    def __init__(self, status, reason=""):
        self.status_code = status
        self._reason = reason

    def json(self):
        return {"reason": self._reason} if self._reason else {}


class FakeClient:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def post(self, url, headers, json):
        self.calls.append((url, headers, json))
        reply = self.replies.get(url.rsplit("/", 1)[1], Resp(200))
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def configured(monkeypatch, tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    (tmp_path / "AuthKey.p8").write_bytes(pem)
    monkeypatch.setenv("APNS_KEY_FILE", str(tmp_path / "AuthKey.p8"))
    monkeypatch.setenv("APNS_KEY_ID", "KEY1234567")
    monkeypatch.setenv("APNS_TEAM_ID", "TEAM123456")
    return key


def test_unconfigured_is_a_quiet_no_op(client, capsys):
    assert apns.send_all("info", "x", "y", "/") == {"configured": False, "sent": 0}
    apns.send_all("info", "x", "y", "/")
    assert capsys.readouterr().err.count("apns not configured") == 1


def test_sends_per_token_environment_and_bundle(client, configured):
    _, me = paired(client)
    _, mac = paired(client, "macos")
    register(client, me, environment="sandbox")
    register(client, mac, token="cd" * 32, platform="macos", environment="production")
    fake = FakeClient({})
    assert apns.send_all("critical", "brain-mcp", "down", "/system", client=fake)["sent"] == 2
    by_url = {u: (h, b) for u, h, b in fake.calls}
    ios = by_url[f"https://api.sandbox.push.apple.com/3/device/{TOKEN}"]
    macos = by_url[f"https://api.push.apple.com/3/device/{'cd' * 32}"]
    assert ios[0]["apns-topic"] == "com.gabrielpenman.gcommand"
    assert macos[0]["apns-topic"] == "com.gabrielpenman.gcommand.mac"
    assert ios[0]["apns-push-type"] == "alert" and ios[0]["apns-priority"] == "10"
    claims = jwt.decode(ios[0]["authorization"].removeprefix("bearer "), configured.public_key(),
                        algorithms=["ES256"])
    assert claims["iss"] == "TEAM123456"
    assert jwt.get_unverified_header(ios[0]["authorization"].removeprefix("bearer "))["kid"] == "KEY1234567"
    assert ios[1]["link"] == "/system"


def test_dead_tokens_are_dropped_and_others_still_sent(client, configured):
    ids = []
    for i, tok in enumerate(("aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32)):
        dev, me = paired(client)
        register(client, me, token=tok)
        ids.append(dev)
    fake = FakeClient({"aa" * 32: Resp(410, "Unregistered"), "bb" * 32: Resp(400, "BadDeviceToken"),
                       "cc" * 32: OSError("network")})
    r = apns.send_all("info", "x", "y", "/", client=fake)
    assert r == {"configured": True, "sent": 1, "failed": 3, "dropped": 2}
    assert sorted(t["token"] for t in push_tokens.live()) == ["cc" * 32, "dd" * 32]


# ------------------------------------------------------------ route

def test_push_route_auth_and_queue(client, monkeypatch):
    seen = []
    monkeypatch.setattr(apns, "send_all", lambda *a: seen.append(a))
    body = {"level": "critical", "source": "brain-mcp", "msg": "down"}
    assert client.post("/api/push", json=body).status_code == 401
    assert client.post("/api/push", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    r = client.post("/api/push", json=body, headers={"Authorization": "Bearer spine-secret"})
    assert r.status_code == 202 and r.json()["queued"] is True
    assert seen == [("critical", "brain-mcp", "down", "/system")]
    monkeypatch.delenv("ALERT_PUSH_TOKEN")
    assert client.post("/api/push", json=body, headers={"Authorization": "Bearer "}).status_code == 503
