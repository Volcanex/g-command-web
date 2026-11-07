# Pages

Each subdirectory is one page. `compile.py` walks them and emits HTML
into `output/`. See `.claude/rules/pages-convention.md` for the file
layout and `core/templates/CLAUDE.md` for available template tokens.

## Example pages

- `index/`: Home, at `/` (`href` in its config): the agenda card over the
  full dash. See `full-dash/CLAUDE.md`.
- `home/`: the life dash. With `ops/` (the system dash) and `full-dash/`
  (both) it is built from the shared panels in
  `full-dash/panels/`; see `full-dash/CLAUDE.md`.
- `brain/`: the brain overview, first tab of the Brain group.
- `crons/`: a page with the optional `api.py` sibling file. The
  auto-discovered router is mounted at `/api/crons`.

- `resell/`: Resell project admin under Projects: dashboard, pool and item details, profit, and bot controls. See `resell/CLAUDE.md`.

## Nav groups

The left rail is the only navigation (g-design `skills/g-navigation`).
The rail's top (the first section, `Overview`, which carries no heading)
is Home, Chat, Upload, then the Life and System groups; the other headings
group by intent: Work, Knowledge, Publish, Setup.
`"tabs": "<group>"` in `config.json` is the parent pointer: the member with
`nav: true` is the group, drawn as a disclosure row (open by default, never
a link), and the rest set `nav: false` and nest one level under it,
labelled by `tab_label`, ordered by `order`, each with its own `nav_icon`.
`web_page: false` on the group says its own page is gone from the web (its
URL is in `MOVED` in `server.py`); otherwise that page leads its children
(Setup, as Bootstrap, with `tab_icon`). `web_section` and `web_order` place
an entry on the web rail apart from the apps (Upload is at the top here and
under Publish there). The key keeps its name because the apps read the same
manifest (their sidebar draws the same groups, and their Overview dash is
still Life, System and Full dash). There are no hub or tile pages.
Groups: `projects` (HALN `/haln`, Studio recorder at `/recorder`,
under Work), `life` (Calendar, Pulse), `system` (Diagram, Services `/system`,
Compute, Crons, Tickets, Projects, Levels), `brain` (Graph, Notes,
Nerves, References, Lineage), `design` (Language `/design`, Showcase) and `setup` (Bootstrap `/setup`, Install,
Passport). `/home`, `/ops`, `/brain` and `/voice` are 301s to Home, Home, Graph and Chat.
`/projects-group` goes to `/recorder`; the Projects group has no hub page.
A page left out of the nav keeps its route: hide pages, never delete or
rename them, since the Mac app and old links name them directly.

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

## New views

Start every new view from the scaffold, not by copying a page:

    python3 scripts/new-view.py <slug> --group <group> [--title "Title"] [--no-api]
    python3 compile.py

It copies `scripts/view-template/` (kept outside `pages/`, so the template is
never compiled or put on the rail) into `pages/<slug>/`: a `config.json`
nested under `<group>` (`nav: false`, `tabs`, `tab_label`; set `nav_icon`
and `order`), a fallback `content.html`, a Preact `app.js`, a token-only
`app.css` and an admin-gated `api.py` at `/api/<slug>` returning `{items: []}`.
The view contract it holds is checked, warn-only for now, by the g-levels gate
`correct.ui.view-contract` (`glevels check pages`, or
`python3 ~/g-levels/glevels/viewcontract.py . --page <slug>`):

- Header: the top bar names the page (`Group > Page`); the page opens with the
  kit `PageHead` (title screen-reader only, `sub` line, actions). No visible
  title, no title spacing, no raw px top offsets.
- Margins: `.content-page` owns the gutter and the `--sp-4` stack gap. Never
  pad or margin `.content-page`/`.site-main`.
- Motion: the shell's cross-document view transition (`g-vt-in`, in
  `g-admin.css`) brings every page in. No page-local entry `@keyframes`.
- States: `useJson` + `Loaded` (skeleton, `ErrorState` with retry), and `Empty`
  when there are no rows.
- Tokens: alias tokens only; no hex, no raw px (0 and 1px hairlines aside).
