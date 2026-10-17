import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api import admin  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin")
    monkeypatch.setattr(admin, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(admin, "ADMIN_VALUE", "ok")
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    monkeypatch.setattr(admin, "_LOGIN_ATTEMPTS", {})
    return TestClient(app)


@pytest.mark.parametrize("password", [None, "", "change-me"])
def test_login_disabled_until_password_set(client, monkeypatch, password):
    if password is None:
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_PASSWORD", password)
    r = client.post("/api/admin/login", json={"password": password or ""})
    assert r.status_code == 503
    assert "seed_admin=" not in r.headers.get("set-cookie", "")
    assert client.get("/api/admin/verify").json() == {"admin": False}


def test_login_with_password_set(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pw")
    assert client.post("/api/admin/login", json={"password": "change-me"}).status_code == 401
    r = client.post("/api/admin/login", json={"password": "test-pw"})
    assert r.status_code == 200
    assert "seed_admin=ok" in r.headers["set-cookie"]


def test_non_ascii_cookie_and_password_are_refused_not_500(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "right-password")
    r = client.get("/api/admin/verify", headers={"cookie": "seed_admin=\u00e9".encode()})
    assert r.status_code == 200
    assert r.json() == {"admin": False}
    assert client.post("/api/admin/login", json={"password": "caf\u00e9"}).status_code == 401
