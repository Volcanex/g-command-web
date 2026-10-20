# Templates: the shared shell

`shell.html` is the outer HTML every page is wrapped in. `compile.py`
replaces `{{ content }}` with each page's `content.html` fragment and
interpolates other `{{ key }}` tokens from the page's `config.json`
(falling back to defaults in `compile.py`).

## Tokens available by default

- `{{ title }}`: from page config, default `"Untitled"`
- `{{ description }}`: from page config, default `""`
- `{{ site_name }}`: default `"Seed"` (override in `compile.py` DEFAULTS)
- `{{ slug }}`: always set, equal to `config.slug` or the directory name
- `{{ brain_api }}`: the brain API origin from `BRAIN_API`, the same on every page. The shell puts it in `<meta name="brain-api">` and exposes it as `window.BRAIN_API`
- `{{ g_command }}`: `https://` plus `PUBLIC_HOST`, or empty when that is unset. The shell puts it in `<meta name="g-command">`, which the g-admin bar reads for its ticket-count and "Command centre" links
- `{{ content }}`: the page body fragment
- `{{! subnav }}`: the page's tab strip when its config sets `tabs`, else
  empty (built by `build_subnavs()` in `compile.py`)
- Any other string/number field in `config.json` (e.g. `{{ author }}`)

These fill the shell only: `content.html` is spliced in raw and not
scanned for `{{ }}`. A page body quotes an instance value through a
`<!-- seed:NAME -->` token instead, expanded (escaped) by `compile.py`
before the splice. Built in: `mcp_url` (`MCP_URL`), `mcp_headless_url`
(`MCP_HEADLESS_URL`), `mcp_headless_host` (its host) and `public_origin`
(`https://` plus `PUBLIC_HOST`). Each falls back to an example.com
placeholder, so no page names the owner's hosts. Every
`pages/*/panels/*.html` file is also a token, `panel-{name}`, expanded raw:
that is how the dashes share panels.

## Adding a nav link

The nav is data-driven: `compile.py`'s `build_nav_html()` groups every
page with `nav: true` by `nav_section` (ordered by `order`) and injects
the result into `shell.html` at the `{{! nav_pages }}` token. There are no
hand-written sections: the sidebar foot carries icon links to `/setup`
and `/logout` beside the density and theme toggles. To add a page to the
sidebar, set `nav`/`nav_section`/`nav_icon`/`nav_label`/`order` in its
`config.json`, no shell edit. To put it under an existing entry instead,
set `nav: false`, `tabs` to that entry's group and a `tab_label`
(`pages/CLAUDE.md` lists the groups). `chrome.js` marks the current link,
and on a tab page with no link of its own it marks the group's entry.

## Styling: g-design

The shell links the vendored g-design pack (`core/static/css/gsys/`:
`g.css` + `g-ui.js` + `fonts/`, produced by g-design's
`scripts/vendor.mjs`. Never hand-edit,
re-vendor to update) plus `core/static/css/gsys/chrome.css` (g-command-web's
sidebar / top bar / status line on `.g-shell`). Dark is the default (no
`data-theme` attribute); the sidebar-foot toggles flip theme/density via
`g.theme` / `g.density` (localStorage keys `g-theme`/`g-density`,
applied pre-paint by an inline `<head>` script). Page CSS goes in that
page's `content.html` `<style>` block using g-design alias tokens only;
the contract is the `g-design` skill.

The legacy bridge era is over: every page carries `"gsys": true` in its
`config.json` and the bridge files, `body.legacy` handling and old token
pack were deleted. The flag is now vestigial but harmless.

Gotcha: `token-select.js` splits text into token spans; inside g-design
badges/buttons (inline-flex + gap) each span becomes a gapped flex item.
Scope `data-tokens` to prose, or mark components `data-no-tokens`.

## body_class

`shell.html` interpolates `{{ body_class }}` on `<body>`. Set
`"body_class": "is-something"` in a page's `config.json` to scope
overrides without polluting global stylesheets. The login page uses
`login-page` (console.css hides the sidebar/top/status for it);
full-dash, home and ops use `full-dash-page` (full-bleed, no measure cap).

## Inside the apps
The G-Command iPhone and Mac apps load web pages with ` GCommandApp/<version>`
in the user agent. A head script then sets `data-app` on `<html>`, and
`chrome.css` hides the sidebar, top bar and status bar: the app draws the
navigation and title. Browsers never send the marker, so the site itself is
unchanged.
