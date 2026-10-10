# g-command-web

The web dashboard for G-System. It has
the ops pages, the Brain views (notes, graph, lineage, references, calendar),
live service health, the g-admin ticket queue and a terminal in the browser. It
mostly renders: the data comes from the g-brain API and the instance manifest
(format in g-core). The one store it keeps is the g-admin ticket queue, a
SQLite file at `var/gadmin.db`.

This repo is source-available under the PolyForm Noncommercial 1.0.0 licence.
It is not open source.

## How it works

Each page lives in `pages/<slug>/` as a `content.html` and a `config.json`.
`compile.py` wraps every page in `core/templates/shell.html` and writes the
result to `output/`, which `server.py` serves. API routers are picked up at
startup from `core/api/*.py` and `pages/*/api.py`, so a page with an `api.py`
needs no registration. The UI is built on g-design, vendored into
`core/static/css/gsys/`.

## Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # then fill in ADMIN_PASSWORD and ADMIN_COOKIE_VALUE
set -a
. ./.env
set +a
.venv/bin/python3 compile.py
.venv/bin/python3 server.py
```

Then open `http://127.0.0.1:8080/`. The whole site sits behind one password.
Logging in sets a cookie to `ADMIN_COOKIE_VALUE`, so that value is a secret
too, and the server won't start without it. `openssl rand -hex 32` makes a good
one.

Most pages read live services, such as the g-brain API at `BRAIN_API` and the
manifest under `GCORE_DIR`. A fresh checkout shows empty states until those are wired up.

To run the tests, install `requirements-dev.txt` into the same venv and run
`.venv/bin/pytest tests/ -q`.

## Licence

PolyForm Noncommercial 1.0.0, see `LICENSE`. Copyright Gabriel Penman. The
fonts and icons vendored here keep their own licences, listed in
`THIRD_PARTY_NOTICES`.
