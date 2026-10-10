"""g-admin: reference server for the g-admin overlay contract.

Drop-in FastAPI router implementing the tickets API described in
`agents/g-admin-contract.md`: an admin bar, annotate mode and edit mode
for any g project, backed here by tickets that a baking agent later
applies to source. **Nothing in this file writes to project source**:
`overrides.css` is an ephemeral reapply layer, not a build step.

Wiring into a seed-family project (g-command-web, g-site, or
anything born from the seed template): copy this file to
`core/api/gadmin.py`. Seed's importlib discovery
(`server.py:discover_apis`) auto-mounts any `core/api/{name}.py` that
exports `router` at `/api/{name}`, so it lands at `/api/gadmin` with no
manual registration. See the package `CLAUDE.md` for the full wiring
recipe (env vars, overrides `<link>`, vendoring the client assets).

The auth model has two tiers, deliberately unequal:

- **Cookie (full)**: the human admin session. Tries
  `core.api.admin.is_admin`/`require_admin` first (the seed pattern) so
  a seed-family project needs zero config. A non-seed FastAPI app sets
  `gadmin.GADMIN_VERIFY = your_is_admin(request) -> bool` before the
  router is mounted. Full auth can do everything: create tickets, edit
  notes, change status, reply.
- **Token (`X-Gadmin-Token`, read + status-only)**: for machine readers
  (g-command-web's tickets panel, a baking agent) that aren't running
  inside the project's own cookie session. Checked against `GADMIN_TOKEN`
  (env var, value lives in the instance passport) with
  `hmac.compare_digest`. Grants GET everywhere and PATCH, but a
  token-authenticated PATCH may only carry `status` (+ an optional
  `reply` describing why), never `note`, and never POST /tickets. This
  is the contract's line, not an implementation detail: a leaked token
  can close tickets and leave a paper trail, it can't rewrite one or
  spawn new ones.

Storage is one SQLite file, `var/gadmin.db` relative to the project
root (created on first use). `drawing` (a PNG data URL, can run to
1.5MB) is excluded from list queries. Poker's tickets panel learned
that the hard way when drawings made the list endpoint crawl.
"""

from __future__ import annotations

import hmac
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

router = APIRouter()

STATUSES = ("open", "baked", "dismissed")
SCOPES = ("page", "site")
KINDS = ("edit", "bug", "visual", "content", "idea")
SEVERITIES = ("critical", "major", "minor", "polish")
SOURCES = ("human", "agent")

# Per-element HTML snippet cap and the drawing size cap, both lifted
# straight from the contract's ticket schema ("html <=10k chars",
# "drawing ... <=1.5MB"). Over-cap is a 400, not a silent truncation:
# unlike baseline's annotate flow this contract's schema has no
# `truncated` flag to hang a partial snapshot off, so the filer (the
# client, which already enforces these caps before sending) decides
# what to trim, we never cut blind.
MAX_ELEMENT_HTML = 10_000
MAX_DRAWING_CHARS = 1_500_000
MAX_NOTE_CHARS = 20_000
MAX_REPLY_CHARS = 20_000

# One ticket per second, project-wide. Not per-IP: this is an internal
# admin tool behind an auth gate already; the point is to absorb a
# double-click on the annotate button (poker's stuck-button rule), not
# to defend against abuse.
_RATE_SECONDS = 1.0
_last_create_at = 0.0


# ---------------------------------------------------------------- auth --

# Non-seed FastAPI apps set this before mounting the router:
#   import gadmin; gadmin.GADMIN_VERIFY = lambda request: my_admin_check(request)
GADMIN_VERIFY: Callable[[Request], bool] | None = None

# Seed's own admin module, imported opportunistically. A seed-family
# project has `core/api/admin.py` on the path already (server.py adds
# the project root to sys.path when it mounts routers); a bare FastAPI
# app used only for tests won't, and that's fine: we fall back to
# GADMIN_VERIFY, and if that's unset too, cookie auth always denies.
try:
    from core.api.admin import is_admin as _seed_is_admin
except ImportError:
    _seed_is_admin = None


