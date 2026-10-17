#!/usr/bin/env python3
"""
Seed framework: FastAPI with page+router auto-discovery.

Two conventions drive the server:

1. Pages live at `pages/{slug}/content.html` + `pages/{slug}/config.json`.
   `compile.py` walks these and emits `output/{slug}.html` wrapped in
   `core/templates/shell.html`. The server serves `output/` as static.

2. API routers live at `pages/{slug}/api.py` (or `core/api/*.py`, or any
   `*/api/*.py`). Each file must export `router = APIRouter()`. Discovery
   scans the tree at startup and mounts each router at a path derived from
   its file location. No manual registration.
"""

import importlib.util
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Admin auth (cookie-based, single-user). Configurable via env vars so
# downstream projects can rename the cookie without forking server.py.
# The matching login/logout/verify endpoints live in core/api/admin.py.
# core/auth.py reads the cookie name and secret for every router and stops
# the process here, before any router mounts, if the secret is unset.
from core.auth import ADMIN_COOKIE, cookie_ok


def _is_admin(request: Request) -> bool:
    return cookie_ok(request.cookies)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
_OUTPUT_RESOLVED = OUTPUT_DIR.resolve()

_discovered: list[dict] = []


def _safe_under_output(candidate: Path) -> Path | None:
    """Resolve `candidate` and confirm it stays under OUTPUT_DIR.
    Defends the catch-all serve_pages route against `..` traversal in
    the URL path (Starlette doesn't normalise these for us)."""
    try:
        resolved = candidate.resolve()
        resolved.relative_to(_OUTPUT_RESOLVED)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() else None


