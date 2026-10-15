# Pages

Each subdirectory is one page. `compile.py` walks them and emits HTML
into `output/`. See `.claude/rules/pages-convention.md` for the file
layout and `core/templates/CLAUDE.md` for available template tokens.

## Example pages

- `home/`: the life dash. With `ops/` (the system dash) and `full-dash/`
  (both, where `/` lands) it is built from the shared panels in
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
Crons, Tickets, Projects, Hours), `brain` (Overview `/brain`, Pulse,
Voice, Writing voice, Graph, Nerves, References, Lineage), `files` (Workspaces `/drive`,
Upload, Photos, Blog) and `setup` (Setup, Install, Passport, reached from
the wrench in the sidebar foot). A page left out of the nav keeps its
route: hide pages, never delete or rename them, since the Mac app and old
links name them directly.

## When to colocate an API

Put `api.py` next to the page if the endpoints are only used by that
page (form submissions, page-specific data loads). Move to `core/api/`
when two or more pages consume the same endpoints.
