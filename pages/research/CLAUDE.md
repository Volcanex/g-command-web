# Research

The Research group under Knowledge: one rail page per research area, each
with its own sub-views (`?view=<id>`, the page's tabs). `/research` itself
is a 301 to the first area (`MOVED` in `server.py`).

`areas.json` is the registry. An area names its checkout (`root`, a sibling
of this one, overridden by `RESEARCH_<ROOT>_DIR` with `-` as `_`), a `path`
inside it, folders never read (`exclude`), filename fragments never read
(`deny`) and its views. Each view has a `kind`:

- `paper`: one Markdown file, headings as its contents.
- `docs`: a list of Markdown files from `globs` (minus `skip`), one shown at
  a time (`&doc=`); `bib` adds a reference count.
- `claims`: the status paragraphs under `section` in a paper, one claim per
  sentence, each `links` match tied to live g-levels evidence (registry,
  hooks, sensors, review, blocking, results, silent, charters, design,
  domain) through `glevels.export`. Counts and states only, never notes or
  waiver reasons. `then` holds the paper's own counts for comparison.
- `tables` (CSV and TSV, first 200 rows) and `charts` (images served by
  `GET /api/research/<area>/file`, only paths the charts view lists).
- `judge`: blind pairwise judging of the sets the `globs` find
  (`runs/<run>/judge/pairs.json`), one pair at a time (`&set=<run>`). Pages
  come from `GET /api/research/<area>/judge/<run>/page/<name>` (names
  `[a-z0-9]{6,16}.html` in that set's `judge/pages/` only, sent with a
  `sandbox` CSP so they get an opaque origin) into iframes that never get
  allow-same-origin. `POST .../judge/<run>/vote` appends one line to
  `votes.jsonl` beside `pairs.json`, and the latest line per pair wins.
  `judge-key.json` (pages to arms) is never read, and nothing shows an arm,
  a file name or a tally.
- `ans-runs` and `ans-atlas`: ANS aggregates from `runs/ans.sqlite`
  (read-only) and the observed atlas bundles. Raw trajectories are never
  read.

Adding an area: an entry in `areas.json` and a page dir
`pages/research-<id>/` (`config.json` with slug `research/<id>`,
`tabs: research`, its own `nav_icon`, plus `content.html` and a one-line
`app.js` calling `mountArea("<id>")`). `tests/test_research_api.py` checks
the two match.

Everything is read from disk on each request, nothing is copied here. A
missing checkout or file is an empty state naming the path, so the
dissertation area fills in as its job writes files. Its `data/` folder is
private raw data and is excluded, as is any file named for prompts. ANS is a
private repo: it shows only behind this site's gate, like every route here.

`area.js` draws every area, `md.js` renders Markdown to Preact nodes
without parsing HTML, `area.css` holds the layout.
