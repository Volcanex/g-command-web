import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.gcore import api as gcore_api  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("# passport\nTOKEN_A=secret-a\nEMPTY=\n")
    (tmp_path / "manifest.json").write_text('{"services": []}')
    app = FastAPI()
    app.include_router(gcore_api.router, prefix="/api/gcore")
    monkeypatch.setattr(gcore_api, "GCORE", tmp_path)
    monkeypatch.setattr(gcore_api, "ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr(gcore_api, "ADMIN_VALUE", "ok")
    return TestClient(app)


def test_requires_cookie(client):
    assert client.get("/api/gcore").status_code == 401
    assert client.post("/api/gcore/reveal", json={"key": "TOKEN_A"}).status_code == 401


def test_list_has_key_names_but_no_values(client):
    client.cookies.set("seed_admin", "ok")
    r = client.get("/api/gcore")
    assert r.json()["env"] == {"TOKEN_A": True, "EMPTY": False}
    assert "secret-a" not in r.text


def test_reveal_returns_one_value_uncached(client):
    client.cookies.set("seed_admin", "ok")
    r = client.post("/api/gcore/reveal", json={"key": "TOKEN_A"})
    assert r.json() == {"key": "TOKEN_A", "value": "secret-a"}
    assert r.headers["cache-control"] == "no-store"
    assert client.post("/api/gcore/reveal", json={"key": "MISSING"}).status_code == 404
