"""The wages proxy: gated by this site, forwarding to g-wages /api/ledger."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.wages import api as wages_api

REAL = httpx.AsyncClient


@pytest.fixture
def client(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"path": request.url.path, "q": request.url.query.decode()})

    monkeypatch.setattr(wages_api.httpx, "AsyncClient",
                        lambda **kw: REAL(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    app = FastAPI()
    app.include_router(wages_api.router, prefix="/api/wages")
    c = TestClient(app)
    c.seen = seen
    return c


def test_requires_cookie(client):
    assert client.get("/api/wages/clients").status_code == 401
    assert client.post("/api/wages/c/x/hours", json={}).status_code == 401
    assert client.seen == []


def test_forwards_to_ledger_with_query_and_body(client):
    client.cookies.set("seed_admin", "ok")
    r = client.get("/api/wages/c/acme/invoice/status?mode=all&current=1")
    assert r.json() == {"path": "/api/ledger/c/acme/invoice/status", "q": "mode=all&current=1"}
    client.post("/api/wages/c/acme/hours", json={"dow": 1, "hours": 2})
    assert client.seen[-1].method == "POST" and b"\"hours\"" in client.seen[-1].content


def test_unreachable_upstream_is_502(client, monkeypatch):
    client.cookies.set("seed_admin", "ok")

    def boom(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(wages_api.httpx, "AsyncClient",
                        lambda **kw: REAL(transport=httpx.MockTransport(boom), **kw))
    assert client.get("/api/wages/clients").status_code == 502
