# upload

A plain dropbox for getting files onto the server fast. Files land in
`UPLOAD_DIR` (default `var/uploads` in this checkout, set in `.env` on a
live instance). Nothing else in G-System reads that directory. It is a staging
area, not a content store, so nothing breaks if you empty it.

## Gotchas
- **nginx caps the body, not this code.** The vhost's global
  `client_max_body_size` is `4M`; a dedicated `location /api/upload/`
  block in the dashboard's vhost (`/etc/nginx/sites-available/<host>`)
  raises it to `10G` and sets `proxy_request_buffering off` so nginx
  streams to uvicorn instead of spooling the whole file to its temp
  dir. Change the ceiling there, not here. A 413 in the UI shows as
  "too big" and means that block was lost or bypassed.
- The site-wide gate in `server.py` does not cover `/api/*`, so the
  admin cookie is re-checked in `api.py` on every route.
- Uploads never overwrite: a name collision becomes `foo-1.zip`.
- The browser sends the filename, so it is untrusted: reduced to a
  basename, filtered to `[A-Za-z0-9._-]`, and the resolved path is
  re-checked against `UPLOAD_DIR` before any read, write, or unlink.
- The UI uploads **serially** and uses `XMLHttpRequest` rather than
  `fetch`, because `fetch` still has no upload-progress event.
- The page is native g-design (`"gsys": true`): `.g-dropzone` for the
  pick/drop area, `.g-progress` + `g.progress()` for the per-file bars
  and their `.progress-readout` (percent, bytes, rate, eta), one
  `g.toast({kind:'loading'})` for the whole batch. The dropzone's file
  input is the only store, so the page clears it the moment a batch
  starts, otherwise the component's own file list would shadow the
  progress rows.
- Toast titles are written as HTML by `g-ui`, so browser-supplied file
  names never go in one; they go in the queue rows via `textContent`.
  Stored names are already filtered by `api.py`.
- Delete is hold-to-delete (`.hold-btn`, 900ms), not a `confirm()`
  dialog. New rows need `g.init(tbody)` after render to wire it up.
