# wages

The g-wages ledger editor, drawn in Command at `/wages` (a tab beside Hours).
g-wages keeps running as its own service (unit `g-wages`, port 8093) and owns
every row and every sum; this page renders what it returns.

## Data flow

```
app.js -> /api/wages/<path>       pages/wages/api.py, this site's gate
       -> $WAGES_URL/api/ledger/<path>   g-wages, loopback, no auth of its own
```

## Gotchas

- **The gate is the only lock.** g-wages has no auth on loopback; its public
  vhost used nginx basic-auth. `api.py` must keep `cookie_ok` first.
- **This is the money surface, Hours is not.** Hours still forwards activity
  fields only (`pages/hours/CLAUDE.md`); do not widen it to reach money,
  use this page.
- **Money arrives formatted.** g-wages formats pence; the page never
  re-derives a balance, so the two cannot drift. `pounds()` only formats raw
  pence fields that g-wages sends unformatted (invoice status, invoice list).
- **Invoice, report and hours basis open as g-wages HTML** through the proxy
  (`/api/wages/c/<slug>/invoice` and so on), so they print exactly as before.
- **Old links.** `wages.gabrielpenman.com` 301s page paths here and proxies
  `/api/` straight to g-wages behind its basic-auth, so scripts keep working.
- **Rail.** A top-level Work entry beside Hours (order 27 to its 26). If Hours
  moves, move Wages with it.
