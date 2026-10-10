# Agent kickoff: g-admin tickets panel

You are an agent working inside a git worktree off `main` for this
project. **Read `agents/CLAUDE.md` in the repo root before doing
anything.** The binding contract is
`agents/g-admin-contract.md` in the g-design repo. Prerequisite: at
least one project serves the contract (opentable is the first).

## The goal

A tickets panel on the command center: every g-admin ticket across
every project that speaks the contract, in one place, using the same
aggregation pattern as service health. This is where a baking session
starts: find a ticket, copy its brief, hand it to an agent.

## Constraints

- **Lands at URL:** `/tickets`, behind the existing admin auth.
- Source list: projects in the instance `manifest.json`. Probe
  `https://{domain}/api/gadmin/verify` with the `X-Gadmin-Token`
  header (`GADMIN_TOKEN` env var, from the passport) to discover who
  speaks the contract; cache the roster, don't probe on every render.
- Server-side fetch with the token header; the browser never sees the
  token. Reads only: this panel never creates tickets.
- **DB:** none. Aggregation is live reads + short in-process cache,
  same as service health. g-command-web stores nothing the projects
  already store.

## Wiring into this codebase

- New endpoint: `core/api/gadmin_panel.py` (auto-mounts) proxying
  list/get/brief/patch-status to the source projects.
- New page: `pages/tickets/`, filter by project/status/severity,
  detail view rendering the brief with a copy button, and a
  mark-baked/dismiss action (PATCH via the token path).
- Drawer link in the admin nav section.

## Acceptance

- Existing test suite passes; tests for the proxy endpoint (token
  header attached, roster caching, a project being down degrades to a
  labelled empty state, never an error page).
- Page renders with opentable as a live source.
- `.env.example` documents `GADMIN_TOKEN`.
- CLAUDE.md files updated and pruned; `python3 scripts/check_docs.py`
  exits 0.

## Don't

- Don't add a tickets store in g-command-web.
- Don't put the token in client-side code or query strings.
- Don't build a bake-launching integration yet: copy-the-brief is v1;
  a g-bake skill is a separate later piece.
