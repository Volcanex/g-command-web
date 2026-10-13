---
paths:
  - "pages/**"
  - "compile.py"
  - "core/templates/**"
---
# Pages Convention

Every page is a directory under `pages/` (or under a top-level product
directory if you've introduced the core/product split).

## Required files

```
pages/{slug}/
  config.json     # Metadata
  content.html    # Body fragment
```

**`config.json`**, at minimum:
```json
{ "title": "Page Title" }
```

Optional fields (use what you need; `compile.py` interpolates all string
values into the shell template):
- `"slug"`: override the URL slug (defaults to the directory name)
- `"description"`: meta description
- `"nav": true`: include in navigation (your shell is responsible for
  reading this; the compiler just passes it through)
- `"order": 10`: sort order in nav
- `"tabs": "group"` + `"tab_label"`: join a tab group shown in the top
  bar (see `pages/CLAUDE.md`)

**`content.html`**: the page body. May include a `<style>` block for
page-specific CSS. No `<html>`, `<head>`, or `<body>` wrappers. The
shell provides those.

## Optional files

- `api.py`: FastAPI router auto-mounted at `/api/{slug}`. Must export
  `router = APIRouter()`. See `.claude/rules/api-conventions.md`.

## How compilation works

`python3 compile.py` does:
1. Reads `core/templates/shell.html`.
2. For each `pages/{slug}/`: loads `config.json` + `content.html`,
   interpolates `{{ key }}` tokens, writes `output/{slug}.html`.
3. Copies `core/static/*` into `output/` for the server to mount.

## Adding a page

Use `/new-page` (see `.claude/commands/new-page.md`) or create the files
by hand. Always run `python3 compile.py` after.
