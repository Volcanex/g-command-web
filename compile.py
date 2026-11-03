#!/usr/bin/env python3
"""
Page compiler: walks `pages/` and writes `output/{slug}.html`.

Each page is a directory under `pages/` with:
- `config.json`: at minimum `{"title": "..."}`. Optional: `description`,
  `slug`, `body_class`, `nav`, `nav_section`, `nav_icon`, `nav_label`,
  `order`, `tabs`, `tab_label`, anything else your shell.html wants to
  interpolate. Pages with `nav: true` are grouped by `nav_section` and
  sorted by `order` to build the rail automatically (`web_nav: false`
  keeps an entry the apps show off the web rail). `tabs` is the parent
  pointer: the group member with `nav: true` is the parent page (a hub),
  the others are its children, nested one level under it in the rail and
  shown as tiles on it (`<!-- seed:hub-head -->`, `<!-- seed:hub-tiles -->`,
  `tile_note`, `tile_line`). The name stays `tabs` because the apps read the
  same manifest. `nav_current` is the rail link a page lights when it has
  none of its own (a detail route, a page reached by URL).
- `content.html`: HTML fragment for the page body. May include a
  `<style>` block.
- `app.js` (optional): a Preact page. Bundled by esbuild into
  `output/js/pages/`; the body becomes its mount slot and content.html is
  only the fallback when no bundle exists (see "Preact pages" below).
- `href` (config, optional): the nav link, when the page answers somewhere
  other than `/<slug>` (Home: `/`).

The fragment is inserted into `core/templates/shell.html` at the
`{{ content }}` placeholder. `{{ title }}` and any other `{{ key }}`
tokens found in the shell are filled from config.json, falling back to
sensible defaults.

Also copies `core/static/*` into `output/css|js|assets` so the server
can mount them as static.

## Slug-with-slashes

If `config.json` sets a slug like `"admin/audits"`, this compiler writes
`output/admin/audits.html` (parent directories are auto-created). Combined
with the tree-walk fallback in `server.py`, this means a single compiled
HTML can serve every `/<prefix>/<dynamic>` URL, no per-slug page needed.

## Token registry

`<!-- seed:NAME -->` markers in content.html are replaced by registered
renderers before the content is spliced into the shell. Built in:
`mcp_url`, `mcp_headless_url`, `mcp_headless_host` and `public_origin`,
the instance values the install and setup pages quote. Register your
own with `register_token("NAME", lambda ctx: "...")` from a project
hook (most projects don't need this).

## Manifest auto-stub

If `data/manifest.json` exists with shape
`{"items": [{"slug": "...", "title": "..."}]}`, this compiler emits a
default page for every entry that has no hand-written
`pages/{prefix}-{slug}/` directory. Configure via env vars:

  SEED_MANIFEST_PATH       (default: data/manifest.json)
  SEED_MANIFEST_PREFIX     (default: item)        # so item-{slug}.html
  SEED_MANIFEST_TEMPLATE   (default: stub.html)   # under core/templates/

Usage: python3 compile.py
"""

from __future__ import annotations

import html
import json
import os
import hashlib
import re
import shutil
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from core.panels import layout as dash_layout

PROJECT_ROOT = Path(__file__).resolve().parent
PAGES_DIR = PROJECT_ROOT / "pages"
OUTPUT_DIR = PROJECT_ROOT / "output"
SHELL_PATH = PROJECT_ROOT / "core" / "templates" / "shell.html"
STATIC_SRC = PROJECT_ROOT / "core" / "static"
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = PROJECT_ROOT / "core" / "templates"

# The keys below are read from `.env` beside this file when the environment
# lacks them. The unit loads that file as its EnvironmentFile before
# ExecStartPre runs this, so a compile by hand matches the one on restart.
# Only these keys are taken, so the secrets in the same file never enter
# this process.
ENV_KEYS = ("BRAIN_API", "MCP_HEADLESS_URL", "MCP_URL", "OWNER_SITE_URL", "PUBLIC_HOST", "STUDIO_ORIGIN",
            "G_DESIGN_DOCS", "SEED_MANIFEST_PATH", "SEED_MANIFEST_PREFIX", "SEED_MANIFEST_TEMPLATE")


