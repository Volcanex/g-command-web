# full-dash

Home of the dash panels. Three pages are built from them: `/full-dash`
(both halves, the landing page `/` redirects to), `/home` (the life dash)
and `/ops` (the system dash). Each panel is one file in `panels/`, and
`compile.py` registers every `pages/*/panels/*.html` as a content token, so
a page includes one with `<!-- seed:panel-{name} -->`. Edit the panel file
and recompile; every dash that includes it picks it up. A page's
`content.html` holds only the kit token, the layout markup and its
placement CSS.

- `kit.html`: `window.FD` and the shared panel and dash-frame CSS. Every
  dash includes `<!-- seed:panel-kit -->` first.
- Life: `calendar` (today, carried over and the next six days, from
  `/api/todos/calendar`), `tasks` (open undated todos by priority),
  `money` (open finance and bill todos by due date), `brief` (the pulse
  brief's bullets, one line each).
- System: `health` (only down and warn services and dependencies, all
  green collapses to one line, plus hosts and disk, from `/api/status`),
  `compute` (Claude week, Claude 5 hour and Codex week with reset times,
  from `/api/compute/pace` and `/state`), `tickets` (open g-admin
  tickets), `crons` (problems, then the next runs, from `/api/crons/list`).

The dash frame (`.fd-dash` grid of `.fd-col` flex columns, `.fd-row` for
side-by-side panels) fills the viewport on a desktop window, so each panel
body scrolls on its own and nothing key sits below the fold at 1280x800.
Under 900px wide or 560px tall it falls back to one scrolling column, so
each page wraps its placement CSS in `@media (min-width: 901px) and
(min-height: 561px)`: an id-scoped flex rule outside it would beat the
fallback and collapse the panel.

`api.py` exposes `GET /api/full-dash/diagram`, the instance's
`render.diagram_elements()` as Cytoscape elements, and
`GET /api/full-dash/voice-health`, both admin-gated inline. No panel uses
them since the 2026-10 redesign; they stay served.

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

- No grid/placement CSS: panel placement is owned by each dash's content.html.
- A panel may appear on several dashes but at most once per page, since
  its id is fixed.
- g-design alias tokens only (`--surface-1/2`, `--card-bg`, `--text-primary/
  -secondary/-placeholder`, `--border/-subtle`, `--sp-1..8`, `--radius/-sm/
  -card`, `--font-ui/-mono`, `--font-size-ui/-body`, `--ok/-warn/-danger-text`,
  `--chart-1..6`, `--dur-*`, `--ease-out`). No raw hex in CSS, no old G-pack
  names (`--fg`, `--t-xs`, `--space-N`, `--rule-thin`, `--status-up`…), no
  `text-transform: uppercase`, sentence case in all copy, no em dashes.
- Statuses are badges (`.badge badge-ok/warn/danger/plain`), row lists are
  `.fd-list` of `.fd-item` (`.t` the ellipsised title, `.k` a right-hand
  fact), groups are `.fd-group` + `.fd-group-label`, overflow is `.fd-more`.
- Anything that updates in place carries `font-variant-numeric: tabular-nums`.
- Dark is the default; both themes must work. Use `var(--chart-N)` and the
  status tokens, which follow the theme for free.
- Pinned-version CDN `<script src>` allowed inside the fragment.
- NEVER write the two characters `{` `{` adjacent anywhere in a fragment:
  compile.py token substitution consumes them. Build such strings in JS via
  concatenation if ever needed.
- Failure must render via `FD.fail(...)`, never a blank panel. The message
  says what is missing and what happens next; the raw exception goes in the
  third argument, which lands on the element's `title`.

## window.FD helper (kit.html, included before every panel)

- `FD.BRAIN`: the brain API origin, `window.BRAIN_API` from the shell (`BRAIN_API` at compile time)
- `FD.fetchJSON(url, {ttl})` / `FD.fetchText(url, {ttl})`: fetch wrappers;
  reject on `!res.ok`; in-memory TTL-ms cache deduping shared URLs, so two
  panels on one page reading the same route make one request. `ttl: 0`
  forces a fresh read (after a write)
- `FD.poll(fn, ms)`: runs `fn()` immediately, then every `ms`; skips ticks
  while `document.hidden`
- `FD.fail(el, msg, detail)`: standard error state into `el`; `detail` becomes
  the `title`
- `FD.empty(el, msg)`: muted empty state
- `FD.plain(s)`: markdown flattened to text (`g.plain` once g-ui has loaded)
- `FD.esc(s)`: `FD.plain` then HTML-escaped, for anything put in innerHTML
- `FD.iso(date)`: local `YYYY-MM-DD`; `FD.day(iso)`: `Tue 13 Oct`
- `FD.rel(iso)`: relative time string ('4m ago')
- `FD.init(el)`: `g.init(el)`, needed after rendering a `.g-meter` or other
  g-ui component into the DOM
