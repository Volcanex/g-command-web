# core/panels: the shared panel contract

One panel is one view-model built here, in Python, and rendered by every
client: the web dash (`pages/full-dash/panels/kit.html`, generic renderer),
the iPhone app and the Mac app (g-command-apple, `GCommandKit`). What a
panel shows (which items, in what order, which words, which tone) is decided
here and nowhere else. Clients only lay it out. A client that filters, sorts
or writes its own copy for a panel is a bug: that logic drifts.

## Routes
- `GET /api/panels/{name}`: one panel, the shape below. Auth as every
  other route (`core/auth.cookie_ok`). Upstream failure is still a 200 with
  `state: "error"` and the panel's own `message`, so a client never shows
  raw upstream text.
- `GET /api/app/manifest`: navigation and which pages are panel pages.
  Built from `pages/*/config.json`, see Manifest.

## Panel (version 1)
```json
{
  "v": 1,
  "id": "money",
  "title": "Money",
  "icon": "wallet",
  "link": "/todos",
  "link_label": "Open todos",
  "meta": "3 open, 1 late",
  "state": "ok",
  "message": "",
  "refresh": 300,
  "blocks": []
}
```
- `icon`: a Phosphor regular name (the web vendors Phosphor). Native
  clients map names to SF Symbols in one table, with a fallback.
- `link` and every row `link` are command paths (`/note/...`, `/system`,
  `/tickets?project=p&id=t`). A client opens a path natively when the
  manifest says that page is a panel page, otherwise in its signed-in web
  view.
- `state`: `ok`, `empty` (show `message` in place of the blocks) or
  `error` (show `message`, keep retrying every `refresh` seconds).
- `refresh`: seconds between polls while the panel is visible.
- Times in copy are computed at request time ("Checked 2 min ago",
  "Tue 21 Oct", "2 days late") in the instance timezone. Clients poll, so
  they stay current. Clients never format dates themselves. Feeds outside panels
  (alerts, devices) carry epoch times, and there the client shows a
  relative, ticking time.

## Blocks
Every block has `type`. Unknown types are skipped by clients, so a new type
can ship server first.