def _is_admin_cookie(request: Request) -> bool:
    if GADMIN_VERIFY is not None:
        return bool(GADMIN_VERIFY(request))
    if _seed_is_admin is not None:
        return bool(_seed_is_admin(request))
    return False


def _token_ok(request: Request) -> bool:
    expected = os.environ.get("GADMIN_TOKEN")
    if not expected:
        return False
    supplied = request.headers.get("x-gadmin-token")
    if not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


# Auth levels, low to high. TOKEN is deliberately not "below" FULL in a
# linear read/write sense: it's a narrower slice (GET + PATCH-status),
# not a weaker version of FULL, but ordering them this way keeps the
# common `level == NONE` / `level != FULL` checks readable.
NONE, TOKEN, FULL = 0, 1, 2


def _auth_level(request: Request) -> int:
    if _is_admin_cookie(request):
        return FULL
    if _token_ok(request):
        return TOKEN
    return NONE


def _require_read(request: Request) -> int:
    level = _auth_level(request)
    if level == NONE:
        raise HTTPException(401, "admin only")
    return level


# ------------------------------------------------------------- storage --


def _project_root() -> Path:
    """Mirrors seed's `core/api/admin.py` convention: three parents up
    from this file's on-disk location once it's copied to
    `core/api/gadmin.py` in a consumer project."""
    return Path(__file__).resolve().parent.parent.parent