def _load_dotenv(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        key, sep, value = line.strip().partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key not in ENV_KEYS:
            continue
        if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(PROJECT_ROOT / ".env")

# Base URL of the brain REST API that every brain page fetches from. The shell
# hands it to page scripts as window.BRAIN_API, so no page names the host.
# The default is this server's admin-gated proxy (core/api/brain.py), so the
# brain needs no public face.
BRAIN_API = (os.environ.get("BRAIN_API") or "/api/brain").rstrip("/")

# The owner's public site, linked from the drawer and the top bar. Unset, both
# links are hidden. PUBLIC_HOST is the host this dashboard answers on, shown
# in the status line.
OWNER_SITE_URL = os.environ.get("OWNER_SITE_URL", "").rstrip("/")
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "")

# The brain's MCP endpoints, quoted on the install and setup pages. MCP_URL is
# the public OAuth endpoint that hosted chats add; MCP_HEADLESS_URL is the
# origin headless agents reach with Cloudflare Access service tokens. Unset,
# the pages show example.com placeholders rather than someone else's hosts.
MCP_URL = os.environ.get("MCP_URL") or "https://mcp.example.com/mcp"
MCP_HEADLESS_URL = os.environ.get("MCP_HEADLESS_URL") or "https://brain.example.com/mcp"

# g-studio's origin, e.g. https://studio.gabrielpenman.com. /studio imports the real studio
# from <origin>/static/mount.js and runs it in the page (no iframe, nothing bundled here); the
# studio must list this server's origin in its GS_EMBED_ORIGINS. Unset, /studio says so.
_studio = urlsplit((os.environ.get("STUDIO_ORIGIN") or "").strip())
STUDIO_ORIGIN = f"{_studio.scheme}://{_studio.netloc}" if _studio.scheme in ("http", "https") and _studio.netloc else ""

DEFAULTS = {
    "title": "Untitled",
    "description": "",
    "site_name": "Command",
    "body_class": "",
    "brain_api": BRAIN_API,
    "owner_site_url": OWNER_SITE_URL,
    "owner_site_label": urlsplit(OWNER_SITE_URL).netloc or OWNER_SITE_URL,
    "owner_site_hidden": "" if OWNER_SITE_URL else " hidden",
    "public_host": PUBLIC_HOST,
    # The g-admin bar links its ticket count and "Command centre" to this
    # origin. Empty without PUBLIC_HOST, and the bar then leaves both out.
    "g_command": f"https://{PUBLIC_HOST}" if PUBLIC_HOST else "",
    "mcp_url": MCP_URL,
    "mcp_headless_url": MCP_HEADLESS_URL,
    "mcp_headless_host": urlsplit(MCP_HEADLESS_URL).netloc,
    # The setup page's agent prompt tells an agent where to read it from.
    "public_origin": f"https://{PUBLIC_HOST}" if PUBLIC_HOST else "https://command.example.com",
    "studio_origin": STUDIO_ORIGIN,
    "nav_current": "",
    "crumbs": "",
}

# `{{ key }}` substitutes context[key] HTML-escaped; `{{! key }}` keeps
# the value raw (use this when the value is already-rendered HTML, e.g.
# the page body inside the shell). Escape-by-default keeps user data
# from a manifest/CMS/database from becoming an injection vector.
TOKEN_RE = re.compile(r"\{\{\s*(!?)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Slugs become file paths under output/. Allow letters, digits, dash,
# underscore, and forward-slash (for slug-with-slashes). Reject anything
# that could escape the output dir. A bad slug fails the build.
SLUG_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_\-/]*[a-zA-Z0-9_\-]$|^[a-zA-Z0-9_]$")


def _safe_slug(slug: str) -> bool:
    if not isinstance(slug, str) or not slug:
        return False
    if ".." in slug.split("/") or slug.startswith("/") or "\\" in slug:
        return False
    return bool(SLUG_RE.match(slug))


def _safe_output_path(slug: str) -> Path | None:
    """Resolve the output path for a slug and confirm it stays under
    OUTPUT_DIR. Returns None if the slug would escape (defence in depth
    on top of `_safe_slug`)."""
    candidate = (OUTPUT_DIR / f"{slug}.html").resolve()
    try:
        candidate.relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return None
    return candidate

# Token registry: `<!-- seed:NAME -->` → renderer(context) -> str.
# Projects extend this by importing `register_token` from compile and
# calling it before main() runs (e.g. from a project-level hook).
SEED_TOKEN_RE = re.compile(r"<!--\s*seed:([a-zA-Z0-9_-]+)\s*-->")
_TOKEN_REGISTRY: dict[str, Callable[[dict], str]] = {}


