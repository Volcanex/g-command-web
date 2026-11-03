"""Signing in to Command with Studio (core/studio_sso.py): only a good assertion for Studio
user 29, made for this origin and this browser's state, sets the admin cookie."""
import base64
import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import studio_sso

STUDIO = "https://studio.test"
HERE = "https://testserver"


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture
def key(monkeypatch):
    k = Ed25519PrivateKey.generate()
    pub = k.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    monkeypatch.setenv("STUDIO_ORIGIN", STUDIO)
    monkeypatch.setenv("STUDIO_IDP_PUBLIC_KEY", base64.b64encode(pub).decode())
    monkeypatch.delenv("STUDIO_ADMIN_USER_ID", raising=False)
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    monkeypatch.setattr(studio_sso, "_studio_up", lambda: True)
    return k


@pytest.fixture
def client(key):
    app = FastAPI()
    app.include_router(studio_sso.router)
    return TestClient(app, base_url=HERE, follow_redirects=False)


def sign(k, **over):
    now = int(time.time())
    c = {"iss": STUDIO, "aud": HERE, "sub": "29", "adm": True, "nonce": "", "iat": now, "exp": now + 60}
    c.update(over)
    body = b64u(json.dumps(c).encode())
    return body + "." + b64u(k.sign(body.encode()))


def begin(client, nxt="/studio"):
    r = client.get("/auth/studio/start", params={"next": nxt})
    assert r.status_code == 302
    u = urlsplit(r.headers["location"])
    assert f"{u.scheme}://{u.netloc}{u.path}" == STUDIO + "/sso/command"
    q = parse_qs(u.query)
    assert q["return_to"] == [HERE + "/auth/studio/callback"]
    return q["state"][0]


def finish(client, state, token):
    return client.get("/auth/studio/callback", params={"state": state, "assertion": token})


def test_round_trip_sets_admin_cookie_and_returns(client, key):
    state = begin(client, "/studio?x=1")
    r = finish(client, state, sign(key, nonce=state))
    assert r.status_code == 302 and r.headers["location"] == "/studio?x=1"
    assert "seed_admin=ok" in r.headers["set-cookie"]


@pytest.mark.parametrize("over", [
    {"sub": "30"}, {"adm": False}, {"aud": "https://evil.test"}, {"iss": "https://evil.test"},
    {"exp": int(time.time()) - 120, "iat": int(time.time()) - 180},
    {"exp": int(time.time()) + 3600},
])
def test_bad_claims_are_refused(client, key, over):
    state = begin(client)
    r = finish(client, state, sign(key, nonce=state, **over))
    assert r.headers["location"] == "/login?studio=refused"
    assert "seed_admin=ok" not in r.headers.get("set-cookie", "")


def test_wrong_key_nonce_or_no_cookie_is_refused(client, key):
    state = begin(client)
    assert finish(client, state, sign(Ed25519PrivateKey.generate(), nonce=state)).headers["location"] == "/login?studio=refused"
    state = begin(client)
    assert finish(client, state, sign(key, nonce="n" * 32)).headers["location"] == "/login?studio=refused"
    fresh = TestClient(client.app, base_url=HERE, follow_redirects=False)
    r = finish(fresh, state, sign(key, nonce=state))
    assert r.headers["location"] == "/login?studio=expired"


def test_studio_refusal_and_outage_land_on_password_login(client, key, monkeypatch):
    state = begin(client)
    r = client.get("/auth/studio/callback", params={"state": state, "error": "not_admin"})
    assert r.headers["location"] == "/login?studio=not_admin"
    monkeypatch.setattr(studio_sso, "_studio_up", lambda: False)
    assert client.get("/auth/studio/start").headers["location"] == "/login?studio=down"
    monkeypatch.delenv("STUDIO_IDP_PUBLIC_KEY")
    assert client.get("/auth/studio/start").headers["location"] == "/login?studio=off"


@pytest.mark.parametrize("nxt", ["//evil.test/x", "https://evil.test", "\\\\evil", "/a b"])
def test_next_is_a_local_path(client, key, nxt):
    state = begin(client, nxt)
    assert finish(client, state, sign(key, nonce=state)).headers["location"] == "/"
