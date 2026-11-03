# g-command-web

Command center: the web UI for G-System. Ops dashboards, Brain
visualisations, service health. Each instance serves it on its own host.
Served at system.gabrielpenman.com since 2026-10-30; command.gabrielpenman.com answers too, for devices paired to it. Was `gcommand` until 2026-10-09. The systemd unit, manifest id, cookie
name and the `gcommand` compat symlink on h keep the old name.

**Owner:** Gabriel Penman
**Role in supersystem:** consumes gp-core (topology) + g-brain (`/api/*`). Renders only and holds no data of its own.
**Licence:** GNU AGPL v3.0 only (`LICENSE`), open source. Vendored fonts and icons are listed in `THIRD_PARTY_NOTICES`.

## What it does
- Three dashes from one set of panels (`pages/full-dash/panels/`): `/home` the life dash (calendar for today and the week, todos, money, a one-line-per-bullet brief), `/ops` the system dash (compute quotas with reset times, health showing only what is down, tickets, crons, disk) and `/full-dash`, both at once with nothing below the fold at 1280x800.
- `/` is Home (`pages/index`): Life's agenda in a card (the brain's three deterministic lines, `core/panels/agenda.py`) above the full dash (the `full-dash` layout less Undated: calendar, money and the brief, which hides when it only repeats the agenda, beside health, compute, tickets and crons). No page head: the top bar says Home.
- The rail is the one navigation (g-design `skills/g-navigation`, the kit's `rail.js`): Home, Chat and Upload at the top, then the Life and System groups, then Work, Knowledge, Publish and Setup. Groups are disclosure rows, open by default, with an icon on every child; there are no hub pages (`/home`, `/ops` and `/brain` are 301s, `MOVED` in `server.py`). From 721px it is collapsed to icons, opens over the content on hover or focus, and its button beside the G pins it open (remembered as `g-rail-command`). Every old URL still serves.
- Renders the brain's graphs (notes, nerves, lineage, refs) by consuming the brain REST API at `BRAIN_API`.
- `/design`: the g-design reference (guideline and component cards) in an index beside a frame. `compile.py` copies the checkout at `G_DESIGN_DOCS` (g-design's `apps/docs`) into `output/assets/design/` and indexes the cards by their `@dsCard` comment, so a g-design change shows here on the next restart.
- `/graph`: the brain's wikilink graph in 3D (3d-force-graph, WebGL).
- `/system`: live service topology + health, from the brain L5 status index.
- `/projects`: project gallery: a card per `manifest.projects[]` (thumbnail, health, gcore compliance, deps, lineage, last commit). Pure renderer; the list is the manifest, so a new entry self-adds. Each card carries one gates line (blocking trouble, how many gates are met), and `/projects?project=<id>` is that project's view: the card, the g-levels charter covering the repo and every gate it pins with its latest result and when it last reported, blocking silent gates in red. Both read `/api/levels/projects` and `/api/levels/project/<id>` (states and counts, never notes). The apps show it in their signed-in web view.
- `/calendar`: the one view of brain todos (Todos merged in on 2026-11-03; `/todos` is a 301 here, see `MOVED` in `server.py`). Every item has a date. The default is a list (Overdue, Today, Tomorrow, This week, Later, five weeks out) with a tick and a move button per row; `?view=month` is the month grid, a cell click listing that day below it. Adding needs a date, the time is optional. Ticking a recurring item ticks that occurrence only; moving is for one-offs (the brain refuses to reschedule a series). Daily habits show on today only. Recurrence and overdue carry-over are the brain's (`/api/todos/calendar`). The essentials (at most three lines: overdue, today, bills of 50 pounds or more this week, tomorrow) are the `agenda` panel (`core/panels/agenda.py`), shown in Home's agenda card (`<div data-lines>`, filled by `hub.js`). Every count beside the calendar (the dash panel's head, the Calendar page's badge) is the agenda's own (`agenda.counts`), so a head never says nothing is due while the agenda names something. It reads the brain's `/api/todos/agenda` and, while that is missing, works the lines out from the calendar feed; a failure is a line, never a blank.
- `/tickets`: every g-admin ticket across every project that speaks the contract, aggregated live via `core/api/gadmin_panel.py`. No local store; same pattern as `/system`. Deep link `/tickets?project=<id>&id=<ticket>` filters to the project and opens that ticket (the desktop app, g-command-mac, uses it); `project` alone just filters.
- `/levels`: g-levels (gates, charters, results, the candidate-gate backlog and the share of Gabriel's prompts per level), read live from the g-levels checkout through `pages/levels/api.py`. Grading a verdict runs `glevels grade`. See `pages/levels/CLAUDE.md`.
- `/browser`: g-browser (the always-on logged-in Chrome on this host) to watch and drive: the noVNC live view (inline, full screen or its own tab), status, mode switch, profile and bandwidth, restart, re-seed from a profile export and the activity feed. It replaces g-browser's own panel: `browser.gabrielpenman.com` 301s its pages here. `pages/browser/api.py` proxies g-browser's panel API and its `/vnc/` socket, adding g-browser's admin cookie server-side, so the visitor needs only this site's gate and a paired app drives it with its device token. The secret comes from `/etc/g-secrets/gbrowser-admin.env` via the `zz-gbrowser.conf` drop-in. nginx needs the `location /api/browser/vnc/websockify` upgrade block, since `location /` sends no Upgrade header.
- `/wages`: g-wages' ledger editor (clients, the week grid of hours, earned, paid in, expenses and work-log, the day editor, invoice period, mark and issued list, report and hours basis), a Work entry beside Hours. `pages/wages/api.py` proxies `/api/wages/*` to g-wages' `/api/ledger/*` on loopback behind this site's gate; g-wages keeps its process and data. `wages.gabrielpenman.com` 301s here. See `pages/wages/CLAUDE.md`.
- `/studio`: g-studio itself, run in this page with no iframe. `pages/studio/content.html` imports `<STUDIO_ORIGIN>/static/mount.js` from the studio's origin and mounts it in the content area; the studio's API, events and sockets stay on its origin with its own session cookie (same site, so it travels). Nothing of the studio is bundled here. Deep links are `/studio#/site/<pid>/<section>`: the studio owns the hash. `STUDIO_ORIGIN` comes from `.env` like `PUBLIC_HOST`, unset the page says Studio is not set up, and the studio must list this origin in its `GS_EMBED_ORIGINS` (g-studio contracts.md "Embedding").
- `/runners`: the g-runner device fleet (devices online or stale, the queue, recent results with runner page rAF frame times and posted values), read live through `core/api/runners.py`, which holds the g-runner token server-side. Read only, refreshes every 5 s while visible.
- The apps (g-command-apple) draw panel pages from the panel contract and copy nothing. The Calendar and the chat todo actions are hand-ported from `pages/calendar/content.html`, so `core/native.json` lists each with that source, its hash when the port was last confirmed and the lowest app build that has it. `GET /api/app/manifest` carries the ones still matching as `native`; a stale one drops out and the apps show the web page. After changing a listed source, run `scripts/native_check.py`: it names what is stale (exit 1). Update the app, or confirm the change does not touch it, then `--verify <screen>` (`--min-build N` when the app had to change). gcore conventions.md, "Native hangs off web".
- Whole site is password-gated (one shared password, once per browser session).

## Stack
gseed-app seed framework: static-first pages compiled by `compile.py`, served by FastAPI (`server.py`). Pages live in `pages/{slug}/` (`config.json` + `content.html`); API routers auto-discover from `core/api/*.py` and `pages/*/api.py`.

## Run
```
npm ci && python3 compile.py && python3 server.py
```
`npm ci` (preact, htm, esbuild, pinned in `package.json` to Studio's web) is
needed once per checkout and after `package.json` changes; without it the
Preact pages serve their plain `content.html` and the compile still succeeds.
Served on `127.0.0.1:$PORT` (default 8089), fronted by nginx. Deployed via the `gcommand` systemd unit on h.

## Gotchas
- Brain data is **not** local: every brain page fetches `${BRAIN_API}/api/*` from the browser. Nothing here reads the brain filesystem. `BRAIN_API` is the one place the origin is set: `compile.py` reads it from the environment, then from `.env` beside it (default `/api/brain`, this server's admin-gated proxy to the g-brain at `BRAIN_UPSTREAM`, trailing slash dropped), the shell writes it into `<meta name="brain-api">` and an inline head script copies that to `window.BRAIN_API`. Pages read the global and never name the host. It is baked in at compile time, so a change needs a recompile, which the unit's `ExecStartPre` runs on every restart. Set it in `.env` (the unit's `EnvironmentFile`). `OWNER_SITE_URL` (the owner's site, linked from the drawer and top bar, hidden when unset) `STUDIO_ORIGIN` (g-studio's origin for `/studio`) `PUBLIC_HOST` (the host in the status line) and `MCP_URL` and `MCP_HEADLESS_URL` (the brain's MCP endpoints, quoted on the install and setup pages through `<!-- seed: -->` tokens) work the same way. compile.py takes only these keys and the `SEED_MANIFEST_*` ones from `.env`, so a compile by hand matches the one on restart.
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
| `core/panels/CLAUDE.md` | core/panels: the shared panel contract |
| `core/templates/CLAUDE.md` | Templates: the shared shell |
| `pages/CLAUDE.md` | Pages |
| `pages/blog/CLAUDE.md` | blog |
| `pages/full-dash/CLAUDE.md` | full-dash |
| `pages/hours/CLAUDE.md` | hours |
| `pages/levels/CLAUDE.md` | levels |
| `pages/sessions/CLAUDE.md` | sessions: the terminal page |
| `pages/upload/CLAUDE.md` | upload |

_Auto-compiled 2026-10-20 12:44 UTC, 11 doc(s) found._
<!-- DOCS:END -->
