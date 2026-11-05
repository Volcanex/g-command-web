"""The Showcase proxy: gated by this site, forwarding to g-content with its token."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.showcase import api as sc

REAL = httpx.AsyncClient
PIECE = "iso-scene-20261105-a1b2c3"
TOKEN = "t" * 40


def raw(status, data, headers):
    # A body the proxy can stream, as a real socket would give it.
    return httpx.Response(status, stream=httpx.ByteStream(data), headers=headers)


def respond(request):
    path = request.url.path
    if path.endswith("/files/clip.mp4"):
        rng = request.headers.get("range")
        if rng:
            return raw(206, b"0123", {
                "content-type": "video/mp4", "content-range": "bytes 0-3/100", "accept-ranges": "bytes"})
        return raw(200, b"x" * 100, {"content-type": "video/mp4", "accept-ranges": "bytes"})
    if path.endswith("/files/page.html"):
        return raw(200, b"<script>1</script>", {"content-type": "text/html; charset=utf-8"})
    if path.endswith("/files/hero.svg"):
        return raw(200, b"<svg/>", {"content-type": "image/svg+xml"})
    if path.endswith("/files/hero.png"):
        return raw(200, b"png", {"content-type": "image/png"})
    if path.endswith("/files/gone.png"):
        return httpx.Response(404, json={"detail": "no such file"})
    if path.startswith("/vendor/three/"):
        return raw(200, b"export{}", {"content-type": "text/javascript"})
    if path == f"/api/pieces/{PIECE}-missing":
        return httpx.Response(404, json={"detail": "no such piece"})
    body = request.content.decode() if request.content else ""
    return httpx.Response(200, json={"path": path, "q": request.url.query.decode(), "body": body,
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
    app.include_router(sc.router, prefix="/api/showcase")
    c = TestClient(app)
    c.seen = seen
    return c


def signed(client):
    client.cookies.set("seed_admin", "ok")
    return client


@pytest.mark.parametrize("method,url", [
    ("get", "/api/showcase/recipes"), ("get", "/api/showcase/recipes/iso-scene"),
    ("get", "/api/showcase/pieces"), ("get", f"/api/showcase/pieces/{PIECE}"),
    ("get", f"/api/showcase/pieces/{PIECE}/files/hero.png"), ("get", "/api/showcase/calibration"),
    ("get", "/api/showcase/runners"), ("get", "/api/showcase/collections"),
    ("get", "/api/showcase/vendor/three/build/three.module.js"),
    ("post", f"/api/showcase/pieces/{PIECE}/rating"),
])
def test_every_route_needs_the_cookie(client, method, url):
    r = getattr(client, method)(url, **({"json": {"score": 5}} if method == "post" else {}))
    assert r.status_code == 401
    assert client.seen == []


def test_forwards_with_token_and_never_returns_it(client):
    r = signed(client).get("/api/showcase/pieces?recipe=iso-scene&status=candidate")
    body = r.json()
    assert body["path"] == "/api/pieces" and "recipe=iso-scene" in body["q"] and "status=candidate" in body["q"]
    assert body["auth"] is True
    assert TOKEN not in r.text
    assert client.get("/api/showcase/recipes/iso-scene").json()["path"] == "/api/recipes/iso-scene"
    assert client.get("/api/showcase/calibration").json()["path"] == "/api/calibration"
    assert client.get("/api/showcase/runners").json()["path"] == "/api/runners"


@pytest.mark.parametrize("url", [
    "/api/showcase/recipes/Bad_ID", "/api/showcase/pieces/not-a-piece",
    f"/api/showcase/pieces/{PIECE}/files/.hidden", f"/api/showcase/pieces/{PIECE}/files/Hero.PNG",
    "/api/showcase/pieces?recipe=..", "/api/showcase/pieces?collection=G_Studio",
    "/api/showcase/pieces?collection=../x", "/api/showcase/pieces?status=anything",
    "/api/showcase/vendor/three/package.json", "/api/showcase/vendor/three/build/../../secret.js",
    "/api/showcase/vendor/three/src/Three.js",
])
def test_ids_and_paths_are_validated_before_forwarding(client, url):
    assert signed(client).get(url).status_code in (400, 404)
    assert client.seen == []


def test_vendor_allows_build_and_examples_jsm(client):
    signed(client)
    assert client.get("/api/showcase/vendor/three/build/three.module.js").status_code == 200
    r = client.get("/api/showcase/vendor/three/examples/jsm/controls/OrbitControls.js")
    assert r.status_code == 200 and client.seen[-1].url.path == "/vendor/three/examples/jsm/controls/OrbitControls.js"


def test_range_passes_both_ways(client):
    r = signed(client).get(f"/api/showcase/pieces/{PIECE}/files/clip.mp4", headers={"Range": "bytes=0-3"})
    assert client.seen[-1].headers["range"] == "bytes=0-3"
    assert r.status_code == 206 and r.content == b"0123"
    assert r.headers["content-range"] == "bytes 0-3/100" and r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-type"] == "video/mp4"
    assert "content-security-policy" not in r.headers


@pytest.mark.parametrize("name", ["page.html", "hero.svg"])
def test_html_and_svg_are_sandboxed(client, name):
    r = signed(client).get(f"/api/showcase/pieces/{PIECE}/files/{name}")
    assert r.headers["content-security-policy"] == "sandbox allow-scripts"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_png_is_not_sandboxed_and_missing_file_is_404(client):
    signed(client)
    assert "content-security-policy" not in client.get(f"/api/showcase/pieces/{PIECE}/files/hero.png").headers
    assert client.get(f"/api/showcase/pieces/{PIECE}/files/gone.png").status_code == 404


@pytest.mark.parametrize("body", [
    {"score": 0}, {"score": 11}, {"score": 5.5}, {"score": "7"}, {"score": True}, {},
    {"score": 5, "note": "x" * 501}, {"score": 5, "note": 3},
])
def test_rating_is_validated(client, body):
    assert signed(client).post(f"/api/showcase/pieces/{PIECE}/rating", json=body).status_code == 400
    assert client.seen == []


def test_rating_forwards(client):
    r = signed(client).post(f"/api/showcase/pieces/{PIECE}/rating", json={"score": 10, "note": "x" * 500})
    assert r.status_code == 200
    assert client.seen[-1].method == "POST" and client.seen[-1].url.path == f"/api/pieces/{PIECE}/rating"
    assert '"score": 10' in r.json()["body"] or '"score":10' in r.json()["body"]


def test_upstream_4xx_passes_through(client, monkeypatch):
    def nf(request):
        return httpx.Response(404, json={"detail": "no such piece"})
    monkeypatch.setattr(sc, "_client", lambda: REAL(transport=httpx.MockTransport(nf), timeout=5))
    r = signed(client).get(f"/api/showcase/pieces/{PIECE}")
    assert r.status_code == 404 and r.json() == {"detail": "no such piece"}


def test_upstream_down_is_a_200_error(client, monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(sc, "_client", lambda: REAL(transport=httpx.MockTransport(boom), timeout=5))
    r = signed(client).get("/api/showcase/recipes")
    assert r.status_code == 200 and r.json()["error"]["code"] == "unreachable"


def test_no_token_is_a_200_error(client, monkeypatch, tmp_path):
    monkeypatch.delenv("G_CONTENT_TOKEN")
    monkeypatch.setenv("G_CONTENT_TOKEN_FILE", str(tmp_path / "none"))
    r = signed(client).get("/api/showcase/pieces")
    assert r.status_code == 200 and r.json()["error"]["code"] == "no_token"
    assert client.seen == []


def test_token_file_is_read_at_call_time(client, monkeypatch, tmp_path):
    monkeypatch.delenv("G_CONTENT_TOKEN")
    f = tmp_path / "token"
    f.write_text(TOKEN + "\n")
    monkeypatch.setenv("G_CONTENT_TOKEN_FILE", str(f))
    assert signed(client).get("/api/showcase/recipes").json()["auth"] is True


def test_collections_forward_and_filter_passes_through(client):
    signed(client)
    body = client.get("/api/showcase/collections").json()
    assert body["path"] == "/api/collections" and body["auth"] is True
    body = client.get("/api/showcase/pieces?collection=g-studio&status=candidate").json()
    assert body["path"] == "/api/pieces" and "collection=g-studio" in body["q"] and "status=candidate" in body["q"]
