import json

from core import native
from core.panels.manifest import build_manifest


def _repo(tmp_path, verified=None):
    (tmp_path / "pages" / "calendar").mkdir(parents=True)
    (tmp_path / "pages" / "calendar" / "content.html").write_text("<p>day view</p>")
    (tmp_path / "core").mkdir()
    sources = ["pages/calendar/content.html"]
    registry = {"v": 1, "screens": {"calendar": {
        "route": "/calendar", "sources": sources, "min_build": 3,
        "verified": verified or native.source_hash(sources, tmp_path)}}}
    path = tmp_path / "core" / "native.json"
    path.write_text(json.dumps(registry))
    return path


def test_a_verified_screen_is_listed(tmp_path):
    path = _repo(tmp_path)
    assert native.native_screens(path, tmp_path) == {"calendar": {"route": "/calendar", "min_build": 3}}


def test_a_changed_source_drops_the_screen_and_says_why(tmp_path):
    path = _repo(tmp_path)
    (tmp_path / "pages" / "calendar" / "content.html").write_text("<p>day view, changed</p>")
    said = []
    assert native.native_screens(path, tmp_path, report=said.append) == {}
    assert "calendar" in said[0] and "pages/calendar/content.html" in said[0]


def test_a_missing_source_drops_the_screen(tmp_path):
    path = _repo(tmp_path)
    (tmp_path / "pages" / "calendar" / "content.html").unlink()
    assert native.native_screens(path, tmp_path) == {}


def test_the_app_manifest_carries_the_current_screens(tmp_path):
    current = {"calendar": {"route": "/calendar", "min_build": 3}}
    assert build_manifest(tmp_path, current)["native"] == current
    assert build_manifest(tmp_path)["native"] == {}
    # Which are current is the check's to flag, not a test failure.
    assert set(json.loads(native.NATIVE_FILE.read_text())["screens"]) == {"calendar", "todo-actions"}
