#!/usr/bin/env python3
"""PageInputs serve command: run this checkout's server:app on a port with an invented session.

Usage: python3 .glevels/serve.py PORT

It serves whatever output/ already holds. It never runs compile.py and never writes into
output/ or var/: production serves from this working tree. Every secret is invented, every
upstream is a dead loopback port, and every path the app writes or reads for live data
points into a fresh temp dir under /tmp, so nothing real is reached.
"""

import os
from pathlib import Path
import sys
import tempfile


REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv/bin/python3"
COOKIE = "glevels-fixture-cookie-only"
DEAD = "http://127.0.0.1:1"


def fixture_env(port, run):
    (run / "empty-brain").mkdir(exist_ok=True)
    (run / "empty-gcore").mkdir(exist_ok=True)
    return {
        "HOME": os.environ.get("HOME", "/root"), "USER": os.environ.get("USER", "root"),
        "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
        "HOST": "127.0.0.1", "PORT": str(port),
        "ADMIN_PASSWORD": "glevels-fixture-demo", "ADMIN_COOKIE_VALUE": COOKIE, "ADMIN_COOKIE_SECURE": "0",
        "BRAIN_UPSTREAM": DEAD, "BRAIN_API_URL": DEAD,
        "BRAIN_ROOT": str(run / "empty-brain"), "GCORE_DIR": str(run / "empty-gcore"),
        "G_RUNNER_TOKEN_FILE": str(run / "nonexistent-runner-token"),
        "G_CONTENT_TOKEN_FILE": str(run / "nonexistent-content-token"),
        "STUDIO_ORIGIN": DEAD,
        # Loopback services on this host the app would otherwise reach.
        "VOICE_URL": DEAD, "VOICE_LIVE_URL": "ws://127.0.0.1:1/live", "WAGES_URL": DEAD,
        "GSITE_URL": DEAD, "G_RUNNER_URL": DEAD, "G_CONTENT_URL": DEAD, "GBROWSER_LOCAL_URL": DEAD,
        "STUDIO_GADMIN_URL": DEAD,
        # Files the app writes default into var/ of this tree.
        "GCOMMAND_DEVICES": str(run / "devices.json"), "GCOMMAND_PUSH_TOKENS": str(run / "push-tokens.json"),
        "UPLOAD_DIR": str(run / "uploads"), "VOICE_UPLOAD_DIR": str(run / "voice-uploads"),
        "GADMIN_DB_PATH": str(run / "gadmin.db"),
    }


def main():
    if len(sys.argv) == 2:
        port = int(sys.argv[1])
        run = Path(tempfile.mkdtemp(prefix="glevels-command-"))
        os.execve(str(PYTHON), [str(PYTHON), str(Path(__file__).resolve()), str(port), "--fixture"],
                  fixture_env(port, run))
    if len(sys.argv) != 3 or sys.argv[2] != "--fixture":
        sys.exit("usage: serve.py PORT")
    port = int(sys.argv[1])
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    from server import app
    import uvicorn

    async def fixture(scope, receive, send):
        # Every request carries the invented admin cookie, so the gate opens without a login.
        if scope["type"] in ("http", "websocket"):
            scope = dict(scope)
            headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"cookie"]
            scope["headers"] = headers + [(b"cookie", f"seed_admin={COOKIE}".encode())]
        await app(scope, receive, send)

    uvicorn.run(fixture, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
