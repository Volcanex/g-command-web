"""Chat: a Preact page in the Life group on the apps' Voice session (pages/chat)."""
import json
import subprocess
from pathlib import Path

import pytest

import compile as c

PAGE = Path(__file__).resolve().parent.parent / "pages" / "chat"


def test_chat_sits_in_life_after_the_daily_pages_and_stays_out_of_the_apps_nav():
    config = json.loads((PAGE / "config.json").read_text())
    life = [json.loads(p.read_text()) for p in PAGE.parent.glob("*/config.json")]
    life = sorted((d for d in life if d.get("tabs") == "life" and not d.get("nav")), key=lambda d: d.get("order", 999))
    assert config["tabs"] == "life" and config["nav"] is False
    assert [d["title"] for d in life] == ["Calendar", "Chat"]
    from core.panels.manifest import build_manifest
    tabs = [t["slug"] for s in build_manifest(PAGE.parent)["sections"] for e in s["entries"] for t in e.get("tabs", [])]
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
