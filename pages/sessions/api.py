"""Terminal sessions API: list tmux sessions, create them, and bridge a PTY
over WebSocket so the browser can attach.

Mounted at /api/sessions. Admin-gated inline (server.py's page gate does not
cover /api/* routers). The hosts come from `SESSION_HOSTS` (see `_hosts`): the
first is this machine's own tmux, the rest are reached over SSH, which needs
passwordless SSH from here for the user the server runs as.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import re
import shlex
import signal
import struct
import subprocess
import termios

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.auth import cookie_ok

router = APIRouter()

# tmux session names: letters, digits, dash, underscore, dot. Kept tight so a
# name can never reach a shell as anything ambiguous.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")

_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=4"]


def _safe_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


def _hosts(spec: str) -> dict[str, str | None]:
    """Host name -> ssh destination, from `SESSION_HOSTS`, e.g. `h,b=b.example.com`.

    The first name is local tmux (None). Each later one is reached over ssh at
    the destination after `=`, or at its own name when there is none. Names go
    into URLs, so they follow the session-name rule. Unset, the only host is
    the local one, called `local`."""
    hosts: dict[str, str | None] = {}
    for item in spec.split(","):
        name, _, dest = (part.strip() for part in item.partition("="))
        if _safe_name(name) and name not in hosts:
            hosts[name] = (dest or name) if hosts else None
    return hosts or {"local": None}


_HOSTS = _hosts(os.environ.get("SESSION_HOSTS", ""))


def _tmux_cmd(host: str, args: list[str]) -> list[str]:
    """argv to run `tmux <args>` on `host`: local, or over ssh for remotes.

    Remote args are shell-quoted into a single string so format strings (with
    `#{...}` and embedded tabs) survive the remote shell's word-splitting."""
    alias = _HOSTS.get(host)
    if alias is None:
        return ["tmux", *args]
    remote = " ".join(shlex.quote(a) for a in ["tmux", *args])
    return ["ssh", *_SSH_OPTS, alias, remote]


def _tmux_attach_cmd(host: str, name: str) -> list[str]:
    """argv for the interactive attach (run inside the forked PTY). Remote needs
    `-tt` to force a remote PTY; `-q` keeps ssh's connect/close chatter out of
    the terminal."""
    inner = ["tmux", "new-session", "-A", "-s", name]
    alias = _HOSTS.get(host)
    if alias is None:
        return inner
    remote = " ".join(shlex.quote(a) for a in inner)
    return ["ssh", "-q", "-tt", *_SSH_OPTS, alias, remote]


def _is_admin(request_or_ws) -> bool:
    return cookie_ok(request_or_ws.cookies)


def _tmux_ls(host: str):
    try:
        out = subprocess.run(
            _tmux_cmd(host, [
                "ls", "-F",
                "#{session_name}\t#{session_attached}\t#{session_windows}\t"
                "#{session_activity}\t#{session_created}",
            ]),
            capture_output=True, text=True, timeout=8,
        )
    except Exception:
        return []
    if out.returncode != 0:
        return []
    sessions = []
    for line in out.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        # tmux >= 3.2 reports activity/created in milliseconds; older versions
        # used seconds. Anything past ~2001 is unambiguously ms: normalise to s.
        def _ts(s):
            n = int(s or 0)
            return n // 1000 if n > 10_000_000_000 else n
        sessions.append({
            "name": parts[0],
            "attached": int(parts[1] or 0) > 0,
            "windows": int(parts[2] or 0),
            "last_activity": _ts(parts[3]),
            "created": _ts(parts[4]),
        })
    return sessions


@router.get("")
def list_sessions(request: Request):
    if not _is_admin(request):
        raise HTTPException(401, "unauthorized")
    return {"hosts": {h: _tmux_ls(h) for h in _HOSTS}}


class SessionRef(BaseModel):
    host: str
    name: str


@router.post("/new")
def new_session(req: SessionRef, request: Request):
    if not _is_admin(request):
        raise HTTPException(401, "unauthorized")
    if req.host not in _HOSTS:
        raise HTTPException(400, "unknown host")
    if not _safe_name(req.name):
        raise HTTPException(400, "invalid session name")
    out = subprocess.run(
        _tmux_cmd(req.host, ["new-session", "-d", "-s", req.name]),
        capture_output=True, text=True, timeout=8,
    )
    if out.returncode != 0 and "duplicate session" not in (out.stderr or ""):
        raise HTTPException(500, (out.stderr or "tmux failed").strip())
    return {"ok": True, "name": req.name}


@router.post("/kill")
def kill_session(req: SessionRef, request: Request):
    if not _is_admin(request):
        raise HTTPException(401, "unauthorized")
    if req.host not in _HOSTS:
        raise HTTPException(400, "unknown host")
    if not _safe_name(req.name):
        raise HTTPException(400, "invalid session name")
    out = subprocess.run(
        _tmux_cmd(req.host, ["kill-session", "-t", req.name]),
        capture_output=True, text=True, timeout=8,
    )
    if out.returncode != 0:
        raise HTTPException(500, (out.stderr or "tmux failed").strip())
    return {"ok": True}


