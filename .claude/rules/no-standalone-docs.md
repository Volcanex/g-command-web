---
paths:
  - "**/*.md"
  - "docs/**"
---
# No standalone documentation files

`CLAUDE.md` files are the only place to record non-obvious context about
this codebase. They exist for Claude, not for human readers.

**Rules:**
- Never create standalone `.md` files for documentation purposes
  (`NOTES.md`, `ARCHITECTURE.md`, `SETUP.md` or anything like them).
- If you learn something that Claude would get wrong without being told,
  add it to the relevant directory's `CLAUDE.md`.
- There is no `docs/` directory. Do not create one.
- Exceptions: `README.md` (repo root only, for GitHub), `LICENSE`,
  `CHANGELOG.md` (if the project publishes releases), `.claude/rules/*.md`
  and `.claude/commands/*.md` (the Claude system itself).
- After editing any `CLAUDE.md`, run `python3 scripts/compile_docs.py`
  so the index in root CLAUDE.md stays fresh.