def _db_path() -> Path:
    override = os.environ.get("GADMIN_DB_PATH")
    if override:
        return Path(override)
    return _project_root() / "var" / "gadmin.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    page TEXT NOT NULL,
    viewport TEXT NOT NULL,
    elements TEXT NOT NULL,
    edits TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    drawing TEXT,
    replies TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,
    baked_by TEXT
)
"""

# Columns used everywhere except the single-ticket GET: drawings can
# run to 1.5MB each and have no business riding along on a list.
_LIST_COLUMNS = (
    "id, created_at, updated_at, status, scope, kind, severity, page, "
    "viewport, elements, edits, note, replies, source, baked_by"
)


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_ticket(row: sqlite3.Row, include_drawing: bool) -> dict:
    ticket = {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "status": row["status"],
        "scope": row["scope"],
        "kind": row["kind"],
        "severity": row["severity"],
        "page": json.loads(row["page"]),
        "viewport": json.loads(row["viewport"]),
        "elements": json.loads(row["elements"]),
        "edits": json.loads(row["edits"]),
        "note": row["note"],
        "replies": json.loads(row["replies"]),
        "source": row["source"],
        "baked_by": row["baked_by"],
    }
    if include_drawing:
        ticket["drawing"] = row["drawing"] if "drawing" in row.keys() else None
    return ticket


# ------------------------------------------------------------- models --


class PageInfo(BaseModel):
    url: str = ""
    path: str = ""
    title: str = ""


class ViewportInfo(BaseModel):
    w: int = 0
    h: int = 0
    dpr: float = 1
    theme: str = "dark"


class Rect(BaseModel):
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0


class ElementSnapshot(BaseModel):
    selector: str = Field(..., max_length=1000)
    dom_path: str = ""
    html: str = Field("", max_length=MAX_ELEMENT_HTML)
    rect: Rect = Field(default_factory=Rect)


class Edit(BaseModel):
    selector: str
    prop: str
    from_value: str | None = Field(None, alias="from")
    to: str | None = None
    token_from: str | None = None
    token_to: str | None = None

    model_config = {"populate_by_name": True}


class TicketCreate(BaseModel):
    scope: Literal["page", "site"]
    kind: Literal["edit", "bug", "visual", "content", "idea"]
    severity: Literal["critical", "major", "minor", "polish"]
    page: PageInfo = Field(default_factory=PageInfo)
    viewport: ViewportInfo = Field(default_factory=ViewportInfo)
    elements: list[ElementSnapshot] = Field(default_factory=list)
    edits: list[Edit] = Field(default_factory=list)
    note: str = Field("", max_length=MAX_NOTE_CHARS)
    drawing: str | None = None
    source: Literal["human", "agent"] = "human"


class TicketPatch(BaseModel):
    status: Literal["open", "baked", "dismissed"] | None = None
    reply: str | None = Field(None, max_length=MAX_REPLY_CHARS)
    note: str | None = Field(None, max_length=MAX_NOTE_CHARS)


# ---------------------------------------------------------- /verify --


@router.get("/verify")
def verify(request: Request):
    if not _is_admin_cookie(request):
        raise HTTPException(401, "admin only")
    return {"admin": True}


# ---------------------------------------------------------- /tickets --


@router.get("/tickets")
def list_tickets(
    request: Request,
    status: Literal["open", "baked", "dismissed"] | None = Query(None),
):
    _require_read(request)
    conn = _get_conn()
    try:
        sql = f"SELECT {_LIST_COLUMNS} FROM tickets"
        params: tuple = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return {"tickets": [_row_to_ticket(r, include_drawing=False) for r in rows]}


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketCreate, request: Request):
    level = _auth_level(request)
    if level != FULL:
        raise HTTPException(401 if level == NONE else 403, "cookie auth only")

    global _last_create_at
    now_monotonic = time.monotonic()
    if now_monotonic - _last_create_at < _RATE_SECONDS:
        raise HTTPException(429, "one ticket per second, try again shortly")

    if body.drawing is not None and len(body.drawing) > MAX_DRAWING_CHARS:
        raise HTTPException(400, f"drawing exceeds {MAX_DRAWING_CHARS} chars")

    _last_create_at = now_monotonic
    now = _now()
    edits_json = json.dumps(
        [e.model_dump(by_alias=True) for e in body.edits]
    )
    conn = _get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO tickets (created_at, updated_at, status, scope, kind, "
            "severity, page, viewport, elements, edits, note, drawing, replies, "
            "source, baked_by) VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                now,
                now,
                body.scope,
                body.kind,
                body.severity,
                body.page.model_dump_json(),
                body.viewport.model_dump_json(),
                json.dumps([e.model_dump() for e in body.elements]),
                edits_json,
                body.note,
                body.drawing,
                json.dumps([]),
                body.source,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM tickets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    finally:
        conn.close()
    return _row_to_ticket(row, include_drawing=True)


def _fetch_full(conn: sqlite3.Connection, ticket_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "ticket not found")
    return row


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, request: Request):
    _require_read(request)
    conn = _get_conn()
    try:
        row = _fetch_full(conn, ticket_id)
    finally:
        conn.close()
    return _row_to_ticket(row, include_drawing=True)


@router.patch("/tickets/{ticket_id}")
def patch_ticket(ticket_id: int, body: TicketPatch, request: Request):
    level = _auth_level(request)
    if level == NONE:
        raise HTTPException(401, "admin only")
    if level == TOKEN and body.note is not None:
        raise HTTPException(403, "token auth may only change status (+ reply), not note")
    if body.status is None and body.reply is None and body.note is None:
        raise HTTPException(400, "nothing to update")

    conn = _get_conn()
    try:
        row = _fetch_full(conn, ticket_id)
        status = body.status if body.status is not None else row["status"]
        note = body.note if body.note is not None else row["note"]
        replies = json.loads(row["replies"])
        if body.reply is not None:
            replies.append(
                {
                    "at": _now(),
                    "by": "agent" if level == TOKEN else "human",
                    "text": body.reply,
                }
            )
        baked_by = row["baked_by"]
        if body.status == "baked" and row["status"] != "baked":
            baked_by = "agent" if level == TOKEN else "human"
        elif body.status is not None and body.status != "baked":
            baked_by = None

        conn.execute(
            "UPDATE tickets SET status=?, note=?, replies=?, baked_by=?, updated_at=? "
            "WHERE id=?",
            (status, note, json.dumps(replies), baked_by, _now(), ticket_id),
        )
        conn.commit()
        row = _fetch_full(conn, ticket_id)
    finally:
        conn.close()
    return _row_to_ticket(row, include_drawing=True)


# ------------------------------------------------------------- /brief --


def _render_brief(ticket: dict) -> str:
    lines = [
        f"# g-admin ticket #{ticket['id']} ({ticket['status']})",
        "",
        f"- **Scope:** {ticket['scope']}  **Kind:** {ticket['kind']}  "
        f"**Severity:** {ticket['severity']}  **Source:** {ticket['source']}",
        f"- **Page:** `{ticket['page'].get('path', '')}` "
        f"({ticket['page'].get('url', '')})"
        + (
            f' titled "{ticket["page"]["title"]}"'
            if ticket["page"].get("title")
            else ""
        ),
        f"- **Viewport:** {ticket['viewport'].get('w')}×{ticket['viewport'].get('h')} "
        f"@{ticket['viewport'].get('dpr')} ({ticket['viewport'].get('theme')})",
        f"- **Created:** {ticket['created_at']}  **Updated:** {ticket['updated_at']}",
    ]

    lines += ["", "## Note", "", ticket["note"] or "_(no note)_"]

    if ticket["elements"]:
        lines += ["", "## Elements", ""]
        for i, el in enumerate(ticket["elements"], 1):
            lines.append(f"### {i}. `{el.get('selector')}`")
            if el.get("dom_path"):
                lines.append(f"- dom_path: `{el['dom_path']}`")
            rect = el.get("rect") or {}
            if rect:
                lines.append(
                    f"- rect: x={rect.get('x')} y={rect.get('y')} "
                    f"w={rect.get('w')} h={rect.get('h')}"
                )
            if el.get("html"):
                lines += ["", "```html", el["html"], "```"]
            lines.append("")

    if ticket["edits"]:
        lines += [
            "## Edits",
            "",
            "| selector | prop | from | to | token from | token to |",
            "|---|---|---|---|---|---|",
        ]
        for e in ticket["edits"]:
            lines.append(
                f"| `{e.get('selector', '')}` | {e.get('prop', '')} | "
                f"{e.get('from', '') or ''} | {e.get('to', '') or ''} | "
                f"{e.get('token_from') or ''} | {e.get('token_to') or ''} |"
            )
        lines.append("")

    if ticket["replies"]:
        lines += ["## Replies", ""]
        for r in ticket["replies"]:
            lines.append(f"- **{r.get('by')}** ({r.get('at')}): {r.get('text')}")
        lines.append("")

    lines += [
        "---",
        f"Baked by: {ticket['baked_by'] or '(not yet baked)'}",
        "PATCH this ticket's status to `baked` with a reply describing the "
        "commit once the change lands in source.",
    ]
    return "\n".join(lines)


@router.get("/tickets/{ticket_id}/brief", response_class=Response)
def ticket_brief(ticket_id: int, request: Request):
    _require_read(request)
    conn = _get_conn()
    try:
        row = _fetch_full(conn, ticket_id)
    finally:
        conn.close()
    ticket = _row_to_ticket(row, include_drawing=False)
    return Response(content=_render_brief(ticket), media_type="text/markdown")


# --------------------------------------------------------- overrides --


@router.get("/overrides.css")
def overrides_css():
    headers = {"Cache-Control": "no-store"}
    if os.environ.get("GADMIN_REAPPLY") != "1":
        return Response(content="", media_type="text/css", headers=headers)

    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, edits FROM tickets WHERE status = 'open'"
        ).fetchall()
    finally:
        conn.close()

    chunks = []
    for row in rows:
        edits = json.loads(row["edits"] or "[]")
        rules = []
        for e in edits:
            selector = (e.get("selector") or "").strip()
            prop = (e.get("prop") or "").strip()
            value = e.get("token_to")
            value = f"var({value})" if value else e.get("to")
            if not selector or not prop or not value:
                continue
            rules.append(f"{selector} {{ {prop}: {value}; }}")
        if rules:
            chunks.append(f"/* g-admin ticket #{row['id']} */\n" + "\n".join(rules))

    css = "\n\n".join(chunks) + ("\n" if chunks else "")
    return Response(content=css, media_type="text/css", headers=headers)
