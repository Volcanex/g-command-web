Create a new page in this project.

Ask the user for:
- **Slug**: URL path (e.g. `about`, `docs/setup`). Defaults to derive
  from the title.
- **Title**: human-readable page title.
- **Description**: one-sentence meta description (optional).
- **Needs an API?**: if yes, also scaffold `api.py`.

Then:
1. Create `pages/{slug}/config.json`:
   ```json
   {
     "title": "Title Here",
     "description": "One-sentence description."
   }
   ```
2. Create `pages/{slug}/content.html` with a skeleton body. No `<html>`
   or `<body>` tags. The shell provides them. May include a `<style>`
   block for page-specific layout.
3. If an API is needed, create `pages/{slug}/api.py`:
   ```python
   from fastapi import APIRouter

   router = APIRouter(tags=["{slug}"])

   @router.get("/")
   async def index():
       return {"ok": True}
   ```
4. Run `python3 compile.py`.
5. If this directory warrants documentation (non-obvious behaviour,
   shared conventions), also create `pages/{slug}/CLAUDE.md` and run
   `python3 scripts/compile_docs.py`.
