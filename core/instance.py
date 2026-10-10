"""Where the checkouts this dashboard reads from live.

Each path is an env var first, then a checkout beside this one, new name
before legacy name, the way g-env's resolver finds the instance. On a host
that keeps every repo in one directory that is the live layout, so the
service needs no extra env.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sibling(*names: str) -> Path:
    for name in names:
        if (ROOT.parent / name).is_dir():
            return ROOT.parent / name
    return ROOT.parent / names[0]


def gcore_dir() -> Path:
    """The instance checkout: its manifest.json, conventions.md and passport."""
    return Path(os.environ.get("GCORE_DIR") or sibling("gp-core", "gcore"))
