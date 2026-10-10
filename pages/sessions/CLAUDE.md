# sessions: the terminal page

Attaches a browser to a tmux session on any host in `SESSION_HOSTS`, e.g.
`h,b=b.example.com`: the first host is local tmux, the rest go over ssh to the
destination after `=` (or the name itself). Unset, there is one local host
called `local`. `api.py` bridges a PTY over a WebSocket; `content.html` is an
xterm.js client built for a phone or an iPad first and a desktop second. The
page's host picker is filled from `GET /api/sessions`, so it names no host.

## Why the page looks the way it does

- **The chrome is g-design, the terminal is not.** Bar, rail, badge and menu are
  `.btn` / `.select` / `.badge` / `.menu` from the vendored g-design pack, sized
  up through `--h-control` because this is a thumb interface. xterm's own
  colours and `#terminal`'s black background are deliberately left alone: the
  wrapper has to match `term.options.theme.background` literally or a seam shows
  around the grid.
- **Keys live in a right-hand rail, not a toolbar.** A horizontally-scrolling
  strip of buttons meant scrolling the chrome to reach a key while also
  scrolling the terminal: two scroll contexts fighting. The rail is always
  reachable by thumb. Rare and destructive actions (new/kill/purge/detach,
  claude, mic) are behind the `⋮` menu, a Popover API `.menu` positioned by
  g-ui.js off `popovertarget`. Choosing any `.menu-item` closes it, which is why
  the mic toggle also raises a toast: its own pressed state is out of sight the
  moment it changes.
- **Height comes from `--vvh`, set from `window.visualViewport`.** iOS does not
  shrink the layout viewport when the software keyboard opens, so `100dvh`
  leaves the prompt underneath the keyboard. The visual viewport is the only
  measure that moves. `body.sessions-page` is `position: fixed` so nothing
  behind it can scroll, and `--vvtop` is applied as `top`, never as a transform:
  a transformed body becomes the containing block for every fixed overlay, and
  the menu, toasts and tooltips would land offset by that much.
- **The shell chrome is `.g-top` / `.g-status` inside `.g-main`.** Both are
  hidden here and `.site-main` gives up its padding, scroll and max-width.
  Successive versions have hidden the wrong selectors (`.site-header` /
  `.site-footer`, then `.cz-top` / `.cz-status`, neither of which exists) and
  each time the bars stayed, stacked on a full-height main, and the page
  scrolled ~86px behind the terminal.
- **The jog is relative, not a scrollbar.** Attached to tmux with mouse on,
  output goes to the alternate screen: xterm's own scrollback is empty and
  `term.scrollLines()` does nothing. Scrolling is forwarded as SGR 1006 wheel
  events (64 up, 65 down) and the browser cannot know how long tmux's real
  history is, so the grip springs back to centre rather than lying about a
  position.
- **Canvas renderer, loaded defensively.** The DOM renderer stutters on a
  Retina panel. If the addon fails to load, xterm keeps the DOM renderer.
- **The rail has to survive a 340px column.** A phone in landscape leaves that
  much height; at full key sizes the stack overflowed and the bottom arrow went
  off-screen. `@media (max-height: 520px)` shrinks the keys and drops the jog's
  min-height so it absorbs the remainder.
- **`/remote-control` types, it does not send.** The button prefills
  `/remote-control <session> ` at the cursor so the rest of the message can be
  typed after it; only `claude!` appends a carriage return.

## Reconnect

Mobile sockets die constantly: carrier NAT rotates the source address, cells
hand over, iOS suspends backgrounded tabs. tmux survives all of it, so the
client reattaches on backoff (~1s, ×1.7, capped at 15s) and immediately on
`visibilitychange`, `online` and `focus`. `deliberate` suppresses it after an
explicit detach or kill. `new-session -A` server-side makes reattaching
idempotent, and tmux repaints the pane, so `term.reset()` on open is safe.

The connection pill (`#conn`) is the honest status, driven through
`g.status(el, {kind, label})`: `Live` (ok) / `Connecting`, `Reconnecting`,
`Dropped`, `Retry Ns`, `Error` (warn) / `Idle`, `Detached`, `Killed` (danger).

## Server-side gotchas

- **Reap the child.** `pty.fork()` children are ours and nothing else will wait
  on them: one zombie leaked per attach before `_reap()` existed. It polls
  `WNOHANG` on the event loop rather than blocking a thread, because a child
  that ignores SIGHUP would strand that thread.
- **Cancel both tasks.** `asyncio.wait(..., FIRST_COMPLETED)` leaves the loser
  pending; unawaited it survives to the GC as
  `Task was destroyed but it is pending!`.
- **uvicorn ws ping.** `server.py` sets `ws_ping_timeout=90`; the 20s default
  killed a backgrounded mobile tab before iOS resumed it.
- nginx already allows long-lived sockets (`proxy_read_timeout 86400s` on
  `/api/sessions/ws/` in the vhost). It is not the thing to suspect.
