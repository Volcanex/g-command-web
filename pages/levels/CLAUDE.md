# levels

`/levels`, a tab in the System group: g-levels on one page. Gates, charters and their
links as a diagram, results per gate over time, the backlog of candidate gates, the
share of Gabriel's prompts per level per week, and a taste-sampling panel.

- `api.py` (`/api/levels`) holds no logic: `GET /snapshot` and `GET /sample` call
  `glevels.export` from the g-levels checkout beside this one (`GLEVELS_DIR` overrides),
  read fresh on every request. `POST /grade` runs `glevels grade <id> agree|disagree`,
  so the CLI stays the only writer of the results log.
- The backlog quotes Gabriel's own prompts. Every route checks the admin cookie inline,
  because the page gate in `server.py` does not cover `/api/*`.
- The backlog and the level summary are dated files in g-levels' gitignored `var/`
  (`backlog-*.json`, `levels-summary-*.json`); the newest of each is read. A newer
  classifier run only needs its file dropped there.
- `content.html` holds the loader (`window.LV`: one fetch, `LV.on(fn)`, `LV.reload()`).
  Each panel is its own `panels/levels-*.html` with styles scoped under its section id.
  Panel files are global compile tokens, hence the `levels-` prefix.