def register_token(name: str, renderer: Callable[[dict], str]) -> None:
    """Register a `<!-- seed:NAME -->` content token. The renderer is
    called once per page and receives the page's render context dict.
    Last registration wins (idempotent override is fine)."""
    _TOKEN_REGISTRY[name] = renderer


# Instance values that page bodies quote. Escaped, so a token is safe in text
# and in attribute values alike.
for _key in ("mcp_url", "mcp_headless_url", "mcp_headless_host", "public_origin", "studio_origin"):
    register_token(_key, lambda context, key=_key: html.escape(str(context[key]), quote=True))


# Panel fragments: `pages/{page}/panels/{name}.html` is the token
# `<!-- seed:panel-{name} -->`, so several pages share one fragment instead
# of each carrying a hand-made copy. Read at expansion time, so an edit needs
# only a recompile.
for _panel in sorted(PAGES_DIR.glob("*/panels/*.html")):
    register_token(f"panel-{_panel.stem}", lambda context, path=_panel: path.read_text(encoding="utf-8"))


def expand_seed_tokens(content: str, context: dict) -> str:
    if not _TOKEN_REGISTRY:
        return content

    def sub(match: re.Match) -> str:
        name = match.group(1)
        renderer = _TOKEN_REGISTRY.get(name)
        if renderer is None:
            return match.group(0)
        try:
            return renderer(context) or ""
        except Exception as exc:  # pragma: no cover. Fail loud, keep building
            print(f"  ⚠ token `{name}` raised: {exc}")
            return match.group(0)

    return SEED_TOKEN_RE.sub(sub, content)


# ---------- Preact pages ----------------------------------------------------
#
# A page opts in by shipping `pages/<slug>/app.js` (Preact + htm on the kit,
# through core/app/boot.js). esbuild bundles it into output/js/pages/, and the
# page body becomes a mount slot plus a module script. content.html stays as
# the fallback. A bundle failure never stops the build: the last good bundle
# (kept in gitignored var/bundles/, since output/ is wiped) is served with a
# notice, or with none the page serves content.html under an error block.
# Every outcome is recorded in var/bundles/status.json (GET /api/bundles).
BUNDLE_URL = "/js/pages"
BUNDLE_OUT = OUTPUT_DIR / "js" / "pages"
LAST_GOOD_DIR = PROJECT_ROOT / "var" / "bundles"
ESBUILD = PROJECT_ROOT / "node_modules" / ".bin" / "esbuild"
BUNDLE_TIMEOUT = 60
_bundle_status: dict[str, dict] = {}


def _bundle_name(slug: str) -> str:
    return slug.replace("/", "__")


