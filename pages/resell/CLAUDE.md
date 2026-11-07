# resell

Native Resell admin, scaffolded with `scripts/new-view.py`. `config.json` nests
it under the Projects rail group; the group itself is owned elsewhere.

`app.js` draws Dashboard, Pool (filters, pagination, selection, deletion, item
details and recent events), Profit (all sold real stock with frozen cost basis),
and Bots (scaling, configuration, logs and variants), using the shared kit.
Item links use `/resell?view=pool&item=<id>`; screen links use `?view=<name>`.
`app.css` contains token-only page layout. `content.html` is the plain fallback.

`api.py` gates every route with Command's admin cookie and forwards an explicit
allowlist to Resell's existing loopback APIs: pool :7500, registry :7503,
config :7504, network :8890 and telegram :7505. Server-only
`RESELL_<SERVICE>_URL` variables override those origins. No data is stored here.
Stopped bots edit the config service; running bots save through the registry
to retain validation and hot reload. Writes always use the existing endpoints.

At port time the manifest marked depopper retired and every arbitrage service
had zero replicas. Unavailable services produce an offline dashboard and retry
states, never invented item counts or profit. This page does not start services
automatically or redirect the old admin.

`tests/test_resell_api.py` checks auth, allowed routes, forwarding, offline handling, images
and profit pagination with isolated upstreams. `journey.json` records the read
path. Browser verification uses headless Playwright on h only.
