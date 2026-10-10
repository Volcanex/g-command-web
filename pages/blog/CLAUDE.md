# blog

The g-site editor panel. Proxies everything to g-site's admin API
(`/api/admin/*` on `GSITE_URL`, default `http://127.0.0.1:8096`). This
panel holds no data of its own, same as the rest of g-command-web.

## Routes (`api.py`, mounted at `/api/blog`)

- `ANY /api/blog/proxy/{path}`: generic passthrough to
  `{GSITE_URL}/api/admin/{path}`, forwarding method/body/query string and
  attaching `X-Admin-Token`. 502 if g-site is unreachable; upstream
  4xx/5xx bodies are passed through unchanged. 60s timeout on
  `preview`/`publish` paths (they compile an edition), 10s elsewhere.
- `POST /api/blog/upload`: multipart file, re-encoded and forwarded to
  g-site's `POST /api/admin/media`.

## Env

- `GSITE_URL`: g-site base URL (g-command-web `.env`).
- `GSITE_ADMIN_TOKEN`: shared secret, lives in the instance passport
  (`.env` in `GCORE_DIR`), loaded via the
  `/etc/systemd/system/gcommand.service.d/gsite.conf` systemd drop-in, not g-command-web's own
  `.env`.

## Gotchas

- g-site is being built in parallel: treat 502s from the proxy as
  expected until it's live, not a bug here.
- The Generation preview iframe hits g-site directly by URL; pre-flip
  g-site is bound to `127.0.0.1` only, so the iframe may fail to load
  even though the underlying preview call succeeded. The stat badges in
  the Preview card head (and the "Preview ready" toast) are the reliable
  signal until the flip.
- `content.html` builds the generation form by path (`grid.cols`,
  `streaks.thickness_px`, …) and reassembles the full JSON object on
  save. It round-trips whatever g-site returns, so new generation
  config keys don't need a matching UI field to survive a save.
