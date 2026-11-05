"""The Recorder proxy: gated by this site, forwarding takes to g-content with its token."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.recorder import api as rec
from pages.showcase import api as sc

REAL = httpx.AsyncClient
PIECE = "cursor-take-20261105-a1b2c3"
TOKEN = "t" * 40


def respond(request):
    path = request.url.path
    if path.endswith("/files/poster.png"):
        return httpx.Response(200, stream=httpx.ByteStream(b"png"), headers={"content-type": "image/png"})
    if path == "/api/takes" and request.method == "POST" and b'"bad"' in request.content:
        return httpx.Response(400, json={"detail": "name: must be 1 to 80 characters"})
    if path == f"/api/takes/{PIECE}" and request.method == "DELETE":
        return httpx.Response(200, json={"deleted": PIECE})
    return httpx.Response(200, json={
        "path": path, "method": request.method, "q": request.url.query.decode(),
        "body": request.content.decode() if request.content else "",
        "ctype": request.headers.get("content-type"),
        "auth": request.headers.get("authorization") == f"Bearer {TOKEN}"})


@pytest.fixture
def client(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return respond(request)

    monkeypatch.setattr(sc, "_client", lambda: REAL(transport=httpx.MockTransport(handler), timeout=5))
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    monkeypatch.setenv("G_CONTENT_TOKEN", TOKEN)
    app = FastAPI()
    app.include_router(rec.router, prefix="/api/recorder")
    c = TestClient(app)
    c.seen = seen
    return c


def signed(client):
    client.cookies.set("seed_admin", "ok")
    return client


@pytest.mark.parametrize("method,url", [
    ("get", "/api/recorder/takes"), ("get", f"/api/recorder/takes/{PIECE}"),
    ("post", "/api/recorder/takes"), ("delete", f"/api/recorder/takes/{PIECE}"),
    ("get", f"/api/recorder/pieces/{PIECE}/files/poster.png"),
])
def test_every_route_needs_the_cookie(client, method, url):
    r = getattr(client, method)(url, **({"content": b"{}"} if method == "post" else {}))
    assert r.status_code == 401
    assert client.seen == []


def test_list_forwards_filters_with_token_and_never_returns_it(client):
    r = signed(client).get("/api/recorder/takes?events=1&kind=you&min_owner=7")
    body = r.json()
    assert body["path"] == "/api/takes" and body["method"] == "GET"
    assert "events=1" in body["q"] and "kind=you" in body["q"] and "min_owner=7" in body["q"]
    assert body["auth"] is True and TOKEN not in r.text
    assert client.get(f"/api/recorder/takes/{PIECE}").json()["path"] == f"/api/takes/{PIECE}"


def test_save_forwards_the_raw_body_as_json(client):
    raw = b'{"schema":"gs-cursor-take/1","name":"drag the G","events":[]}'
    r = signed(client).post("/api/recorder/takes", content=raw, headers={"content-type": "text/plain"})
    body = r.json()
    assert body["method"] == "POST" and body["path"] == "/api/takes"
    assert body["body"] == raw.decode() and body["ctype"] == "application/json" and body["auth"] is True


def test_save_uses_the_long_timeout(client, monkeypatch):
    calls = {}
    real = sc._json

    async def spy(*a, **kw):
        calls.update(kw)
        return await real(*a, **kw)
    monkeypatch.setattr(rec, "_json", spy)
    signed(client).post("/api/recorder/takes", content=b"{}")
    assert calls["timeout"] == 60


def test_save_over_4mb_is_413_before_forwarding(client):
    r = signed(client).post("/api/recorder/takes", content=b"x" * (4 * 1024 * 1024 + 1))
    assert r.status_code == 413
    assert client.seen == []


def test_empty_save_is_400(client):
    assert signed(client).post("/api/recorder/takes", content=b"").status_code == 400
    assert client.seen == []


def test_bad_take_passes_g_contents_reason_through(client):
    r = signed(client).post("/api/recorder/takes", content=b'{"name":"bad"}')
    assert r.status_code == 400 and r.json() == {"detail": "name: must be 1 to 80 characters"}


def test_delete_forwards(client):
    r = signed(client).delete(f"/api/recorder/takes/{PIECE}")
    assert r.json() == {"deleted": PIECE} and client.seen[-1].method == "DELETE"


def test_poster_streams(client):
    r = signed(client).get(f"/api/recorder/pieces/{PIECE}/files/poster.png")
    assert r.status_code == 200 and r.content == b"png" and client.seen[-1].url.path == f"/api/pieces/{PIECE}/files/poster.png"


@pytest.mark.parametrize("method,url", [
    ("get", "/api/recorder/takes/not-a-piece"), ("delete", "/api/recorder/takes/Bad_ID"),
    ("get", f"/api/recorder/pieces/{PIECE}/files/.hidden"), ("get", "/api/recorder/pieces/x/files/poster.png"),
    ("get", "/api/recorder/takes?events=2"), ("get", "/api/recorder/takes?kind=robot"),
    ("get", "/api/recorder/takes?min_owner=11"), ("get", "/api/recorder/takes?min_owner=-1"),
])
def test_ids_and_filters_are_validated_before_forwarding(client, method, url):
    assert getattr(signed(client), method)(url).status_code in (400, 404)
    assert client.seen == []


def test_upstream_404_passes_through(client, monkeypatch):
    def nf(request):
        return httpx.Response(404, json={"detail": "not a cursor-take piece"})
    monkeypatch.setattr(sc, "_client", lambda: REAL(transport=httpx.MockTransport(nf), timeout=5))
    r = signed(client).delete(f"/api/recorder/takes/{PIECE}")
    assert r.status_code == 404 and r.json() == {"detail": "not a cursor-take piece"}


def test_upstream_down_is_a_200_error(client, monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(sc, "_client", lambda: REAL(transport=httpx.MockTransport(boom), timeout=5))
    r = signed(client).get("/api/recorder/takes")
    assert r.status_code == 200 and r.json()["error"]["code"] == "unreachable"


def test_no_token_is_a_200_error(client, monkeypatch, tmp_path):
    monkeypatch.delenv("G_CONTENT_TOKEN")
    monkeypatch.setenv("G_CONTENT_TOKEN_FILE", str(tmp_path / "none"))
    r = signed(client).post("/api/recorder/takes", content=b"{}")
    assert r.status_code == 200 and r.json()["error"]["code"] == "no_token"
    assert client.seen == []
