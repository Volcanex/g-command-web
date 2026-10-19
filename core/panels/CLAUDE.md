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
  they stay current. Clients never format dates themselves.

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
Any Chip in a `line` or a row may carry a `tip`.

Action (one per row, a tick): `{"label": "Mark done", "method": "PATCH",
"path": "/api/brain/api/todos/<slug>", "body": {...}, "error": {"title": "Not saved", "desc": "..."}}`. The client sends
`body` as JSON to `path` with its credentials, then refetches the panel. The
server decides the body (a recurring todo ticks one date, a one-off closes),
so no client knows todo semantics.

## Manifest (version 1)
```json
{
  "v": 1,
  "name": "G-Command",
  "sections": [
    {"title": "Dash", "entries": [
      {"slug": "home", "label": "Life", "icon": "sun-horizon",
       "panels": ["calendar", "brief", "tasks", "money"],
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
web page. A page opts in by listing `panels` in its `config.json`. For the
dashes that list must match the order of the `seed:panel-*` tokens in its
`content.html` (a test holds them together). The web layout still places
the columns.

## Implementation

Each panel module exposes `build(ctx)`. The shared `builder` wrapper fills
the panel envelope and turns failures into the panel's own error state.
`context.py` supplies `ctx.get(path)` and a request-time London `ctx.now`.
It reads Brain directly and calls the existing local API functions with
the authenticated request. Tests inject fixture contexts with the same
interface. `helpers.py` owns text flattening, date copy and chips.
`manifest.py` mirrors the compiler's navigation rules without importing
the compiler or mounting a route.