def _mount_router(app: FastAPI, py_file: Path, prefix: str, group: str) -> None:
    module_name = f"{group}.{py_file.stem}".replace("/", ".")
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        print(f"  ✗ {py_file.relative_to(PROJECT_ROOT)}: could not load")
        return

    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec: Pydantic v2 (and any forward
    # references) need the module reachable by its qualified name to
    # rebuild model schemas. Without this you get
    # "TypeAdapter[X] is not fully defined" at request time as soon as
    # an endpoint declares a body model. Don't revert.
    sys.modules[module_name] = module
    parent = str(py_file.parent.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        print(f"  ✗ {py_file.relative_to(PROJECT_ROOT)}: {exc}")
        return

    router = getattr(module, "router", None)
    if router is None:
        print(f"  ⚠ {py_file.relative_to(PROJECT_ROOT)}: no `router` exported")
        return

    app.include_router(router, prefix=prefix)
    _discovered.append({"file": str(py_file.relative_to(PROJECT_ROOT)), "prefix": prefix})
    print(f"  ✓ {prefix}  ←  {py_file.relative_to(PROJECT_ROOT)}")


def discover_apis(app: FastAPI) -> None:
    """
    Mount all API routers found in the repo.

    Conventions (in order):
    - `core/api/{name}.py`       → `/api/{name}`
    - `pages/{slug}/api.py`      → `/api/{slug}`
    - `{anything}/api/{name}.py` → `/api/{anything}/{name}`

    `{anything}` in the third form is the directory name. This is the
    "core/product split" escape hatch. One top-level product by default
    (`pages/`); add more top-level dirs only when you truly need isolation.
    """
    # core/api/*.py → /api/*
    core_api = PROJECT_ROOT / "core" / "api"
    if core_api.is_dir():
        for py in sorted(core_api.glob("*.py")):
            if py.name.startswith("_"):
                continue
            _mount_router(app, py, f"/api/{py.stem}", "core.api")

    # pages/{slug}/api.py → /api/{slug}
    pages_dir = PROJECT_ROOT / "pages"
    if pages_dir.is_dir():
        for api_py in sorted(pages_dir.glob("*/api.py")):
            slug = api_py.parent.name
            _mount_router(app, api_py, f"/api/{slug}", f"pages.{slug}")

    # Any other top-level */api/*.py → /api/{top}/{name}
    # Skip rules: dot-prefixed dirs, common cache/build dirs, and the
    # framework dirs already handled above. New top-level dirs (data/,
    # node_modules/, etc.) are skipped automatically by the dot/cache
    # rule or by the "no api/ subdir" check below: no blocklist edits
    # needed when you add one.
    _framework_dirs = {"core", "pages", "output", "tests", "scripts", "static"}
    _cache_dirs = {"__pycache__", "venv", ".venv", "node_modules", "dist", "build"}
    for top in sorted(PROJECT_ROOT.iterdir()):
        if not top.is_dir():
            continue
        if top.name.startswith(".") or top.name in _framework_dirs or top.name in _cache_dirs:
            continue
        api_dir = top / "api"
        if not api_dir.is_dir():
            continue
        for py in sorted(api_dir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            _mount_router(app, py, f"/api/{top.name}/{py.stem}", f"{top.name}.api")


app = FastAPI(
    title="Seed",
    description="Static-first site framework with FastAPI routers.",
    version="0.1.0",
)


print("Discovering APIs...")
discover_apis(app)
print()


@app.middleware("http")
async def _no_cache_api(request: Request, call_next):
    """Brain data is live: never let intermediaries cache /api/* responses.
    Static assets get a day of browser cache (StaticFiles already serves
    ETags, so a hard refresh still revalidates); vendored files a week.

    Pages get `no-cache`: always revalidate. Without a header at all a browser
    may apply heuristic caching, and iOS Safari will keep serving a page it
    never revalidates, which is how a deployed fix stays invisible on the iPad
    while being live everywhere else. Note the page route returns a bare
    FileResponse, which sets an ETag but does not answer If-None-Match, so a
    revalidation is a full 200 rather than a 304; pages are small and correct
    beats cheap here. Conditional GET would need handling on that route."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        # a route that set its own Cache-Control opted in deliberately
        # (photo thumbnails are immutable); everything else stays live
        if "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
    elif path.startswith("/css/vendor/"):
        response.headers["Cache-Control"] = "public, max-age=604800"
    elif path.startswith(("/css/", "/js/", "/assets/")):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/_health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.get("/api/_routes", tags=["system"])
async def routes():
    """List discovered routers and all mounted routes. Handy for sanity checks."""
    all_routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path") and route.path.startswith("/api/"):
            all_routes.append({
                "path": route.path,
                "methods": sorted(m for m in route.methods if m not in {"HEAD", "OPTIONS"}),
            })
    return {"discovered": _discovered, "routes": sorted(all_routes, key=lambda r: r["path"])}


# Static assets compiled by compile.py (CSS, JS, images)
if OUTPUT_DIR.exists():
    for sub in ("css", "js", "assets"):
        p = OUTPUT_DIR / sub
        if p.is_dir():
            app.mount(f"/{sub}", StaticFiles(directory=p), name=sub)


def _admin_gated(path: str, request: Request) -> "RedirectResponse | None":
    """Whole-site password gate. Every page redirects to /login unless the
    visitor holds the auth cookie. The login page is public; static assets
    and /api/* are matched before this runs, so they pass through untouched.
    """
    if path.strip("/") == "login":
        return None
    if _is_admin(request):
        return None
    return RedirectResponse(url="/login", status_code=302)


@app.get("/logout", include_in_schema=False)
async def logout_page():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(ADMIN_COOKIE, path="/")
    return resp


@app.get("/{path:path}", include_in_schema=False)
async def serve_pages(path: str, request: Request):
    """Serve compiled HTML pages with clean URLs."""
    if path.startswith("api/"):
        return JSONResponse({"error": "not found"}, status_code=404)

    # Whole-site password gate.
    redirect = _admin_gated(path, request)
    if redirect is not None:
        return redirect

    if path in ("", "/"):
        return RedirectResponse("/full-dash", status_code=302)

    # Direct file match
    if (resolved := _safe_under_output(OUTPUT_DIR / path)) is not None:
        return FileResponse(resolved)

    # Slug → output/{slug}.html
    if (resolved := _safe_under_output(OUTPUT_DIR / f"{path}.html")) is not None:
        return FileResponse(resolved)

    # Directory index
    if (resolved := _safe_under_output(OUTPUT_DIR / path / "index.html")) is not None:
        return FileResponse(resolved)

    # Tree-walk fallback for dynamic URLs:
    #   /report/{any-slug}        → output/report.html
    #   /admin/audit/{any-slug}   → output/admin/audit.html
    # The first matching prefix wins. Lets one compiled HTML file handle
    # every variant of /report/X without per-slug compilation. The page
    # reads the slug from `location.pathname` and fetches via its API.
    parts = path.strip("/").split("/")
    for i in range(len(parts) - 1, 0, -1):
        candidate = OUTPUT_DIR / ("/".join(parts[:i]) + ".html")
        if (resolved := _safe_under_output(candidate)) is not None:
            return FileResponse(resolved)

    return HTMLResponse(_placeholder_404(path), status_code=404)


def _placeholder_home() -> str:
    return (
        "<!doctype html><title>Seed</title>"
        "<h1>Seed is running, but nothing is compiled yet.</h1>"
        "<p>Run <code>python3 compile.py</code> to build pages.</p>"
    )


def _placeholder_404(path: str) -> str:
    from html import escape
    return (
        "<!doctype html><title>Not found</title>"
        f"<h1>404</h1><p><code>/{escape(path)}</code> does not exist.</p>"
        "<p><a href=\"/\">Home</a></p>"
    )


if __name__ == "__main__":
    # Default to loopback so a stray `python3 server.py` on a laptop
    # doesn't expose the app on the LAN. Containers set HOST=0.0.0.0 in
    # the Dockerfile so the compose port-forward keeps working.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    reload_flag = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    # Terminal sockets are long-lived and idle for minutes at a time. uvicorn's
    # 20s pong deadline kills a backgrounded mobile tab before iOS resumes it,
    # so the deadline is loosened; the ping itself stays, because it is what
    # frees the PTY when a peer really is gone.
    uvicorn.run(
        "server:app", host=host, port=port, reload=reload_flag,
        ws_ping_interval=25, ws_ping_timeout=90,
    )
