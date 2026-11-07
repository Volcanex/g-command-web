"""HALN admin data, read-only over gcommerce's live pool.

HALN_ROOT selects the gcommerce checkout; HALN_DB overrides its pool database.
The project's pure evidence/readiness/prompt functions remain the source of rules.
No GPool is constructed: its constructor performs schema writes.
"""
import importlib
import json
import logging
import os
import sqlite3
import sys
import time
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from core.auth import cookie_ok
from core.instance import sibling


def _auth(request: Request):
    if not cookie_ok(request.cookies):
        raise HTTPException(401, "admin only")


router = APIRouter(tags=["haln"], dependencies=[Depends(_auth)])
VISIBLE = ("evidence_mined", "floor_verified", "listed", "live")
EVENT_TYPES = ("item.added", "item.claimed", "item.released", "item.failed",
               "item.data_updated", "item.reaped")


def _root():
    return Path(os.environ.get("HALN_ROOT") or sibling("gcommerce"))


@lru_cache
def _module(name):
    source = str(_root() / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    return importlib.import_module("gcommerce." + name)


def _db():
    path = Path(os.environ.get("HALN_DB") or _root() / "data/pool.db").resolve()
    try:
        # FastAPI can enter, use and close a request's connection on different workers.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                     timeout=5, check_same_thread=False)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("BEGIN")
            yield conn
    except sqlite3.Error:
        logging.getLogger(__name__).exception("HALN database read failed")
        raise HTTPException(503, "HALN data could not be read. Try again.") from None


def _decode(row):
    out = dict(row)
    for key in ("data", "address_json", "items_json"):
        if key in out:
            out[key.removesuffix("_json")] = json.loads(out.pop(key))
    return out


def _items(conn):
    return [_decode(r) for r in conn.execute("SELECT * FROM items ORDER BY id DESC")]


def _item(conn, item_id):
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "This item is no longer in the HALN pool.")
    return _decode(row)


def _asset_path(asset):
    if asset.get("dry_run"):
        return None
    path = asset.get("path")
    if asset.get("kind") == "turntable" and asset.get("frames_dir"):
        path = str(Path(asset["frames_dir"]) / "frame_01.jpg")
    if not path:
        return None
    path = Path(path).resolve()
    if not path.is_relative_to((_root() / "assets").resolve()) or not path.is_file():
        return None
    return path


def _present(item):
    data = item["data"]
    item["title"] = data.get("title") or item["source_key"]
    item["shop_visible"] = item["status"] in VISIBLE
    item["evidence_tiers"] = _module("pool.evidence").tier_counts(data)
    for i, asset in enumerate(data.get("creative_assets") or []):
        path = _asset_path(asset)
        asset["url"] = f"/api/haln/assets/{item['id']}/{i}" if path else None
        asset["is_video"] = bool(path and path.suffix.lower() in (".mp4", ".webm", ".mov"))
    return item


def _events(conn, event_type=None, item_id=None, limit=100):
    clauses, params = [], []
    if event_type in EVENT_TYPES:
        clauses.append("event_type = ?")
        params.append(event_type)
    if item_id is not None:
        clauses.append("item_id = ?")
        params.append(item_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return [_decode(r) for r in conn.execute(
        "SELECT * FROM events" + where + " ORDER BY ts DESC, id DESC LIMIT ?", (*params, limit))]


@router.get("")
def overview(conn=Depends(_db)):
    items = _items(conn)
    by_status = {}
    for item in items:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
    now = time.time()
    decisions = [i for i in items if i["data"].get("fulfilment_status") in ("rfq_pending", "unresolved")]
    return {"by_status": by_status, "total_items": len(items),
            "locked_items": sum(bool(i.get("locked_until") and i["locked_until"] > now) for i in items),
            "failed_items": by_status.get("failed", 0), "decisions": [_present(i) for i in decisions],
            "candidates_count": sum(i["status"] == "candidate" and bool(i["data"].get("graduation_requirement")) for i in items),
            "last_events": _events(conn, limit=5), "now": now}


@router.get("/pool")
def pool(conn=Depends(_db)):
    return {"items": [_present(i) for i in _items(conn)]}


@router.get("/decisions")
def decisions(conn=Depends(_db)):
    return {"items": [_present(i) for i in _items(conn)
                      if i["data"].get("fulfilment_status") in ("rfq_pending", "unresolved")]}


@router.get("/staging")
def staging(conn=Depends(_db)):
    rules = _module("store.staging")
    items = []
    for item in _items(conn):
        if item["status"] not in VISIBLE:
            continue
        criteria = rules.readiness(item)
        items.append({**_present(item), "criteria": criteria, "overall": rules.overall(criteria)})
    return {"items": items}


@router.get("/creative")
def creative(conn=Depends(_db)):
    return {"items": [_present(i) for i in _items(conn) if i["data"].get("creative_briefs")]}


@router.get("/creative/pack")
def prompt_pack(conn=Depends(_db)):
    items = _items(conn)

    class ReadPool:
        def list_items(self, **kwargs):
            return items

        def get_item(self, item_id):
            return next((i for i in items if i["id"] == item_id), None)

    try:
        return {"items": _module("content.prompt_pack").build_entries(ReadPool())}
    except RuntimeError:
        raise HTTPException(409, "HALN's prompt checks blocked this pack. Review the creative briefs before trying again.") from None


@router.get("/item/{item_id}")
def detail(item_id: int, conn=Depends(_db)):
    return {"item": _present(_item(conn, item_id)), "events": _events(conn, item_id=item_id, limit=200)}


@router.get("/events")
def events(type: str = "", conn=Depends(_db)):
    return {"items": _events(conn, event_type=type), "types": EVENT_TYPES,
            "active_type": type if type in EVENT_TYPES else ""}


@router.get("/orders")
def orders(conn=Depends(_db)):
    return {"items": [_decode(r) for r in conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200")]}


@router.get("/orders/{token}")
def order_detail(token: str, conn=Depends(_db)):
    row = conn.execute("SELECT * FROM orders WHERE token = ?", (token,)).fetchone()
    if row is None:
        raise HTTPException(404, "This order could not be found. Return to the orders list.")
    return {"order": _decode(row)}


@router.get("/assets/{item_id}/{index}")
def asset(item_id: int, index: int, conn=Depends(_db)):
    assets = _item(conn, item_id)["data"].get("creative_assets") or []
    path = _asset_path(assets[index]) if 0 <= index < len(assets) else None
    if path is None:
        raise HTTPException(404, "This creative file is not available.")
    return FileResponse(path)
