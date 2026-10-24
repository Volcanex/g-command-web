import asyncio
import json
import threading

import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pages.voice import api as voice_api


@pytest.fixture
def upstream():
    """A fake Voice /live on a random port: answers hello with ready, echoes
    binary audio back, and records everything it got."""
    got, started = [], threading.Event()
    state = {}

    async def handler(ws):
        async for frame in ws:
            got.append(frame)
            if isinstance(frame, bytes):
                await ws.send(frame)
            elif json.loads(frame).get("type") == "hello":
                await ws.send(json.dumps({"type": "ready", "engine": "fake", "rate": 24000}))
            elif json.loads(frame).get("type") == "bye":
                await ws.close(code=1000)

    def run():
        loop = asyncio.new_event_loop()
        state["loop"] = loop

        async def main():
            async with websockets.serve(handler, "127.0.0.1", 0) as srv:
                state["port"] = srv.sockets[0].getsockname()[1]
                state["stop"] = asyncio.Event()
                started.set()
                await state["stop"].wait()
        loop.run_until_complete(main())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    started.wait(5)
    yield f"ws://127.0.0.1:{state['port']}/live", got
    state["loop"].call_soon_threadsafe(state["stop"].set)
    t.join(5)


@pytest.fixture
def client(monkeypatch, upstream):
    monkeypatch.setattr("core.auth.ADMIN_COOKIE", "seed_admin")
    monkeypatch.setattr("core.auth.ADMIN_VALUE", "ok")
    monkeypatch.setattr(voice_api, "VOICE_LIVE_URL", upstream[0])
    app = FastAPI()
    app.include_router(voice_api.router, prefix="/api/voice")
    return TestClient(app)


def test_live_refuses_without_a_cookie(client, upstream):
    with client.websocket_connect("/api/voice/live") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4401
    assert upstream[1] == []


def test_live_relays_frames_both_ways(client, upstream):
    client.cookies.set("seed_admin", "ok")
    pcm = bytes(range(256)) * 8
    with client.websocket_connect("/api/voice/live") as ws:
        ws.send_text(json.dumps({"type": "hello", "client": "web", "session": "talk"}))
        assert json.loads(ws.receive_text()) == {"type": "ready", "engine": "fake", "rate": 24000}
        ws.send_bytes(pcm)
        assert ws.receive_bytes() == pcm
        ws.send_text(json.dumps({"type": "bye"}))
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 1000
    assert upstream[1][0] == json.dumps({"type": "hello", "client": "web", "session": "talk"})
    assert upstream[1][1] == pcm