- `rows`: `{"type": "rows", "title": "Today"?, "count": 2?, "empty": "Nothing planned"?, "rows": [Row]}`.
  A titled `rows` block is a group (the calendar's days). `count` is drawn
  beside the title as a muted number, never baked into `title`. `empty` is
  shown when `rows` is empty.
- Any block may carry `"aside": true`: it belongs to the panel's secondary
  column (the calendar's next days). A wide layout puts aside blocks beside
  the rest, a narrow one after them.
- `line`: `{"type": "line", "items": [Chip]}`, one wrapping line of short
  facts (`All 41 services up`, `h 30/30`).
- `meter`: `{"type": "meter", "label": "Disk", "value": 71, "max": 100,
  "warn_at": 85, "danger_at": 95, "text": "71% used, 40 GB free"}`.
- `meter`: optional `"tone"` colours the text and fill when the server
  wants a tone other than the thresholds give. A meter can be a small
  card (a compute quota): optional `badge` (Chip after the label, the
  temperature) and `sub` ([Chip], one line under the bar, first item at
  the start and the rest at the end: `Resets Sun 25 Oct, 01:00` and
  `in 5d 4h`). Head line: label, badge, bar, `text`.
- `bullets`: `{"type": "bullets", "items": [{"text": "...", "label": "Money"?, "link": "/..."?}]}`,
  plain sentences (the brief). `label` is a short bold lead before the text.
- `detail`: `{"type": "detail", "text": "..."}`, small secondary text in
  the muted tone (a caveat, a source, small print). Plain text, no markup;
  line breaks are kept.
- `image`: `{"type": "image", "url": "/api/voice/files/<id>", "alt": "..."?,
  "width": 1200?, "height": 800?}`. `url` is always a path on this server
  behind the same cookie, never an outside URL; a client fetches it with its
  credentials. Drawn full width at its aspect ratio (from `width`/`height`
  when given), tap to view full size.
- `fold`: `{"type": "fold", "title": "Details", "open": false, "blocks": [Block]}`,
  a collapsible section: a disclosure row with `title`, its blocks shown when
  open. `open` is the initial state. One level only: a fold holds no fold.
- `panel`: `{"type": "panel", "name": "calendar", "title", "icon", "link",
  "link_label", "meta", "state", "message", "blocks"}`, a whole panel inside
  another surface (a chat reply), drawn as a card with the panel's own header
  and blocks. Its fields are the panel envelope above. Voice emits only
  `{"type": "panel", "name"}`; the server fills the rest from `build(name)`.

Row:
```json
{
  "id": "stable-id",
  "title": "Pay council tax",
  "detail": "secondary text"?,
  "lead": Chip?,
  "trail": Chip?,
  "link": "/note/..."?,
  "done": false?,
  "struck": false?,
  "accent": "warn"?,
  "title_tone": "danger"?,
  "marks": [Chip]?,
  "action": Action?
}
```
- `accent`: a tone drawn as a thin stripe at the row's leading edge
  (priority, category). `title_tone` colours the title. `marks` are small
  chips after the title (vital, starred), in order.

Chip: `{"text": "Down", "tone": "danger", "badge": true?, "icon": "star"?, "tip": "..."?}`.
Tones: `ok`, `warn`, `danger`, `accent`, `muted`, `plain`, and `chart-1`
to `chart-6` for categories (g-design's `--chart-*` tokens, the same six
in every client). `badge` draws a
pill, else coloured text. `icon` is a Phosphor name drawn before the text
(a mark with an icon and empty text is icon only). `tip` is the longer
explanation: a tooltip on the web, a long-press or help popover natively.
Any Chip in a `line` or a row may carry a `tip`. In a `line`, chips with `"end": true` sit together
at the end of the line (the health panel's host counts) and wrap as one group.

Action (one per row, a tick): `{"label": "Mark done", "method": "PATCH",
"path": "/api/brain/api/todos/<slug>", "body": {...}, "error": {"title": "Not saved", "desc": "..."}}`. The client sends
`body` as JSON to `path` with its credentials, then refetches the panel. The
server decides the body (a recurring todo ticks one date, a one-off closes),
so no client knows todo semantics.

## Chat replies (Voice, app session)
Voice's app replies carry these same blocks, so a reply looks like the dash.
`pages/voice/api.py` is the route, `brain-tools/voice/blocks.py` checks what
the model emits against the shapes above and drops the rest (a new type is
added here first, then there). A reply row may carry an `action` only when
server code built it (brain-tools `voice/todos.py`, through
`blocks.clean(actions=True)`), never when the model wrote the row: the model's
row actions are dropped. A live `panel` keeps its own ticks. The apps draw a
todo row's action and offer the web Day view's changes on it. Contract:

- `POST /api/voice/chat` `{"message", "session": "web"|"app", "budget"?:
  {"lines", "chars_per_line"}, "attachments"?: [upload id, at most 4]}` →
  web: `{"reply"}` (unchanged), app: `{"reply", "blocks": [Block]}`.
  `budget` is a soft guide for the app session only: the visible chat area
  with the keyboard up.
- `POST /api/voice/chat/stream`, same body, app only: NDJSON lines
  `{"t": "delta", "text"}` (append to the bubble), `{"t": "tool", "name"}`,
  then `{"t": "done", "reply", "blocks", "tools", "ms"}` (replace the
  bubble's text with `reply`, draw `blocks`) or `{"t": "error", "error"}`.
- `POST /api/voice/upload`, raw body, `Content-Type` the file's own, optional
  `X-Filename` (URL-encoded) → `{"id", "kind": "image"|"file", "name",
  "content_type", "size", "url"}`. Images JPEG/PNG/WebP/GIF up to 8 MB (send
  HEIC as JPEG), files PDF/text/Markdown/CSV/JSON up to 20 MB. 413 over,
  415 other types. `GET /api/voice/files/{id}` serves it behind the cookie.
- `GET /api/voice/history?session=app&limit=100` → `{"session", "turns":
  [{"ts", "role", "text", "blocks"?, "attachments"?: [upload]}]}`. A
  `panel` in an old turn comes back as a one-row link to the page, not live
  data.

## Manifest (version 1)
```json
{
  "v": 1,
  "name": "G-Command",
  "sections": [
    {"title": "Dash", "entries": [
      {"slug": "home", "label": "Life", "icon": "sun-horizon",
       "panels": ["calendar", "brief", "tasks", "money"], "layout": {...},
       "tabs": [{"slug": "...", "label": "...", "panels": [...]?}]}
    ]}
  ],
  "panels": {"calendar": {"title": "Calendar", "icon": "calendar-blank"}}
}
```
Sections and entries follow the web sidebar exactly (`build_nav_html` and
`build_subnavs` in `compile.py`: `nav: true` pages grouped by `nav_section`,
tabs from `tabs` groups). An entry or tab with `panels` is a panel page:
native clients render those panels in that order. Without `panels` it is a
web page. A page opts in with a `layout` in its `config.json`: the manifest
gives its reading order as `panels` and the layout itself, normalised, as
`layout`.

## Layout (the one source for dash placement)
A panel page's `config.json` `layout` decides where its panels sit on a
desktop window, for every client. The web compiles it into the dash markup
and placement CSS (`core/panels/layout.py`, the `<!-- seed:dash-layout -->`
token, so a dash's `content.html` is only that token and the kit). The Mac
app lays the same grid out natively. The iPhone, and any window under 900 by
560, shows one scrolling column in reading order. `layout_note` beside it
says why the page is laid out that way.

```json
"layout": {
  "top": ["compute"],
  "columns": [
    {"width": 2, "min": 0, "items": [
      {"panel": "calendar", "grow": 3},
      {"row": ["tasks", "money", "brief"], "grow": 2}]},
    {"width": 1, "min": 320, "items": [
      {"panel": "health", "fit": true},
      {"panel": "tickets", "fit": true, "max": 22},
      "crons"]}
  ]
}
```
- `top`: panels across the full width above the columns, at their natural
  height.
- `columns`: side by side, `width` a share of the width (CSS `fr`), `min`
  the narrowest it may get, in points.
- An item is a panel name (fills, weight 1), `{"panel"}` or `{"row": [...]}`
  (panels side by side, equal widths). The column fills the window's height:
  `grow` items share what is left by weight, `fit` items take their natural
  height and do not shrink, `shrink: true` lets a `fit` item shrink and
  scroll when the column runs short, and `max` caps an item at a percentage
  of the column's height. A panel's body scrolls inside it.
- Reading order is `top`, then each column top to bottom, a row left to right.
- The manifest form (`layout.normalise`) writes every item as an object and
  every column with `width` and `min`. Clients skip keys they do not know.
- `tests/test_dash_layout.py` is the gate: no hand-placed dash markup, no
  `panels` list beside a layout, every panel once, and the manifest serves
  each layout.

## Implementation

Each panel module exposes `build(ctx)`. The shared `builder` wrapper fills
the panel envelope and turns failures into the panel's own error state.
`context.py` supplies `ctx.get(path)` and a request-time London `ctx.now`.
It reads Brain directly and calls the existing local API functions with
the authenticated request. Tests inject fixture contexts with the same
interface. `helpers.py` owns text flattening, date copy and chips.
`manifest.py` mirrors the compiler's navigation rules without importing
the compiler or mounting a route.
