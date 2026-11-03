# Pages

Each subdirectory is one page. `compile.py` walks them and emits HTML
into `output/`. See `.claude/rules/pages-convention.md` for the file
layout and `core/templates/CLAUDE.md` for available template tokens.

## Example pages

- `index/`: Home, at `/` (`href` in its config): a tile per place with a
  live line where one is cheap. The first Preact page, see below.
- `home/`: the life dash. With `ops/` (the system dash) and `full-dash/`
  (both) it is built from the shared panels in
  `full-dash/panels/`; see `full-dash/CLAUDE.md`.
- `brain/`: the brain overview, first tab of the Brain group.
- `crons/`: a page with the optional `api.py` sibling file. The
  auto-discovered router is mounted at `/api/crons`.

## Nav groups

The sidebar holds about ten daily entries. Related pages share one entry
through `"tabs": "<group>"` in `config.json`: the member with `nav: true`
is the sidebar entry, the rest set `nav: false`, and every member gets the
group's tab strip in the top bar, labelled by `tab_label` and ordered by
`order`. Groups: `system` (Overview `/ops`, Services `/system`, Compute,
Crons, Tickets, Projects, Hours, Levels), `brain` (Overview `/brain`, Pulse,
Voice, Writing voice, Graph, Nerves, References, Lineage), `files` (Workspaces `/drive`,
Upload, Photos, Blog) and `setup` (Setup, Install, Passport, reached from
the wrench in the sidebar foot). A page left out of the nav keeps its
route: hide pages, never delete or rename them, since the Mac app and old
links name them directly.

## When to colocate an API

Put `api.py` next to the page if the endpoints are only used by that
page (form submissions, page-specific data loads). Move to `core/api/`
when two or more pages consume the same endpoints.

## Preact pages

A page moves to Preact by shipping `app.js` beside its `config.json`
(`index/` and `nerves/` are the examples). Nothing else opts it in.

- `app.js` imports everything from `core/app/boot.js` (the vendored kit at
  `core/static/css/gsys/kit/`, htm, hooks, `getJson`, `useJson`,
  `loadScript`) and ends with `mount(Page)`. It may `import "./app.css"`
  for page styles (alias tokens only). Draw glyphs with the Phosphor font
  (`<i class="ph ph-NAME">`); `core/app/icon-paths.js` holds only the
  paths kit components draw themselves.
- `compile.py` bundles it with esbuild (`node_modules/.bin/esbuild`, so a
  checkout needs `npm ci`) into `output/js/pages/<slug>.js` (+ `.css`) and
  the page body becomes a `[data-page-app]` slot (`display: contents`, so
  the component's blocks sit in the page stack) plus a module script, both
  stamped `?v=<hash>`. The shell, nav, tabs and URL stay as they are.
- `content.html` is still required: it is the plain fallback.
- Failure never stops a compile, so it never stops the unit starting. The
  error is printed in full in the compile log; the last good bundle (kept
  in gitignored `var/bundles/`, since `output/` is wiped) is served under a
  one-line notice; with no last good bundle the page serves `content.html`
  under a "This page did not build" block. Every outcome is in
  `var/bundles/status.json`, served at `GET /api/bundles`
  (`{pages, failing}`).
- `app_nav: false` in a config keeps a nav entry out of the apps' manifest
  (Home: the apps draw their own navigation).
- Tests: `tests/test_preact_pages.py`.
