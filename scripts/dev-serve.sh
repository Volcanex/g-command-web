#!/usr/bin/env bash
set -euo pipefail

if (( $# < 1 || $# > 2 )) || [[ ! ${1:-} =~ ^[0-9]{1,5}$ ]]; then
  echo "Usage: scripts/dev-serve.sh PORT [STUDIO_ORIGIN]" >&2
  exit 2
fi
dev_port=$((10#$1))
if (( dev_port < 1 || dev_port > 65535 || dev_port == 8089 || dev_port == 8240 )); then
  echo "Choose a port from 1 to 65535 other than production ports 8089 and 8240." >&2
  exit 2
fi

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
dev_python="$repo_dir/.venv/bin/python3"
if [[ ! -x "$dev_python" ]]; then
  dev_python=/home/gabriel/g-command-web/.venv/bin/python3
fi
if [[ ! -x "$dev_python" ]]; then
  echo "No worktree venv or /home/gabriel/g-command-web/.venv/bin/python3 found." >&2
  exit 2
fi

umask 077
export HOST=127.0.0.1 PORT="$dev_port" DEBUG=0
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-$("$dev_python" -c 'import secrets; print("fake-dev-password-" + secrets.token_hex(16))')}"
export ADMIN_COOKIE_VALUE="${ADMIN_COOKIE_VALUE:-$("$dev_python" -c 'import secrets; print("fake-dev-cookie-" + secrets.token_hex(16))')}"
export ADMIN_COOKIE="${ADMIN_COOKIE:-seed_admin}" ADMIN_COOKIE_SECURE=0
export BRAIN_API=/api/brain
export STUDIO_ORIGIN="${2-${STUDIO_ORIGIN:-}}"
export GCOMMAND_DEV_STORAGE_STATE="${GCOMMAND_DEV_STORAGE_STATE:-$repo_dir/var/dev/$PORT/storage-state.json}"

"$dev_python" compile.py
"$dev_python" - <<'PY'
import json
import os
from pathlib import Path

state = Path(os.environ["GCOMMAND_DEV_STORAGE_STATE"])
state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
with state.open("w") as stream:
    json.dump({"cookies": [{
        "name": os.environ["ADMIN_COOKIE"],
        "value": os.environ["ADMIN_COOKIE_VALUE"],
        "domain": "127.0.0.1",
        "path": "/",
        "expires": -1,
        "httpOnly": True,
        "secure": False,
        "sameSite": "Lax",
    }], "origins": []}, stream)
state.chmod(0o600)
print(f"Dev server: http://127.0.0.1:{os.environ['PORT']}", flush=True)
print(f"Signed-in Playwright storage state (0600, gitignored): {state}", flush=True)
print(f"Headless: browser.new_context(storage_state={str(state)!r})", flush=True)
print(f"Spacing: python3 /home/gabriel/g-levels/glevels/spacing.py "
      f"http://127.0.0.1:{os.environ['PORT']}/ --storage-state {str(state)!r}", flush=True)
print("The gate also accepts /login (#password, #login-form), or "
      "POST /api/admin/login with JSON password from ADMIN_PASSWORD. "
      "Keep fake values in the environment; never put them in command arguments.", flush=True)
PY

exec "$dev_python" server.py
