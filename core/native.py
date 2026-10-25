"""Hand-ported native screens and whether each is still current (stdlib only).

The apps (g-command-apple) draw panel pages from the panel contract, which
copies nothing. A few screens are ported by hand instead (the Calendar, the
todo actions in chat). Each is listed in core/native.json with the web files
it copies and their hash when someone last confirmed the port matches. When
those files change the screen drops out of the app manifest, so the apps show
the web page until a person or an agent re-verifies it:

    scripts/native_check.py                     report what is current or stale
    scripts/native_check.py --verify calendar   record the port as matching again

The convention is gcore conventions.md, "Native hangs off web".
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATIVE_FILE = ROOT / "core" / "native.json"


def source_hash(sources, root=ROOT):
    digest = hashlib.sha256()
    for source in sorted(sources):
        for value in (source.encode("utf-8"), (Path(root) / source).read_bytes()):
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
    return digest.hexdigest()


def native_screens(path=NATIVE_FILE, root=ROOT, report=lambda message: None):
    """The current screens as {name: {route, min_build}}; stale ones are reported."""
    registry = json.loads(Path(path).read_text())
    current = {}
    for name, screen in registry["screens"].items():
        try:
            verified = source_hash(screen["sources"], root) == screen["verified"]
        except FileNotFoundError:
            verified = False
        if verified:
            current[name] = {key: screen[key] for key in ("route", "min_build")}
        else:
            report(f"native screen '{name}' is stale: {', '.join(screen['sources'])} "
                   "changed since verification - the apps will show the web page")
    return current
