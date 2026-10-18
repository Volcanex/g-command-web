# core/api: shared API routers

Files here are auto-discovered at startup and mounted at `/api/{stem}`.
Each must export `router = APIRouter()`. See
`.claude/rules/api-conventions.md` for the convention; see `server.py`
for the discovery code.

## What's shipped

| File | Mounted at | Purpose |
|---|---|---|
| `admin.py` | `/api/admin` | Cookie-based single-user auth: login / logout / verify, plus a browser-runnable test runner |
| `gadmin.py` | `/api/gadmin` | This project's own g-admin ticket store (annotate/edit overlay backend) |
| `gadmin_panel.py` | `/api/gadmin_panel` | Cross-project tickets panel: proxies every project that speaks the g-admin contract |
| `runners.py` | `/api/runners` | Read-only, admin-gated proxy to g-runner (`GET /state`, `GET /jobs/{id}`) for `/runners`; adds the bearer token server-side |
| `brain.py` | `/api/brain` | Admin-gated proxy to the g-brain REST API at `BRAIN_UPSTREAM`, so brain pages work without a public brain host |

## admin.py

Single-user, password-gated. A correct password sets the cookie to
`ADMIN_COOKIE_VALUE`, which is itself a secret: holding the cookie is being
logged in. It has no default (it used to be the forgeable constant "ok").
`core/auth.py` reads it and the cookie name once, every router imports them
from there, and the server refuses to start without it. Configure via env vars:

| Env var | Default | What |
|---|---|---|
| `ADMIN_COOKIE` | `seed_admin` | Cookie name |
| `ADMIN_COOKIE_VALUE` | none, required | Cookie value: a long random secret. Rotating it logs every session out. |
| `ADMIN_PASSWORD` | none, required | The password. Login is refused (503) while it is unset or `change-me`. |

Endpoints:

- `POST /api/admin/login`: body `{password}` → sets the cookie on success
- `POST /api/admin/logout`: clears the cookie
- `GET /api/admin/verify`: `{admin: bool}` (used by `nav.js` to swap drawer sections)
- `POST /api/admin/tests/run`: runs `pytest tests/ -v` synchronously and returns the
  exit code + output. Admin-only. Useful as a "re-run the suite from the browser"
  button in your admin UI.

`is_admin(request)` and `require_admin(request)` are exported for other
API modules to gate endpoints. Import from `core.api.admin`.

## gadmin.py

The reference server for the g-admin overlay contract
(`agents/g-admin-contract.md` in the g-design repo): tickets from the
annotate/edit overlay, stored in `var/gadmin.db` (SQLite, one row per
ticket). Two auth tiers: cookie (`is_admin`, full read/write) and
`X-Gadmin-Token` (`GADMIN_TOKEN` env var, GET everywhere + PATCH-status
only, never note edits or ticket creation). Nothing here writes to
project source; baking is a separate, human/agent-driven step.

## gadmin_panel.py

Cross-project aggregation for the tickets panel at `/tickets`, mounted
here rather than colocated with the page because the same data could
back other admin surfaces later. Holds no data of its own: every read
proxies to a project's own `/api/gadmin` with the token header, same
"live reads, no local store" pattern as `/system`'s service health.

Roster discovery: group the instance `manifest.json` services by `repo`, probe
`{base}/api/gadmin/tickets?status=open` with the token, cache the
project ids that answer for `ROSTER_TTL_S` (10 min), rebuilt lazily.
**Gotcha:** a 200 alone isn't proof of the contract. A project with a
catch-all SPA route (seen live against gdesign) 200s any unmatched path
including this one, serving its index page. The probe also checks the
payload is `{"tickets": [...]}` before counting a project as a roster
member; `list_tickets` re-checks the same shape per call so a project
that stops speaking mid-window degrades that project, not the page.

Every downstream call times out at `REQUEST_TIMEOUT_S` (3s) and never
raises past `_http`: a dead project shows up in the aggregate
response's `degraded` list, never a 500. The admin-cookie gate is
checked inline, same as `pages/gcore/api.py`, since the site-wide page
gate in `server.py` doesn't cover `/api/*`.

## runners.py

Backs `/runners`. `GET /api/runners/state` fetches `${G_RUNNER_URL}/api/state`
and `GET /api/runners/jobs/{id}` fetches one job, both with
`Authorization: Bearer <token>` added here, so the token never reaches the
browser. 3 s timeout. A missing token, a refused token or a dead upstream
answers 200 with `{"error": {"code", "message"}, "upstream"}`, which the page
shows as a card; never a 500. No enqueue or cancel from gcommand.

| Env var | Default | What |
|---|---|---|
| `G_RUNNER_URL` | `http://127.0.0.1:8160` | g-runner base URL |
| `G_RUNNER_TOKEN` | none | g-runner agent token (`RUNNER_TOKEN` there) |
| `G_RUNNER_TOKEN_FILE` | `/etc/g-runner/token` | Read when `G_RUNNER_TOKEN` is unset; must be readable by the gcommand unit's user |

## How the gate works

`server.py::_admin_gated()` redirects any unauthenticated request to a
path under `/admin` (except `/admin/login`) to `/admin/login`. The
endpoints here are how the frontend toggles that cookie.

When real multi-user auth is needed (multiple humans, external
surfaces, audit logs), upgrade the cookie to a signed token (HMAC) and
introduce a session table, but most internal-only projects never need
to.