@router.post("/purge")
def purge_stale(request: Request, idle_days: int = 7):
    """Kill every unattached session created more than `idle_days` days ago.

    Uses creation time rather than last_activity because tmux's activity ticks
    on any background output (status bar, clocks) so an "idle" session can look
    fresh forever. Creation time is the honest orphan signal once filtered to
    the unattached set."""
    if not _is_admin(request):
        raise HTTPException(401, "unauthorized")
    import time
    cutoff = time.time() - max(1, idle_days) * 86400
    killed = []
    for host in _HOSTS:
        for s in _tmux_ls(host):
            if s["attached"] or s["created"] >= cutoff:
                continue
            out = subprocess.run(
                _tmux_cmd(host, ["kill-session", "-t", s["name"]]),
                capture_output=True, text=True, timeout=8,
            )
            if out.returncode == 0:
                killed.append(f"{host}:{s['name']}")
    return {"killed": killed, "count": len(killed)}


@router.get("/history/{host}/{name}")
def history(host: str, name: str, request: Request, lines: int = 2000):
    """The pane's scrollback plus its visible screen, with colours, for a
    native client to scroll through. Attached tmux draws on the alternate
    screen, so the attach stream never carries history. Wrapped lines are
    joined (-J) so the client rewraps them at its own width. A session that
    does not exist yet has no history: an empty text, not an error."""
    if not _is_admin(request):
        raise HTTPException(401, "unauthorized")
    if host not in _HOSTS or not _safe_name(name):
        raise HTTPException(400, "invalid session")
    lines = max(0, min(lines, 10000))
    try:
        out = subprocess.run(
            _tmux_cmd(host, ["capture-pane", "-p", "-e", "-J", "-S", f"-{lines}", "-t", f"={name}:"]),
            capture_output=True, text=True, timeout=8, errors="replace",
        )
    except Exception:
        return {"text": ""}
    return {"text": out.stdout if out.returncode == 0 else ""}


@router.websocket("/ws/{host}/{name}")
async def attach(ws: WebSocket, host: str, name: str):
    # Cookie auth: Starlette parses cookies on the upgrade request.
    if not _is_admin(ws):
        await ws.close(code=1008)
        return
    if host not in _HOSTS or not _safe_name(name):
        await ws.close(code=1003)
        return

    await ws.accept()

    # `new-session -A`: attach if it exists, create if not. Idempotent.
    # For remote hosts this is wrapped in `ssh -tt` (see _tmux_attach_cmd).
    cmd = _tmux_attach_cmd(host, name)

    pid, master_fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        try:
            os.execvp(cmd[0], cmd)
        except Exception:
            os._exit(127)

    os.set_blocking(master_fd, False)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    done = asyncio.Event()

    def _on_readable():
        try:
            data = os.read(master_fd, 65536)
        except OSError:
            queue.put_nowait(None)
            return
        if not data:
            queue.put_nowait(None)
        else:
            queue.put_nowait(data)

    loop.add_reader(master_fd, _on_readable)

    def _resize(cols, rows):
        try:
            fcntl.ioctl(
                master_fd, termios.TIOCSWINSZ,
                struct.pack("HHHH", int(rows), int(cols), 0, 0),
            )
        except Exception:
            pass

    async def pty_to_ws():
        while True:
            data = await queue.get()
            if data is None:
                done.set()
                return
            try:
                await ws.send_bytes(data)
            except Exception:
                done.set()
                return

    async def ws_to_pty():
        try:
            while not done.is_set():
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text")
                if text is not None:
                    try:
                        obj = json.loads(text)
                    except json.JSONDecodeError:
                        os.write(master_fd, text.encode())
                        continue
                    t = obj.get("type")
                    if t == "data":
                        os.write(master_fd, str(obj.get("data", "")).encode())
                    elif t == "resize":
                        _resize(obj.get("cols", 80), obj.get("rows", 24))
                else:
                    b = msg.get("bytes")
                    if b is not None:
                        os.write(master_fd, b)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            done.set()

    tasks = [asyncio.create_task(pty_to_ws()), asyncio.create_task(ws_to_pty())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # FIRST_COMPLETED leaves the loser pending. Unawaited, it survives until
        # the GC eventually collects it ("Task was destroyed but it is pending!")
        # holding the socket and the queue with it. Cancel it here instead.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.remove_reader(master_fd)
        try:
            os.kill(pid, signal.SIGHUP)
        except Exception:
            pass
        try:
            os.close(master_fd)
        except Exception:
            pass
        await _reap(pid)
        try:
            await ws.close()
        except Exception:
            pass


async def _reap(pid: int):
    """Wait out the forked attach child so it doesn't linger as a zombie.

    pty.fork() children are ours to reap (nothing else will) and one leaks per
    attach otherwise. SIGHUP has already been sent; poll briefly for it to land,
    then escalate. Polling with WNOHANG keeps the event loop free (a blocking
    waitpid in a thread would strand that thread if the child ignored SIGHUP)."""
    for delay in (0.0, 0.05, 0.1, 0.2, 0.4, 0.8):
        if delay:
            await asyncio.sleep(delay)
        try:
            if os.waitpid(pid, os.WNOHANG)[0] == pid:
                return
        except ChildProcessError:
            return
        except Exception:
            return
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    for delay in (0.05, 0.2, 0.5):
        await asyncio.sleep(delay)
        try:
            if os.waitpid(pid, os.WNOHANG)[0] == pid:
                return
        except Exception:
            return
