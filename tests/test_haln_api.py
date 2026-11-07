"""HALN's admin gate, read-only database boundary and legacy data shapes."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pages.haln import api


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "pool.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE items (id INTEGER PRIMARY KEY, source_key TEXT, status TEXT,
                                locked_until REAL, data TEXT);
            CREATE TABLE events (id INTEGER PRIMARY KEY, event_type TEXT, ts REAL,
                                 item_id INTEGER, data TEXT);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, token TEXT, created_ts REAL,
                                 status TEXT, email TEXT, name TEXT, address_json TEXT,
                                 items_json TEXT, total_pence INTEGER, gateway TEXT);
        """)
        for item_id, status, data in (
            (1, "listed", {"title": "Bottle", "price_pence": 1299, "fulfilment_status": "rfq_pending",
                           "creative_briefs": [{"hook": "Bottle brief"}], "creative_assets": []}),
            (2, "candidate", {"graduation_requirement": "Find evidence"}),
            (3, "failed", {"title": "Failed candidate"}),
        ):
            conn.execute("INSERT INTO items VALUES (?,?,?,?,?)", (item_id, f"source:{item_id}", status, None, json.dumps(data)))
        for event_id, kind, item_id in ((1, "item.added", 1), (2, "item.failed", 3), (3, "item.added", 2)):
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?)", (event_id, kind, event_id, item_id, "{}"))
        conn.execute("INSERT INTO orders VALUES (1, 'opaque-token', 1, 'test_paid', 'a@example.com', 'A', '{}', '[]', 1299, 'test')")
    monkeypatch.setenv("HALN_ROOT", str(tmp_path))
    monkeypatch.setenv("HALN_DB", str(path))
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    rules = {
        "pool.evidence": SimpleNamespace(tier_counts=lambda data: {"measured": 7, "review": 9}),
        "store.staging": SimpleNamespace(readiness=lambda item: [{"key": "evidence", "ok": True}],
                                          overall=lambda criteria: "from-project-rules"),
        "content.prompt_pack": SimpleNamespace(build_entries=lambda pool: [
            {"item_id": pool.get_item(1)["id"], "count": len(pool.list_items())}]),
    }
    monkeypatch.setattr(api, "_module", rules.__getitem__)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/haln")
    c = TestClient(app)
    c.db_path = path
    c.root = tmp_path
    return c


@pytest.mark.parametrize("path", ["", "/pool", "/decisions", "/staging", "/creative", "/events", "/orders",
                                   "/item/1", "/orders/opaque-token", "/creative/pack", "/assets/1/0"])
def test_every_endpoint_requires_command_cookie(client, path):
    assert client.get("/api/haln" + path).status_code == 401


def test_reads_old_schema_and_reuses_project_rules_without_writes(client):
    before = client.db_path.read_bytes()
    client.cookies.set("seed_admin", "ok")
    overview = client.get("/api/haln").json()
    assert overview["total_items"] == 3
    assert overview["by_status"] == {"failed": 1, "candidate": 1, "listed": 1}
    assert overview["candidates_count"] == 1
    assert len(overview["decisions"]) == 1
    assert client.get("/api/haln/pool").json()["items"][-1]["evidence_tiers"] == {"measured": 7, "review": 9}
    staging = client.get("/api/haln/staging").json()["items"]
    assert len(staging) == 1 and staging[0]["overall"] == "from-project-rules"
    assert len(client.get("/api/haln/creative").json()["items"]) == 1
    assert client.get("/api/haln/creative/pack").json()["items"] == [{"item_id": 1, "count": 3}]
    order = client.get("/api/haln/orders/opaque-token").json()["order"]
    assert order["total_pence"] == 1299 and order["items"] == [] and order["address"] == {}
    assert len(client.get("/api/haln/orders").json()["items"]) == 1
    assert client.db_path.read_bytes() == before
    with sqlite3.connect(client.db_path) as conn:
        assert "reference" not in {r[1] for r in conn.execute("PRAGMA table_info(orders)")}
    db = api._db()
    conn = next(db)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM items")
    db.close()


def test_event_filters_are_parameterized_and_item_history_is_scoped(client):
    client.cookies.set("seed_admin", "ok")
    filtered = client.get("/api/haln/events?type=item.added").json()
    assert [e["id"] for e in filtered["items"]] == [3, 1]
    assert len(client.get("/api/haln/events?type=%27%20OR%201=1").json()["items"]) == 3
    detail = client.get("/api/haln/item/1").json()
    assert detail["item"]["title"] == "Bottle"
    assert [e["item_id"] for e in detail["events"]] == [1]
    assert client.get("/api/haln/item/999").status_code == 404
    assert client.get("/api/haln/orders/not-an-order").status_code == 404
    assert client.post("/api/haln/pool", json={"status": "live"}).status_code == 405


def test_only_recorded_files_inside_assets_are_served(client):
    client.cookies.set("seed_admin", "ok")
    assets = client.root / "assets"
    assets.mkdir()
    image = assets / "bottle.png"
    image.write_bytes(b"recorded image")
    outside = client.root / "private.txt"
    outside.write_text("private")
    (assets / "escape.png").symlink_to(outside)
    records = [{"path": str(image)}, {"path": str(outside)},
               {"path": str(assets / "escape.png")}, {"path": str(image), "dry_run": True}]
    with sqlite3.connect(client.db_path) as conn:
        conn.execute("UPDATE items SET data = ? WHERE id = 1", (json.dumps({"creative_assets": records}),))
    assert client.get("/api/haln/assets/1/0").content == b"recorded image"
    for index in (-1, 1, 2, 3, 99):
        assert client.get(f"/api/haln/assets/1/{index}").status_code == 404


def test_missing_database_does_not_get_created(client, monkeypatch):
    missing = client.root / "missing.db"
    monkeypatch.setenv("HALN_DB", str(missing))
    client.cookies.set("seed_admin", "ok")
    assert client.get("/api/haln").status_code == 503
    assert not missing.exists()


def test_parallel_reads_survive_fastapi_worker_handoffs(client):
    async def read():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://test",
                                     cookies={"seed_admin": "ok"}) as c:
            responses = await asyncio.gather(*(c.get("/api/haln/pool") for _ in range(48)))
            return [r.status_code for r in responses]
    statuses = asyncio.run(read())
    assert statuses == [200] * 48
