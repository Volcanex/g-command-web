# hours

An **activity tracker**: where the week went across projects, your time against
agent runtime, token spend and usage blocks. `/hours`.

**Pure renderer, like the rest of g-command-web.** It computes nothing. A
separate time-tracking service builds the weekly session snapshot, and this
page fetches it through `api.py` from `WAGES_URL` (default
`http://127.0.0.1:8093`, over localhost).

**Activity only, by design.** `api.py` forwards just `TRACKER_FIELDS`, so
anything else the service keeps never reaches g-command-web. Widen that list
only for activity data. If a page needs more than that, add a route to the
service instead.

## Data flow

```
time-tracking service (refreshes the snapshot on its own timer)
  -> GET $WAGES_URL/api/ledger/sessions/week
  -> g-command-web /api/hours/week                this page's api.py, admin-gated
  -> content.html renders it client-side
```

## Gotchas

- **Two numbers, computed differently on purpose.** `presence` is a *union*
  (parallel sessions don't add up: one person, one place at a time);
  `agent` is a *sum* (concurrent agents really did overlap). Their ratio is
  leverage. Never present agent hours as billable.
- **The by-day chart pairs them side by side, never stacked**. Agent time
  routinely exceeds desk time, so a stack would read as a bigger day rather
  than a more leveraged one.
- **Accent means "your time" throughout**, neutral means machine time. It is a
  semantic, not decoration, and no project owns it: the ranked bars are one
  series, so identity comes from the label and position.
- **Snapshot age is shown, and >6h reads as stale.** If the page looks frozen,
  check the service's refresh timer, not this page.
- **503 means "no snapshot yet", not "broken".** `api.py` forwards that code
  from the service rather than flattening it, so the page can say which.
- The cookie name comes from `ADMIN_COOKIE` in the env, read once in
  `core/auth.py`, so a deployment that renames it needs no change here. Don't
  hardcode it.
