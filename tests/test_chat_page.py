"""Chat: a Preact page under Dash on the apps' Voice session (pages/chat)."""
import json
import subprocess
from pathlib import Path

import pytest

import compile as c

PAGE = Path(__file__).resolve().parent.parent / "pages" / "chat"


def test_chat_sits_last_under_dash_and_stays_out_of_the_apps_nav():
    config = json.loads((PAGE / "config.json").read_text())
    dash = [json.loads(p.read_text()) for p in PAGE.parent.glob("*/config.json")]
    dash = [d for d in dash if d.get("nav") and d.get("nav_section") == "Dash"]
    assert config["nav_section"] == "Dash" and config["nav"] is True
    assert config["order"] == max(d.get("order", 0) for d in dash)
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
