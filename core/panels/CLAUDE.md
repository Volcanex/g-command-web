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

- `rows`: `{"type": "rows", "title": "Today"?, "empty": "Nothing planned"?, "rows": [Row]}`.
  A titled `rows` block is a group (the calendar's days). `empty` is shown
  when `rows` is empty.
- `line`: `{"type": "line", "items": [Chip]}`, one wrapping line of short
  facts (`All 41 services up`, `h 30/30`).
- `meter`: `{"type": "meter", "label": "Disk", "value": 71, "max": 100,
  "warn_at": 85, "danger_at": 95, "text": "71% used, 40 GB free"}`.
- `bullets`: `{"type": "bullets", "items": [{"text": "...", "link": "/..."?}]}`,
  plain sentences (the brief).

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
  "action": Action?
}
```
Chip: `{"text": "Down", "tone": "danger", "badge": true?}`. Tones: `ok`,
`warn`, `danger`, `accent`, `muted`, `plain`. `badge` draws a pill, else
coloured text.

Action (one per row, a tick): `{"label": "Mark done", "method": "PATCH",
"path": "/api/brain/api/todos/<slug>", "body": {...}}`. The client sends
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
