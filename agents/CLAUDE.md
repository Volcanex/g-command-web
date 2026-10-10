# Agents: kickoff prompts for parallel integrations

Each `.md` file here is a **self-contained brief** for one integration:
copy-paste it into a fresh Claude / Codex / Cursor session to spawn an
agent that builds that piece. The brief tells the agent everything it
needs: the goal, the boundaries, the conventions of this repo, how to
verify, and where to leave its docs.

## The discipline (one paragraph)

Each integration runs in its own **git worktree** off `main`. The agent
works there, doesn't touch the production container, and merges back
when the integration is feature-complete and tested. This keeps `main`
shippable while several agents are building things in parallel.

## Worktree workflow

```bash
# Spawn in a worktree so main stays shippable.
git worktree add ../myproject-feature -b feat/feature
cd ../myproject-feature

# Agent works here. Convention: each integration declares a port + a
# container name in the prompt; agents pick from a reserved range so
# they don't clash. Maintain the table below.

# When done:
git push -u origin feat/feature
gh pr create
# After merge:
git worktree remove ../myproject-feature
git branch -d feat/feature
```

## What agents are NOT allowed to do

- Restart the production container while building. Live traffic.
- Add a sibling Docker container that listens on a port already in use.
  Pick from the reserved range (maintain a table per project).
- `git push` to `main`. Push the feature branch and stop. The human
  reviews and merges.
- Modify shared core (`server.py`, `compile.py`, `core/db.py`,
  `core/api/admin.py`) unless the brief explicitly says so.
- Skip the prune rule below.

## What every agent MUST do before opening a PR

1. Run the existing test suite from **inside the worktree**, not via
   `docker exec` against production (which executes against `main`,
   not the branch). Set up a venv once:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
   .venv/bin/pytest tests/ -q
   ```

   All existing tests must still pass against the branch.
2. Add at least one test for the new endpoints / pages it created.
3. Update `CLAUDE.md` files for any directory whose shape it changed.
4. Document any new env vars in `.env.example`.
5. **Prune what you replaced.** If the change made an old paragraph,
   table row, env var, or path in any `CLAUDE.md` obsolete, **delete
   it**. Don't just append. The doc system only stays sustainable if
   replacements remove their predecessors.
6. Run `python3 scripts/check_docs.py`. It must exit 0. Fails if any
   path in `CLAUDE.md` no longer exists on disk, or root drifts past
   the configured line cap.

## Available kickoffs

Add a new kickoff by copying `_template.md`, filling in the goal +
constraints, and adding a row below.

| File | Builds | Reserved port | Lands at |
|---|---|---|---|
| `g-admin-tickets-panel.md` | Cross-project g-admin tickets panel | n/a (no container) | `/tickets` |
