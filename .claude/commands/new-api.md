Create a new API router.

Ask the user:
- **Scope**: is this tied to a specific page (`pages/{slug}/api.py`),
  shared across many pages (`core/api/{name}.py`), or product-scoped
  (`{product}/api/{name}.py`)?
- **Name**: module name (becomes part of the URL prefix).
- **Auth**: none, authenticated, or admin-only. (The seed does not ship
  with auth; add it when needed and document in a `CLAUDE.md`.)

Then:
1. Create the file at the chosen path:
   ```python
   from fastapi import APIRouter

   router = APIRouter(tags=["{name}"])

   @router.get("/")
   async def index():
       return {"ok": True}
   ```
2. Restart the server (`docker compose restart app` or re-run
   `python3 server.py`).
3. Hit `GET /api/_routes` and confirm the new routes appear.