def _run_esbuild(entry: Path, outfile: Path) -> str | None:
    """Bundle entry into outfile (plus outfile.css if it imports CSS).
    Returns None on success, else the error text."""
    if not ESBUILD.is_file():
        return "esbuild is not installed: run `npm ci` in the checkout"
    import subprocess
    try:
        proc = subprocess.run(
            [str(ESBUILD), str(entry), "--bundle", "--format=esm", "--minify", "--target=es2020",
             "--legal-comments=none", "--log-level=error", f"--outfile={outfile}"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=BUNDLE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"esbuild did not run: {exc}"
    if proc.returncode != 0 or not outfile.is_file():
        return (proc.stderr or proc.stdout or f"esbuild exited {proc.returncode}").strip()[-2000:]
    return None


def bundle_page(page_dir: Path, slug: str) -> dict:
    """Bundle a page's app.js. Returns its status: `state` is built, stale
    (the new bundle failed, the last good one is served) or failed (no bundle
    at all), with `error`, and `js`/`css` hashes when a bundle is served."""
    import time
    name = _bundle_name(slug)
    LAST_GOOD_DIR.mkdir(parents=True, exist_ok=True)
    good_js, good_css = LAST_GOOD_DIR / f"{name}.js", LAST_GOOD_DIR / f"{name}.css"
    tmp_js, tmp_css = LAST_GOOD_DIR / f"{name}.new.js", LAST_GOOD_DIR / f"{name}.new.css"
    for f in (tmp_js, tmp_css):
        f.unlink(missing_ok=True)

    error = _run_esbuild(page_dir / "app.js", tmp_js)
    if error is None:
        tmp_js.replace(good_js)
        if tmp_css.is_file():
            tmp_css.replace(good_css)
        else:
            good_css.unlink(missing_ok=True)
        state = "built"
    else:
        for f in (tmp_js, tmp_css):
            f.unlink(missing_ok=True)
        state = "stale" if good_js.is_file() else "failed"
        print(f"  ✗ {slug}: app.js did not bundle, "
              + ("serving the last good bundle" if state == "stale" else "serving content.html") + ":")
        for line in error.splitlines()[:20]:
            print(f"      {line}")

    status = {"state": state, "error": error, "at": int(time.time())}
    if good_js.is_file() and state != "failed":
        BUNDLE_OUT.mkdir(parents=True, exist_ok=True)
        for src, kind in ((good_js, "js"), (good_css, "css")):
            if src.is_file():
                shutil.copy2(src, BUNDLE_OUT / f"{name}.{kind}")
                status[kind] = hashlib.sha256(src.read_bytes()).hexdigest()[:10]
    _bundle_status[slug] = status
    return status


def app_body(slug: str, status: dict, fallback: str) -> str:
    """The page body for a Preact page, given its bundle status."""
    name = _bundle_name(slug)
    if status["state"] == "failed":
        detail = html.escape((status.get("error") or "").splitlines()[0] if status.get("error") else "")
        return ('<div class="card"><div class="empty state-error" role="alert">'
                '<div class="e-title">This page did not build</div>'
                f'<div class="e-desc">Its script failed to bundle, so this is the plain version. {detail}</div>'
                '</div></div>\n' + fallback)
    parts = []
    if "css" in status:
        parts.append(f'<link rel="stylesheet" href="{BUNDLE_URL}/{name}.css?v={status["css"]}">')
    if status["state"] == "stale":
        parts.append('<p class="muted" role="status">This page runs its last good build: '
                     'the newest one failed to bundle. Details at /api/bundles.</p>')
    parts.append('<div data-page-app></div>')
    parts.append(f'<script type="module" src="{BUNDLE_URL}/{name}.js?v={status["js"]}"></script>')
    return "\n".join(parts)


def write_bundle_status() -> None:
    """Record every bundle outcome for GET /api/bundles. Pages no longer
    bundled drop out; the file is rewritten whole on each compile."""
    if not _bundle_status and not LAST_GOOD_DIR.is_dir():
        return
    LAST_GOOD_DIR.mkdir(parents=True, exist_ok=True)
    (LAST_GOOD_DIR / "status.json").write_text(json.dumps(_bundle_status, indent=1, sort_keys=True), encoding="utf-8")


def load_shell() -> str:
    if not SHELL_PATH.is_file():
        sys.exit(f"ERROR: shell template not found at {SHELL_PATH}")
    return SHELL_PATH.read_text(encoding="utf-8")


def render(template: str, context: dict) -> str:
    def sub(match: re.Match) -> str:
        raw_marker, key = match.group(1), match.group(2)
        if key not in context:
            return match.group(0)  # unknown key: leave the placeholder
        value = str(context[key])
        return value if raw_marker == "!" else html.escape(value, quote=True)
    return TOKEN_RE.sub(sub, template)


def compile_page(page_dir: Path, shell: str) -> tuple[Path | None, dict | None, bool]:
    """Returns (output_path, config, error). `error=True` means the page
    was malformed (not just missing): main() exits non-zero so CI catches it."""
    config_file = page_dir / "config.json"
    content_file = page_dir / "content.html"
    if not (config_file.is_file() and content_file.is_file()):
        print(f"  - {page_dir.name}: skipped (missing config.json or content.html)")
        return None, None, False

    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  ✗ {page_dir.name}: invalid config.json: {exc}")
        return None, None, True

    content = content_file.read_text(encoding="utf-8")
    slug = config.get("slug", page_dir.name)

    if not _safe_slug(slug):
        print(f"  ✗ {page_dir.name}: unsafe slug {slug!r} (letters/digits/-/_/ only)")
        return None, None, True
    out_path = _safe_output_path(slug)
    if out_path is None:
        print(f"  ✗ {page_dir.name}: slug {slug!r} resolves outside output/")
        return None, None, True

    context = {**DEFAULTS, **{k: v for k, v in config.items() if isinstance(v, (str, int, float))}}
    context["slug"] = slug
    context["nav_current"] = config.get("nav_current") or config.get("href") or f"/{slug}"
    context["crumbs"] = crumbs({**config, "slug": slug})

    # A panel page's `layout` (core/panels/CLAUDE.md, Layout) becomes its dash
    # markup and placement CSS here, before the panel tokens it holds expand.
    if "layout" in config:
        content = content.replace("<!-- seed:dash-layout -->",
                                  dash_layout.render(slug, config["layout"], heads=_band_heads()))

    # Expand seed:* tokens before splicing into the shell so registered
    # renderers can produce HTML the shell template doesn't know about.
    content = expand_seed_tokens(content, context)
    if (page_dir / "app.js").is_file():
        content = app_body(slug, bundle_page(page_dir, slug), content)
    context["content"] = content

    html = render(shell, context)
    out_path.parent.mkdir(parents=True, exist_ok=True)  # supports slug-with-slashes
    out_path.write_text(html, encoding="utf-8")
    try:
        rel = out_path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = out_path
    print(f"  ✓ {slug:<28}  →  {rel}")
    return out_path, config, False


def clean_output() -> None:
    """Wipe `output/` before rebuilding so deleted pages don't linger.
    `compile.py` owns this directory entirely. Anything you put here
    by hand will be removed on the next build. Use `core/static/` for
    files that should be copied in by `copy_static()`."""
    if not OUTPUT_DIR.is_dir():
        return
    for item in OUTPUT_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_static() -> int:
    if not STATIC_SRC.is_dir():
        return 0
    count = 0
    for src in STATIC_SRC.rglob("*"):
        if src.is_file():
            rel = src.relative_to(STATIC_SRC)
            dst = OUTPUT_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1
    return count


# The g-design reference (its apps/docs: guideline and component cards) is
# copied in at compile time for the /design page, not linked at runtime, the
# same vendoring g-design asks of every consumer. G_DESIGN_DOCS points at that
# checkout; unset or missing, the page says so. Each card's first line is an
# `<!-- @dsCard group= name= subtitle= -->` comment, which becomes the index.
DESIGN_OUT = OUTPUT_DIR / "assets" / "design"
DS_CARD_RE = re.compile(r'<!--\s*@dsCard\s+(.*?)-->')
DS_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def copy_design_docs() -> int:
    src = Path(os.environ.get("G_DESIGN_DOCS", "")).expanduser()
    if not os.environ.get("G_DESIGN_DOCS") or not src.is_dir():
        return 0
    shutil.copytree(src, DESIGN_OUT, dirs_exist_ok=True)
    cards = []
    for card in sorted(src.glob("*/*.card.html")):
        with card.open(encoding="utf-8") as f:
            m = DS_CARD_RE.search(f.readline())
        if not m:
            continue
        attrs = dict(DS_ATTR_RE.findall(m.group(1)))
        cards.append({
            "group": attrs.get("group", card.parent.name.capitalize()),
            "name": attrs.get("name", card.stem),
            "subtitle": attrs.get("subtitle", ""),
            "path": card.relative_to(src).as_posix(),
        })
    (DESIGN_OUT / "cards.json").write_text(json.dumps(cards), encoding="utf-8")
    return len(cards)


# ---------- Manifest auto-stub --------------------------------------------

# Stub template uses `{key}` placeholders that we substitute one-by-one.
# We deliberately avoid `str.format` so titles/descriptions containing
# `{` or `}` (entirely possible in user data) don't crash the build.
DEFAULT_STUB_BODY = (
    '<article class="seed-stub">'
    '<h1>{title}</h1>'
    '<p>{description}</p>'
    '<p><em>This page was auto-generated from <code>data/manifest.json</code>. '
    'Add a hand-written <code>pages/{prefix}-{slug}/</code> directory to override.</em></p>'
    '</article>'
)


def _fill_stub(template: str, **fields: str) -> str:
    """Substitute `{key}` placeholders. User-supplied fields (title,
    description) are HTML-escaped; structural fields (slug, prefix) are
    already validated by `_safe_slug`, so escape is a harmless no-op."""
    out = template
    for key, value in fields.items():
        out = out.replace("{" + key + "}", html.escape(str(value), quote=True))
    return out


def load_manifest() -> dict:
    path = Path(os.environ.get("SEED_MANIFEST_PATH") or str(DATA_DIR / "manifest.json"))
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def emit_manifest_stubs(shell: str, handled_slugs: set[str]) -> tuple[int, int]:
    """Returns (built, errors). Errors are counted (not raised) so a single
    bad manifest entry doesn't kill the whole build."""
    manifest = load_manifest()
    if not manifest:
        return 0, 0
    items = manifest.get("items") or manifest.get("entries") or []
    if not items:
        return 0, 0

    prefix = os.environ.get("SEED_MANIFEST_PREFIX", "item")
    if not _safe_slug(prefix):
        print(f"  ✗ manifest: unsafe prefix {prefix!r}")
        return 0, 1
    template_name = os.environ.get("SEED_MANIFEST_TEMPLATE", "stub.html")
    template_path = TEMPLATES_DIR / template_name
    template = (
        template_path.read_text(encoding="utf-8")
        if template_path.is_file()
        else DEFAULT_STUB_BODY
    )

    built = 0
    errors = 0
    for item in items:
        slug = item.get("slug")
        if not slug:
            continue
        page_slug = f"{prefix}-{slug}"
        if page_slug in handled_slugs or slug in handled_slugs:
            continue
        if not _safe_slug(page_slug):
            print(f"  ✗ manifest: unsafe slug {slug!r}")
            errors += 1
            continue
        out_path = _safe_output_path(page_slug)
        if out_path is None:
            print(f"  ✗ manifest: slug {slug!r} resolves outside output/")
            errors += 1
            continue
        body = _fill_stub(
            template,
            slug=slug,
            prefix=prefix,
            title=item.get("title", slug),
            description=item.get("description", ""),
        )
        ctx = {
            **DEFAULTS,
            "title": item.get("title", slug),
            "description": item.get("description", ""),
            "slug": page_slug,
            "body_class": "is-stub",
            "content": body,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render(shell, ctx), encoding="utf-8")
        built += 1
    return built, errors


# ---------- The page tree: the rail and the hub tiles ---------------------
#
# One tree, from the configs, drives both the rail and every hub's tiles, so
# they cannot drift. A rail entry is a page with `nav: true` (and not
# `web_nav: false`); its children are the other members of its `tabs` group.
_PAGES: list[dict] = []


def page_href(config: dict) -> str:
    return config.get("href") or f"/{config.get('slug', '')}"


def children_of(config: dict, configs: list[dict]) -> list[dict]:
    """The pages nested under a parent: its `tabs` group less itself, in order."""
    group = config.get("tabs")
    if not group:
        return []
    return sorted((c for c in configs if c is not config and str(c.get("tabs")) == str(group)),
                  key=lambda c: c.get("order", 999))


def page_tree(configs: list[dict]) -> list[tuple[str, list[tuple[dict, list[dict]]]]]:
    """[(section, [(entry, children)])] in rail order."""
    from collections import defaultdict

    sections: dict[str, list[dict]] = defaultdict(list)
    for c in configs:
        if c.get("nav") and c.get("web_nav", True):
            sections[c.get("nav_section") or c.get("title", "Other")].append(c)
    first = {sec: min(c.get("order", 999) for c in pages) for sec, pages in sections.items()}
    return [(sec, [(c, children_of(c, configs)) for c in sorted(sections[sec], key=lambda c: c.get("order", 999))])
            for sec in sorted(sections, key=lambda s: first[s])]


def _child_label(config: dict) -> str:
    return config.get("tab_label") or config.get("nav_label") or config.get("title", config.get("slug", ""))


def build_nav_html(configs: list[dict]) -> str:
    """The rail (kit .nav-list): a .nav-head per section, a .nav-item per
    entry, and a parent's children nested in a kit .nav-group. chrome.js marks
    the current item and opens its group."""
    def item(c: dict, label: str, cls: str = "nav-item", icon: bool = True) -> str:
        glyph = f'<i class="ph ph-{html.escape(str(c.get("nav_icon", "circle")))}" aria-hidden="true"></i>' if icon else ""
        return (f'<a class="{cls}" href="{html.escape(page_href(c))}">{glyph}'
                f'<span class="ellipsis">{html.escape(str(label))}</span></a>')

    parts = []
    for sec, entries in page_tree(configs):
        parts.append(f'      <div class="nav-head">{html.escape(str(sec))}</div>')
        for c, kids in entries:
            label = c.get("nav_label") or c.get("title", c.get("slug", ""))
            if not kids:
                parts.append("      " + item(c, label))
                continue
            parts.append(f'      <div class="nav-group" data-group="{html.escape(str(c["tabs"]))}">')
            parts.append('        <div class="nav-group-row">' + item(c, label)
                         + f'<button class="nav-twist" type="button" aria-label="{html.escape(str(label))} pages"'
                           ' aria-expanded="false"></button></div>')
            parts.append('        <div class="nav-children">'
                         + "".join(item(k, _child_label(k), "nav-item nav-child", icon=False) for k in kids)
                         + "</div>")
            parts.append("      </div>")
    return '    <nav class="nav-list" aria-label="Pages">\n' + "\n".join(parts) + "\n    </nav>"


def _tile(c: dict) -> str:
    line = c.get("tile_line")
    line_attr = f' data-line="{html.escape(str(line))}"' if line else ""
    note = c.get("tile_note") or c.get("description", "")
    return (f'<li><a class="card tile hub-tile" href="{html.escape(page_href(c))}">'
            '<div class="tile-head">'
            f'<span class="tile-title ellipsis">{html.escape(_child_label(c))}</span>'
            f'<i class="ph ph-{html.escape(str(c.get("nav_icon", "circle")))} muted" aria-hidden="true"></i></div>'
            '<div class="tile-body">'
            f'<p class="tile-strong num hub-line"{line_attr}></p>'
            f'<p class="muted tile-note">{html.escape(str(note))}</p>'
            "</div></a></li>")


def hub_tiles(slug: str) -> str:
    """A hub's tiles: one per child page, each with its live line slot
    (core/static/js/hub.js fills `data-line`)."""
    page = next((c for c in _PAGES if c.get("slug") == slug), None)
    kids = children_of(page, _PAGES) if page else []
    if not kids:
        return ""
    return ('<ul class="tile-grid hub-tiles" aria-label="Pages here">'
            + "".join(_tile(k) for k in kids) + "</ul>")


def hub_head(context: dict) -> str:
    """A hub's page head (title, one line, the pulse tagline where the page
    asks for it) and its tiles."""
    page = next((c for c in _PAGES if c.get("slug") == context["slug"]), {})
    tagline = page.get("tagline")
    tag = (f'<a class="hub-tagline ellipsis" href="/pulse" data-line="tagline:{html.escape(str(tagline))}" hidden></a>'
           if tagline else "")
    return ('<div class="hub-top">'
            '<div class="page-head"><div class="page-head-text">'
            f'<h1 class="page-title">{html.escape(str(context.get("title", "")))}</h1>'
            f'<p class="page-sub">{html.escape(str(context.get("description", "")))}</p>{tag}'
            "</div></div>" + hub_tiles(context["slug"]) + "</div>")


def parent_of(config: dict) -> dict | None:
    """The page a page sits under: its group's head, or for a page off the
    rail the page its `nav_current` names."""
    if config.get("tabs") and not config.get("nav"):
        return next((c for c in _PAGES if c.get("nav") and str(c.get("tabs")) == str(config["tabs"])), None)
    if config.get("nav_current"):
        return next((c for c in _PAGES if page_href(c) == config["nav_current"] and c.get("slug") != config.get("slug")), None)
    return None


def crumbs(config: dict) -> str:
    """The top bar's title: `Parent > Page` for a nested page, else the
    title. A child is named as the rail names it."""
    parent = parent_of(config)
    if not parent:
        return f'<span class="topbar-title">{html.escape(str(config.get("title", "")))}</span>'
    label = _child_label(config) if config.get("tabs") else config.get("title", "")
    return ('<nav class="topbar-crumbs" aria-label="Breadcrumb">'
            f'<a class="hide-sm" href="{html.escape(page_href(parent))}">{html.escape(str(parent.get("nav_label") or parent.get("title", "")))}</a>'
            '<span class="crumb-sep hide-sm" aria-hidden="true"></span>'
            f'<span class="topbar-title" aria-current="page">{html.escape(str(label))}</span></nav>')


def _band_heads() -> dict:
    """slug -> (label, href, live line) for a layout row's `head`."""
    return {c.get("slug"): (c.get("nav_label") or c.get("title", ""), page_href(c), c.get("tile_line"))
            for c in _PAGES}


register_token("hub-head", hub_head)
register_token("hub-tiles", lambda context: hub_tiles(context["slug"]))


def _embed_bundle(slug: str) -> str:
    """Another Preact page's bundle, run inside this page (Brain carries
    Graph as a panel). The bundle decides where it mounts."""
    status = bundle_page(PAGES_DIR / slug, slug)
    if status["state"] == "failed":
        return ""
    name = _bundle_name(slug)
    parts = []
    if "css" in status:
        parts.append(f'<link rel="stylesheet" href="{BUNDLE_URL}/{name}.css?v={status["css"]}">')
    parts.append(f'<script type="module" src="{BUNDLE_URL}/{name}.js?v={status["js"]}"></script>')
    return "\n".join(parts)


for _app in sorted(PAGES_DIR.glob("*/app.js")):
    register_token(f"embed-{_app.parent.name}", lambda context, slug=_app.parent.name: _embed_bundle(slug))


def stamp_shell_assets(shell: str) -> str:
    """Append ?v=<content hash> to the shell's own /css, /js and /assets links.

    server.py lets browsers cache those for a day without asking, so an
    unversioned URL keeps serving the old file after a deploy: the page's HTML
    (no-cache) updated, its stylesheet did not, and the sidebar mark rendered
    as an empty square. A changed file now gets a new URL."""
    def stamp(m: re.Match) -> str:
        src = STATIC_SRC / m.group(2)
        # a font preload must match the unstamped URL its stylesheet requests
        if not src.is_file() or src.suffix == ".woff2":
            return m.group(0)
        digest = hashlib.sha256(src.read_bytes()).hexdigest()[:10]
        return f'{m.group(1)}/{m.group(2)}?v={digest}"'

    return re.sub(r'((?:href|src)=")/((?:css|js|assets)/[^"?#]+)"', stamp, shell)


def main() -> None:
    if not PAGES_DIR.is_dir():
        sys.exit(f"ERROR: {PAGES_DIR} not found")

    OUTPUT_DIR.mkdir(exist_ok=True)
    clean_output()
    shell = load_shell()

    # First pass: collect all configs to build the dynamic nav.
    all_configs: list[dict] = []
    for page_dir in sorted(PAGES_DIR.iterdir()):
        if not page_dir.is_dir() or page_dir.name.startswith("_"):
            continue
        cfg_file = page_dir / "config.json"
        if cfg_file.is_file():
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                cfg.setdefault("slug", page_dir.name)
                all_configs.append(cfg)
            except json.JSONDecodeError:
                pass

    _PAGES[:] = all_configs
    nav_html = build_nav_html(all_configs)
    # Pre-inject nav into the shell so {{! nav_pages }} resolves without
    # per-page context pollution. Use a literal string replace so the
    # TOKEN_RE substitution loop never sees it.
    shell = shell.replace("{{! nav_pages }}", nav_html)
    shell = stamp_shell_assets(shell)

    print("Compiling pages...")
    built = 0
    errors = 0
    handled: set[str] = set()
    for page_dir in sorted(PAGES_DIR.iterdir()):
        if not page_dir.is_dir() or page_dir.name.startswith("_"):
            continue
        out, config, err = compile_page(page_dir, shell)
        if out:
            built += 1
        if config:
            handled.add(config.get("slug", page_dir.name))
        if err:
            errors += 1

    write_bundle_status()
    failed = sorted(s for s, st in _bundle_status.items() if st["state"] != "built")
    if failed:
        print(f"  ⚠ Preact pages not on their newest build: {', '.join(failed)} (var/bundles/status.json)")

    stub_built, stub_errors = emit_manifest_stubs(shell, handled)
    errors += stub_errors
    if stub_built:
        print(f"  + {stub_built} stub page(s) auto-emitted from manifest")

    print()
    static_count = copy_static()
    if static_count:
        print(f"Copied {static_count} static file(s) from {STATIC_SRC.relative_to(PROJECT_ROOT)} → output/")
    design_count = copy_design_docs()
    if design_count:
        print(f"Copied {design_count} g-design card(s) → output/assets/design/")
    print(f"Done. {built} page(s) compiled.")
    if errors:
        sys.exit(f"FAILED: {errors} page(s) had errors")


if __name__ == "__main__":
    main()
