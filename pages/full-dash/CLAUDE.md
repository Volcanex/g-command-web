# full-dash

Home of the dash panels. Three pages are built from them: `/full-dash`
(both halves, the landing page `/` redirects to), `/home` (the life dash)
and `/ops` (the system dash). Each panel is one file in `panels/`, and
`compile.py` registers every `pages/*/panels/*.html` as a content token, so
a page includes one with `<!-- seed:panel-{name} -->`. Edit the panel file
and recompile; every dash that includes it picks it up. A dash's placement
is the `layout` in its `config.json` (`core/panels/CLAUDE.md`, Layout), which
the Mac app reads too. Its `content.html` is only `<!-- seed:panel-kit -->`
and `<!-- seed:dash-layout -->`, which compiles to the markup and CSS below.

- `kit.html`: `window.FD`, the generic panel renderer `FD.panel`, and the
  shared panel, block and dash-frame CSS. Every dash includes
  `<!-- seed:panel-kit -->` first.
- Every panel renders the server view-model from `GET /api/panels/{name}`,
  built in `core/panels/{name}.py` and specified in `core/panels/CLAUDE.md`.
  The iPhone and Mac apps render the same JSON. What a panel shows (which
  items, their order, copy, tones) is decided there, never in a panel file.
- Life: `calendar` (today and carried over, the next six days as aside
  blocks), `tasks` (open undated todos by priority), `money` (open finance
  and bill todos by due date), `brief` (the pulse brief's bullets).
- System: `health` (down and warn services and dependencies, hosts and
  disk), `compute` (the three quota cards, credit and hours), `tickets`
  (open g-admin tickets), `crons` (problems, then the next runs).

The dash frame (`.fd-dash` grid of `.fd-col` flex columns, `.fd-row` for
side-by-side panels) fills the viewport on a desktop window, so each panel
body scrolls on its own and nothing key sits below the fold at 1280x800.
Under 900px wide or 560px tall it falls back to one scrolling column, so
the generated placement CSS sits in `@media (min-width: 901px) and
(min-height: 561px)`: an id-scoped flex rule outside it would beat the
fallback and collapse the panel. The frame's class is `fd-{slug}`.

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
<style>/* optional layout only, every selector scoped under #fd-{name} */</style>
<script>FD.panel('{name}');</script>
```

- The script is that one line. A panel file never fetches, filters, sorts
  or writes copy: if the JSON lacks something the panel should show, the
  fix is a contract field in `core/panels`, not panel JS.
- Panel CSS is for layout keyed off the rendered structure: the calendar
  places `.fd-split-lead` (its blocks) beside `.fd-split-rest` (the aside
  blocks) and draws a row accent as a trailing dot, compute grids its quota
  meters three across, tickets puts the project on the right.

- No grid/placement CSS: panel placement is owned by each dash's `layout`.
- A panel may appear on several dashes but at most once per page, since
  its id is fixed.
- g-design alias tokens only (`--surface-1/2`, `--card-bg`, `--text-primary/
  -secondary/-placeholder`, `--border/-subtle`, `--sp-1..8`, `--radius/-sm/
  -card`, `--font-ui/-mono`, `--font-size-ui/-body`, `--ok/-warn/-danger-text`,
  `--chart-1..6`, `--dur-*`, `--ease-out`). No raw hex in CSS, no old G-pack
  names (`--fg`, `--t-xs`, `--space-N`, `--rule-thin`, `--status-up`…), no
  `text-transform: uppercase`, sentence case in all copy, no em dashes.
- `FD.panel` draws the contract with the shared classes: a `rows` block
  is `.fd-group` (`.fd-group-label` with a muted `.n` count) holding an
  `.fd-list` of `.fd-item`. In a row, `.fd-tick` is the action, `.fd-lead`
  and `.fd-mark` chips sit before and after `.t` (the ellipsised title),
  `.d` is the detail and `.k` the trail. `.has-accent` draws the accent
  stripe from `data-accent`, `.is-done` and `.is-struck` mark state, and
  `.fd-tone-*` colours text. A `line` is `.fd-line` of chips, a `meter` is
  `.fd-meter` (`.fd-meter-head`: label, badge, `.g-meter`, text, then
  `.fd-meter-sub`), `bullets` are `.fd-bullets` of `details > .fd-bullet`.
  Badge chips are `.badge badge-ok/warn/danger/info/plain`, tips are
  `data-tip`. Unknown block types are skipped. When any block has
  `aside`, the blocks render as `.fd-split` > `.fd-split-lead` +
  `.fd-split-rest`, otherwise in one `.fd-blocks`.
- Anything that updates in place carries `font-variant-numeric: tabular-nums`.
- Dark is the default; both themes must work. Use `var(--chart-N)` and the
  status tokens, which follow the theme for free.
- Pinned-version CDN `<script src>` allowed inside the fragment.
- NEVER write the two characters `{` `{` adjacent anywhere in a fragment:
  compile.py token substitution consumes them. Build such strings in JS via
  concatenation if ever needed.
- Failure never leaves a blank panel: `FD.panel` shows the panel's own
  `message` for `state: "error"`, and for a failed request the last
  message it had (else "{Title} unavailable") with the raw error on the
  element's `title`.

## window.FD helper (kit.html, included before every panel)

- `FD.panel(name)`: renders `#fd-{name}` from `/api/panels/{name}`. Fills
  the header title, icon, meta and link, draws the blocks, polls every
  `refresh` seconds (skipping while the tab is hidden), and runs row
  actions: `body` as JSON to `path` with the cookie, then a refetch, or
  `action.error` as a danger toast on failure. All text goes in through
  `textContent`, and a link that is not a command path (`/...`) is dropped.

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
