---
paths:
  - "**/api.py"
  - "**/api/**"
  - "server.py"
---
# API Conventions

APIs are auto-discovered. Create a file; restart the server; it mounts.
No manual registration.

## Where to put an API

| File location | URL prefix |
|---|---|
| `pages/{slug}/api.py` | `/api/{slug}` |
| `core/api/{name}.py` | `/api/{name}` |
| `{product}/api/{name}.py` | `/api/{product}/{name}` |

Pick based on scope:
- Page-specific endpoint? Co-locate in `pages/{slug}/api.py`.
- Used by many pages? Put in `core/api/`.
- Product-specific in a multi-product layout? `{product}/api/`.

## Minimum API file

```python
from fastapi import APIRouter

router = APIRouter(tags=["example"])

@router.get("/")
async def index():
    return {"ok": True}
```

The file must export a module-level `router` object. Files starting with
`_` are skipped (use for helpers).

## Rules

- **`router` is required at module level.** No `router` = not mounted.
- **No top-level side effects** (DB connections, network calls). Module
  import happens at server startup; blocking imports stall the server.
  Use FastAPI's `lifespan` in `server.py` for startup work.
- **Sanity-check mounts** via `GET /api/_routes` after restart.
- **Restart is required** after adding a new `api.py`. Editing an
  existing one: use `uvicorn --reload` in dev, or restart in prod.
