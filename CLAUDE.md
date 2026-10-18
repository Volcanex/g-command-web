# g-command-web

Command center: the web UI for G-System. Ops dashboards, Brain
visualisations, service health. Each instance serves it on its own host.
Was `gcommand` until 2026-10-09. The systemd unit, manifest id, cookie
name and the `gcommand` compat symlink on h keep the old name.

**Owner:** Gabriel Penman
**Role in supersystem:** consumes gp-core (topology) + g-brain (`/api/*`). Renders only and holds no data of its own.
**Licence:** GNU AGPL v3.0 only (`LICENSE`), open source. Vendored fonts and icons are listed in `THIRD_PARTY_NOTICES`.

## What it does
- Three dashes from one set of panels (`pages/full-dash/panels/`): `/home` the life dash (calendar for today and the week, todos, money, a one-line-per-bullet brief), `/ops` the system dash (compute quotas with reset times, health showing only what is down, tickets, crons, disk) and `/full-dash`, both at once with nothing below the fold at 1280x800, where `/` lands so a down service is never a tab away.
- The sidebar is three short sections (Dash, Daily, Tools: Brain, Design, Files, Runners); everything else is a tab under one of those entries (System, Brain, Files) or under the setup wrench in the sidebar foot. Every old URL still serves.
- Renders the brain's graphs (notes, nerves, lineage, refs) by consuming the brain REST API at `BRAIN_API`.
- `/design`: the g-design reference (guideline and component cards) in an index beside a frame. `compile.py` copies the checkout at `G_DESIGN_DOCS` (g-design's `apps/docs`) into `output/assets/design/` and indexes the cards by their `@dsCard` comment, so a g-design change shows here on the next restart.
- `/graph`: the brain's wikilink graph in 3D (3d-force-graph, WebGL).
- `/system`: live service topology + health, from the brain L5 status index.
- `/projects`: project gallery: a card per `manifest.projects[]` (thumbnail, health, gcore compliance, deps, lineage, last commit). Pure renderer; the list is the manifest, so a new entry self-adds.
- `/calendar`: every dated brain todo, in four views over one fetch: **day** (one day full width, grouped starred/to do/settled, the triage view; steps to tomorrow and back), **month** (shape only: daily habits are counted on the date line rather than listed, because a month grid should show what is *different* about a day; a cell click opens that day in the day view), **week** (seven columns, nothing truncated, full width), **agenda** (four weeks forward from today, empty days omitted, the phone view). A star toggles `urgent`, which is triage; `vital` is set on the todo and drives the reminder ladder. Both sort to the top of their day, server-side, so every view agrees. Week and agenda re-sort chronologically: they show everything, so they read as a timeline, while the truncating views need the important things at the top of the cell.

  Two gotchas. Only the **regular** Phosphor weight is vendored here, so `ph-fill` renders an empty box: a starred row lost its star that way, and state has to be carried by colour. And the reminder ladder is shown short (`3 reminders, last 1 day before`) with the full list in a `data-tip`, because a five-rung vital ladder spelled out wrapped over three lines and buried the two facts worth reading. Recurrence is expanded server-side by `/api/todos/calendar`, which also carries overdue one-offs onto today rather than letting them vanish. Items show done (green, struck), failed (red, struck) or late, and vital ones carry a mark. The day panel ticks a single occurrence of a recurring todo without retiring the whole habit, and offers did-not-happen, tomorrow, next week and drop. Each item states the reminder ladder it will fire, so the page explains its own behaviour rather than leaving you to guess when ntfy pings.
- `/tickets`: every g-admin ticket across every project that speaks the contract, aggregated live via `core/api/gadmin_panel.py`. No local store; same pattern as `/system`. Deep link `/tickets?project=<id>&id=<ticket>` filters to the project and opens that ticket (the desktop app, g-command-mac, uses it); `project` alone just filters.
- `/levels`: g-levels (gates, charters, results, the candidate-gate backlog and the share of Gabriel's prompts per level), read live from the g-levels checkout through `pages/levels/api.py`. Grading a verdict runs `glevels grade`. See `pages/levels/CLAUDE.md`.
- `/runners`: the g-runner device fleet (devices online or stale, the queue, recent results with runner page rAF frame times and posted values), read live through `core/api/runners.py`, which holds the g-runner token server-side. Read only, refreshes every 5 s while visible.
- Whole site is password-gated (one shared password, once per browser session).

## Stack
gseed-app seed framework: static-first pages compiled by `compile.py`, served by FastAPI (`server.py`). Pages live in `pages/{slug}/` (`config.json` + `content.html`); API routers auto-discover from `core/api/*.py` and `pages/*/api.py`.

## Run
```
python3 compile.py && python3 server.py
```
Served on `127.0.0.1:$PORT` (default 8089), fronted by nginx. Deployed via the `gcommand` systemd unit on h.

## Gotchas
- Brain data is **not** local: every brain page fetches `${BRAIN_API}/api/*` from the browser. Nothing here reads the brain filesystem. `BRAIN_API` is the one place the origin is set: `compile.py` reads it from the environment, then from `.env` beside it (default `/api/brain`, this server's admin-gated proxy to the g-brain at `BRAIN_UPSTREAM`, trailing slash dropped), the shell writes it into `<meta name="brain-api">` and an inline head script copies that to `window.BRAIN_API`. Pages read the global and never name the host. It is baked in at compile time, so a change needs a recompile, which the unit's `ExecStartPre` runs on every restart. Set it in `.env` (the unit's `EnvironmentFile`). `OWNER_SITE_URL` (the owner's site, linked from the drawer and top bar, hidden when unset) `PUBLIC_HOST` (the host in the status line) and `MCP_URL` and `MCP_HEADLESS_URL` (the brain's MCP endpoints, quoted on the install and setup pages through `<!-- seed: -->` tokens) work the same way. compile.py takes only these keys and the `SEED_MANIFEST_*` ones from `.env`, so a compile by hand matches the one on restart.
- Auth is the whole-site gate in `server.py` (`_admin_gated`), not just `/admin/*`. Password comes from `ADMIN_PASSWORD`, set in this server's `.env` (one of the unit's `EnvironmentFile`s). It is a single shared secret, a placeholder until g-auth exists. The cookie it sets carries `ADMIN_COOKIE_VALUE`, a second secret with no default. `core/auth.py` is the one place that reads it and the cookie name: every router imports them from there, and the server refuses to start without the secret (set by the `zz-admin-secret.conf` drop-in from `/etc/g-secrets/gcommand-admin.env`).
- `/css`, `/js` and `/assets` are cached for a day (a week for vendor) without revalidating, so the shell's links are stamped `?v=<content hash>` by `stamp_shell_assets()` in `compile.py`. A file a page links itself, or one a stylesheet pulls in (the mask in `chrome.css`), is not stamped and can stay a day stale.
- Sibling checkouts are found by `core/instance.py`: an env var first (`GCORE_DIR`, `BRAIN_ROOT`, `COMPUTE_*`), then a checkout beside this one, new name before legacy (`gp-core` then `gcore`, `g-env` then `genv`). `scripts/refresh_projects.py` copies the instance lookup because the timer runs it without the app on `sys.path`.
- `/system` depends on the brain's `/api/status` snapshot, refreshed by the `brain-status.timer` on h.
- `/notes` also reads the brain's `/api/stale`, the rewrite review queue (notes whose dependency changed and that nobody re-checked), refreshed by `brain-verify.timer`. The block is hidden when the queue is empty and fails silently if the route is unreachable, so it can never break the notes table.
- `/projects` thumbnails + git/dep metadata live in gitignored `var/` (`var/shots/`, `var/projects-meta.json`), **not** `output/`: `compile.py` wipes `output/` on every restart, so anything there vanishes; `var/` survives and updates live without a gcommand restart. Thumbnails are served through the admin-gated `/api/projects/shot/{id}` route (not a public StaticFiles mount) so they stay behind the password. The `gcommand-projects.timer` (6-hourly, runs `scripts/refresh_projects.py` as root, since Chromium is in `/root/.cache`) regenerates them. The job shoots the public domain first, then falls back to the service's **internal `127.0.0.1:{port}`** (bypasses nginx basic-auth since it runs on-host); app-level login gates (302→/login) and non-HTML ports fail the no-redirect HTML pre-check and fall back to a placeholder tile.
- `/calendar` holds no recurrence logic of its own. `rrule` expansion and the reminder ladder both live in the brain's `brain_todos`, and the page renders what `/api/todos/calendar` returns. A second rrule parser in JavaScript would drift from the one the reminder outlet fires on, and the drift would show up as a reminder nobody can explain.
- `/tickets` (`core/api/gadmin_panel.py`) discovers which projects speak the g-admin contract by grouping the instance `manifest.json` services by `repo` and probing each one, cached in-process for 10 minutes. A project can 200 that probe without truly speaking the contract (a catch-all SPA route serving its index page, seen live against gdesign), so the probe also checks the payload shape, not just the status code. See `core/api/CLAUDE.md` for the full gotcha.

<!-- DOCS:START -->
| Path | Summary |
|------|---------|
| `agents/CLAUDE.md` | Agents: kickoff prompts for parallel integrations |
| `core/api/CLAUDE.md` | core/api: shared API routers |
| `core/templates/CLAUDE.md` | Templates: the shared shell |
| `pages/CLAUDE.md` | Pages |
| `pages/blog/CLAUDE.md` | blog |
| `pages/full-dash/CLAUDE.md` | full-dash |
| `pages/hours/CLAUDE.md` | hours |
| `pages/levels/CLAUDE.md` | levels |
| `pages/sessions/CLAUDE.md` | sessions: the terminal page |
| `pages/upload/CLAUDE.md` | upload |

_Auto-compiled 2026-10-18 23:53 UTC, 10 doc(s) found._
<!-- DOCS:END -->
