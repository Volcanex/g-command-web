"""Chat: a Preact page at the top of the rail on the apps' Voice session (pages/chat)."""
import json
import subprocess
from pathlib import Path

import pytest

import compile as c

PAGE = Path(__file__).resolve().parent.parent / "pages" / "chat"


def test_chat_sits_at_the_top_of_the_rail_after_home_and_stays_out_of_the_apps_nav():
    config = json.loads((PAGE / "config.json").read_text())
    assert config["nav"] is True and "tabs" not in config
    pages = [dict(json.loads(p.read_text()), slug=p.parent.name) for p in PAGE.parent.glob("*/config.json")]
    top = c.page_tree(pages)[0][1]
    assert [entry.get("slug") for entry, _ in top][:3] == ["index", "chat", "upload"]
    from core.panels.manifest import build_manifest
    tabs = [t["slug"] for s in build_manifest(PAGE.parent)["sections"] for e in s["entries"] for t in [e, *e.get("tabs", [])]]
    assert "chat" not in tabs
    assert config["app_nav"] is False  # the apps draw their own Chat entry


def test_chat_uses_the_app_session_and_its_stream():
    src = (PAGE / "app.js").read_text()
    assert 'const SESSION = "app"' in src
    assert "/api/voice/chat/stream" in src and "/api/voice/history?session=" in src


@pytest.mark.skipif(not c.ESBUILD.is_file(), reason="node_modules not installed (npm ci)")
def test_chat_bundles(tmp_path):
    out = subprocess.run([str(c.ESBUILD), str(PAGE / "app.js"), "--bundle", "--format=esm",
                          f"--outdir={tmp_path}", "--log-level=error"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
