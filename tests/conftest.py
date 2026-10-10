import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Page APIs read ADMIN_COOKIE_VALUE (no default) at import, and test modules
# import them at collection time, before the autouse fixture below runs.
os.environ.setdefault("ADMIN_COOKIE_VALUE", "ok")


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    """Every test gets a known cookie name/value and a known token, so
    assertions don't depend on whatever happens to be in the real .env."""
    monkeypatch.setenv("ADMIN_COOKIE", "seed_admin")
    monkeypatch.setenv("ADMIN_COOKIE_VALUE", "ok")
    monkeypatch.setenv("GADMIN_TOKEN", "test-secret-token")


@pytest.fixture
def manifest_dir(tmp_path, monkeypatch):
    """A small manifest with three services grouped under two repos, so
    tests never touch the real instance manifest."""
    manifest = {
        "services": [
            {"id": "alpha", "repo": "alpha", "domain": "alpha.example.com", "port": 9001},
            {"id": "beta", "repo": "beta", "domain": "beta.example.com", "port": 9002},
            {"id": "noport", "repo": "noport"},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setenv("GCORE_DIR", str(tmp_path))
    return tmp_path
