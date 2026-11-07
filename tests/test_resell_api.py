"""Resell keeps data and actions upstream; Command gates and renders them."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.resell import api

REAL_CLIENT = httpx.AsyncClient
ITEM = "507f1f77bcf86cd799439011"
SERVICE = "arbitrage_finder-bot"


@pytest.fixture
def client(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/items" and request.url.params.get("status") == "real_sold":
            page = int(request.url.params["page"])
            return httpx.Response(200, json={"items": [{"_id": f"sold-{page}"}], "total_pages": 2})
        if request.url.path.startswith("/images/"):
            return httpx.Response(200, content=b"image bytes", headers={"content-type": "image/jpeg", "set-cookie": "upstream=secret"})
        if request.url.path == "/services":
            return httpx.Response(200, json={"services": [{"name": SERVICE}], "count": 1})
        if request.url.path == "/bots":
            return httpx.Response(200, json={"bots": []})
        return httpx.Response(200, json={"path": request.url.path})

    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    app = FastAPI()
    app.include_router(api.router, prefix="/api/resell")
    result = TestClient(app)
    result.seen = seen
    return result


@pytest.mark.parametrize("method,path", [
    ("GET", ""), ("GET", "/bots"), ("GET", "/profit"),
    ("GET", f"/pool/items/{ITEM}"), ("GET", f"/pool/images/{ITEM}"),
    ("DELETE", f"/pool/items/{ITEM}"), ("POST", f"/registry/bots/{SERVICE}/scale?count=1"),
    ("POST", f"/config/config/{SERVICE}"),
])
def test_requires_admin_before_contacting_upstream(client, method, path):
    assert client.request(method, f"/api/resell{path}").status_code == 401
    assert client.seen == []


@pytest.mark.parametrize("method,path", [
    ("GET", "/pool/items/invalid"), ("POST", "/pool/items"),
    ("GET", "/pool/public-images/x/y"), ("GET", "/config/config/other-service"),
    ("POST", "/registry/bots/unrelated/scale"), ("DELETE", "/pool/items"),
    ("GET", "/registry/bots/arbitrage_x/other"), ("GET", "/network/sessions"),
    ("GET", "/pool/items/%2e%2e%2fstats"), ("GET", "/pool/items/%252e%252e"),
])
def test_only_existing_admin_endpoints_are_exposed(client, method, path):
    client.cookies.set("seed_admin", "ok")
    assert client.request(method, f"/api/resell{path}").status_code == 404
    assert client.seen == []


def test_preserves_filters_body_method_and_upstream_origin(client):
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/resell/pool/items?status=real_sold&page=2&page_size=10&include_data=true")
    assert response.status_code == 200
    request = client.seen[-1]
    assert request.url.host == "127.0.0.1" and request.url.port == 7500
    assert request.url.params["status"] == "real_sold" and request.url.params["page"] == "2"
    assert "cookie" not in request.headers
    client.post(f"/api/resell/config/config/{SERVICE}", json={"dry_run": True})
    request = client.seen[-1]
    assert request.url.port == 7504 and request.method == "POST"
    assert request.content == b'{"dry_run":true}'
    client.post(f"/api/resell/registry/bots/{SERVICE}/config", json={"dry_run": True})
    assert client.seen[-1].url.port == 7503
    client.delete(f"/api/resell/pool/items/{ITEM}")
    assert client.seen[-1].method == "DELETE"


def test_scale_and_variant_use_the_existing_query_parameters(client):
    client.cookies.set("seed_admin", "ok")
    assert client.post(f"/api/resell/registry/bots/{SERVICE}/scale?count=0").status_code == 200
    assert client.seen[-1].url.params["count"] == "0"
    assert client.post(f"/api/resell/registry/services/create-variant?base_service={SERVICE}&variant_name=test&replicas=0").status_code == 200
    assert dict(client.seen[-1].url.params) == {"base_service": SERVICE, "variant_name": "test", "replicas": "0"}


def test_profit_collects_every_page_from_pool(client):
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/resell/profit")
    assert response.json() == {"items": [{"_id": "sold-1"}, {"_id": "sold-2"}]}
    assert [r.url.params["page"] for r in client.seen] == ["1", "2"]
    assert all(r.url.params["status"] == "real_sold" and r.url.params["include_data"] == "true" for r in client.seen)


def test_image_bytes_are_gated_and_upstream_cookies_are_dropped(client):
    client.cookies.set("seed_admin", "ok")
    response = client.get(f"/api/resell/pool/images/{ITEM}")
    assert response.content == b"image bytes" and response.headers["content-type"] == "image/jpeg"
    assert "set-cookie" not in response.headers and response.headers["cache-control"] == "no-store"


def test_bots_combines_services_and_tasks(client):
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/resell/bots").json() == {"services": [{"name": SERVICE}], "bots": []}


def test_offline_services_do_not_look_like_an_empty_pool(client, monkeypatch):
    def offline(request):
        raise httpx.ConnectError("private internal connection details")

    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(offline), **kw))
    client.cookies.set("seed_admin", "ok")
    response = client.get("/api/resell")
    assert response.status_code == 200
    assert len(response.json()["services"]) == 5
    assert all(s["available"] is False and "data" not in s for s in response.json()["services"])
    response = client.get("/api/resell/pool/items")
    assert response.status_code == 503 and "private" not in response.text


def test_upstream_error_status_is_preserved_without_exception_details(client, monkeypatch):
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(
        transport=httpx.MockTransport(lambda req: httpx.Response(422, json={"detail": "private traceback"})), **kw))
    client.cookies.set("seed_admin", "ok")
    response = client.post(f"/api/resell/config/config/{SERVICE}", json={})
    assert response.status_code == 422 and "private" not in response.text


def test_unreadable_profit_does_not_silently_drop_items(client, monkeypatch):
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, text="not JSON")), **kw))
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/resell/profit").status_code == 502


def test_missing_persistent_config_can_be_created_without_hiding_offline_errors(client, monkeypatch):
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(
        transport=httpx.MockTransport(lambda req: httpx.Response(404, json={})), **kw))
    client.cookies.set("seed_admin", "ok")
    assert client.get(f"/api/resell/config/config/{SERVICE}").json() == {"config": {}, "exists": False}
    assert client.get(f"/api/resell/pool/items/{ITEM}").status_code == 404
