# full-dash

Whole-G-System dashboard page. `content.html` is assembled by hand from the
panel fragments in `panels/`: **edit the fragment, then re-inline it into
content.html** (mechanical copy between the panel's start/end comment
markers). There is deliberately no build script.

`api.py` exposes `GET /api/full-dash/diagram`, the instance's
`render.diagram_elements()` as Cytoscape elements, and
`GET /api/full-dash/voice-health`, both admin-gated inline.

The page is on native g-design (`"gsys": true` in `config.json`), so the
legacy token bridge does **not** apply here: only g-design alias tokens
resolve.

## Fragment contract (binding on every panel)

- One panel = one file `panels/{name}.html`. A panel touches nothing else
  in the repo.
- Structure, exactly:

```html
<section class="card fd-panel" id="fd-{name}">
  <header class="fd-panel-head">
    <i class="ph ph-{icon}"></i>
    <h2 class="card-title">{Title}</h2>
    <span class="fd-spacer"></span>
    <span class="fd-meta" data-meta></span>
    <a class="btn btn-tertiary btn-sm btn-icon" href="/{page}" data-tip="Open {page}"
       aria-label="Open {page}"><i class="ph ph-arrow-up-right"></i></a>
  </header>
  <div class="fd-body" data-body><em class="fd-loading">Loading…</em></div>
</section>
<style>/* optional, every selector scoped under #fd-{name} */</style>
<script>(function () { /* IIFE; reads window.FD only; no globals created */ })();</script>
```

- No grid/placement CSS: panel placement is owned by content.html.
- g-design alias tokens only (`--surface-1/2`, `--card-bg`, `--text-primary/
  -secondary/-placeholder`, `--border/-subtle`, `--sp-1..8`, `--radius/-sm/
  -card`, `--font-ui/-mono`, `--font-size-ui/-body`, `--ok/-warn/-danger-text`,
  `--chart-1..6`, `--dur-*`, `--ease-out`). No raw hex in CSS, no old G-pack
  names (`--fg`, `--t-xs`, `--space-N`, `--rule-thin`, `--status-up`…), no
  `text-transform: uppercase`, sentence case in all copy, no em dashes.
- Statuses are badges (`.badge badge-ok/warn/danger/plain`), row lists are
  `.table` inside `.table-wrap`, groups are `.fd-group` + `.fd-group-label`.
  Panel tables are `table-layout: fixed` (see the shared block in
  content.html), so give each column an explicit width class or it splits the
  leftover space.
- Anything that updates in place carries `font-variant-numeric: tabular-nums`.
- Dark is the default; both themes must work. The canvas panels (3D graph,
  Cytoscape) hold **copies** of whatever colour they were handed, so they
  resolve through `FD.color` and re-resolve on a `data-theme` MutationObserver.
  Anything in the DOM should use `var(--chart-N)` instead, which follows the
  theme for free.
- Pinned-version CDN `<script src>` allowed inside the fragment.
- NEVER write the two characters `{` `{` adjacent anywhere in a fragment:
  compile.py token substitution consumes them. Build such strings in JS via
  concatenation if ever needed.
- Failure must render via `FD.fail(...)`, never a blank panel. The message
  says what is missing and what happens next; the raw exception goes in the
  third argument, which lands on the element's `title`.

## window.FD helper (defined in content.html before all fragments)

- `FD.BRAIN`: the brain API origin, `window.BRAIN_API` from the shell (`BRAIN_API` at compile time)
- `FD.fetchJSON(url, {ttl})` / `FD.fetchText(url, {ttl})`: fetch wrappers;
  reject on `!res.ok`; in-memory TTL-ms cache deduping shared URLs
- `FD.poll(fn, ms)`: runs `fn()` immediately, then every `ms`; skips ticks
  while `document.hidden`
- `FD.fail(el, msg, detail)`: standard error state into `el`; `detail` becomes
  the `title`
- `FD.empty(el, msg)`: muted empty state
- `FD.rel(iso)`: relative time string ('4m ago')
- `FD.color(name, fallback)`: a custom property resolved to plain sRGB
  `rgb(...)`. g-design serves its scales as `color(display-p3 ...)` where the
  browser supports it, which three.js and Cytoscape cannot parse; this paints
  one pixel and reads it back. Use it for anything handed to a canvas library.
- `FD.palette`: array of the resolved `--chart-1`..`--chart-6` colours
- `FD.repalette()`: re-resolves `FD.palette` in place after a theme change
