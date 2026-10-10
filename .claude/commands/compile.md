Compile everything: pages and the docs index.

1. Run `python3 compile.py` to rebuild pages from `pages/*/content.html`
   into `output/*.html`.
2. Run `python3 scripts/compile_docs.py` to rebuild the `<!-- DOCS:START -->`
   block in root `CLAUDE.md`.
3. Report what was compiled and any warnings.

Run this before every commit that touches `pages/`, `core/templates/`,
or any `CLAUDE.md`.
