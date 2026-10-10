# Pages

Each subdirectory is one page. `compile.py` walks them and emits HTML
into `output/`. See `.claude/rules/pages-convention.md` for the file
layout and `core/templates/CLAUDE.md` for available template tokens.

## Example pages

- `home/`: landing page, demos the grid layout.
- `crons/`: a page with the optional `api.py` sibling file. The
  auto-discovered router is mounted at `/api/crons`.

## When to colocate an API

Put `api.py` next to the page if the endpoints are only used by that
page (form submissions, page-specific data loads). Move to `core/api/`
when two or more pages consume the same endpoints.
