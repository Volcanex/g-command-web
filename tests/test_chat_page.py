"""Chat: a Preact page under Additional tools on the apps' Voice session (pages/chat)."""
import json
import subprocess
from pathlib import Path

import pytest

import compile as c

PAGE = Path(__file__).resolve().parent.parent / "pages" / "chat"


def test_chat_sits_under_additional_tools_and_stays_out_of_the_apps_nav():
    config = json.loads((PAGE / "config.json").read_text())
    assert config["nav"] is True and "tabs" not in config
    pages = [dict(json.loads(p.read_text()), slug=p.parent.name) for p in PAGE.parent.glob("*/config.json")]
    tree = dict(c.page_tree(pages))
    assert "chat" in [entry.get("slug") for entry, _ in tree["Additional tools"]]
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


def test_chat_is_the_one_chat_page_and_voice_moves_here():
    # Read, not imported: importing server mounts every router and swaps modules other tests patch.
    import ast
    tree = ast.parse((PAGE.parent.parent / "server.py").read_text())
    moved = next(ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "MOVED")
    assert moved["voice"] == "/chat"
    assert not (PAGE.parent / "voice").exists()   # the page and its live call client are gone
    pages = [dict(json.loads(p.read_text()), slug=p.parent.name) for p in PAGE.parent.glob("*/config.json")]
    assert not any(p.get("slug") == "voice" or p.get("tab_label") == "Voice" for p in pages)
    from core.api import voice   # the routes Chat and the apps share stay at /api/voice
    paths = {r.path for r in voice.router.routes}
    assert {"/chat/stream", "/history", "/tts", "/live"} <= paths


def test_chat_has_a_mic_and_reads_replies_aloud_through_voice_tts():
    src = (PAGE / "app.js").read_text()
    assert "webkitSpeechRecognition" in src and "ph-microphone" in src
    assert "/api/voice/tts" in src and "chat-read-aloud" in src
    for f in PAGE.glob("*.*"):
        assert "·" not in f.read_text() and "—" not in f.read_text(), f.name
