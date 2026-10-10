# Agent kickoff: <integration name>

You are an agent working inside a git worktree off `main` for this
project. **Read `agents/CLAUDE.md` in the repo root before doing
anything.** It explains the worktree discipline, the reserved port
range, and what you are NOT allowed to do.

## The goal

<one-paragraph description of what to build, in plain language>

## Constraints

- **Port:** <reserved port from agents/CLAUDE.md>
- **Container name:** `<project>-<short-name>`
- **Lands at URL:** `/<slug>` (gated by the existing admin auth if it's
  an admin surface)
- **Env vars to add to `.env.example`:** <list>
- **DB:** <use existing `core.db` / runs its own / no DB>
- **External APIs:** <list, free tier or paid?>

## Wiring into this codebase

- New endpoint(s): <list, under `core/api/<name>.py` or
  `pages/<slug>/api.py`>
- New page(s): <list, under `pages/<slug>/`>
- Drawer link in `core/templates/shell.html`: add a `<a href="/<slug>">`
  inside the relevant `<nav>` section. For admin links, place inside
  `nav-admin-section` so it only renders when authenticated.
- Update relevant `CLAUDE.md` files (root + any directory whose shape
  changed).

## Acceptance criteria

- The full existing test suite still passes.
- At least one new test for the integration.
- The page renders (behind admin auth if applicable).
- `.env.example` documents every new env var.
- A new `CLAUDE.md` exists in the integration's directory if it has
  non-obvious behaviour.
- **Before opening the PR, prune anything in `CLAUDE.md` the change
  made obsolete.** Don't just append. Delete stale rows, rewrite
  paragraphs that are now wrong, drop env vars that were replaced. Run
  `python3 scripts/check_docs.py` and confirm it exits 0.

## What's already there

- Admin auth: cookie-based, password in env var `ADMIN_PASSWORD`.
  Cookie name configurable via `ADMIN_COOKIE`. Gated routes documented
  in root `CLAUDE.md` under "Admin auth".
- Drawer: `core/templates/shell.html` + `core/static/js/nav.js`. Add a
  link with the right Phosphor icon (https://phosphoricons.com/).
- Phosphor icons: already loaded site-wide via CDN. Use as
  `<i class="ph ph-<name>"></i>`.

## Don't

<list specific NO-NOs for this integration>
