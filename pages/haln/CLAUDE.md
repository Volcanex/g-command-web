# HALN

Native admin at `/haln`, under Projects. Scaffolded with
`python3 scripts/new-view.py haln --group projects --title HALN`.

`api.py` reads gcommerce's SQLite pool with `mode=ro` and `query_only`.
`HALN_ROOT` defaults to the sibling `gcommerce` checkout; `HALN_DB` defaults
to its `data/pool.db`. No GPool is instantiated, since that can migrate data.
Evidence counts, staging readiness and prompt checks call the existing
gcommerce Python functions from that checkout. They perform no writes.

Overview, pool, decisions, staging, creative, events and orders use the
same records and limits as the old admin. Item, order and prompt-pack
detail URLs use query parameters. The overview refreshes every ten seconds
while visible. Pool search and status filter are local; events filter on
the server. Money remains integer pence until display.

Assets are the existing project files, restricted to recorded paths inside
gcommerce's assets directory. All review verdicts are visible to the
operator, including failed and unreviewed media. Nothing is published.
The existing Phosphor font supplies all icons. No assets are copied here.

The old admin remains running. The fulfilment brain note links to its
existing authenticated page. Shop previews use the shop's existing session.
The old admin has no data-writing web actions, only password login;
creative verdicts and pool transitions remain the project's CLI workflow.

Verification journey: open `/haln`, follow a pipeline status into the pool,
search and clear filters, open an item and its evidence/media/events,
visit decisions and staging, open creative and copy a prompt, filter
events, visit orders. Check 1440x900 and 390x900, dark and light themes.
