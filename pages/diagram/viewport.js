// Viewport: zoom and pan for either view, and fullscreen for the card that holds it.
// Wheel or pinch zooms about the pointer, a drag pans (a click that did not move still
// reaches the node under it), and the bar carries zoom in, zoom out, reset and fit. The
// content keeps its natural size; only a CSS transform moves it, so nothing re-lays out.
// Fullscreen uses the Fullscreen API on the card and falls back to a fixed overlay where
// the API is missing (iPhone Safari); Esc leaves either.
import { html, useState, useEffect, useRef } from "../../core/app/boot.js";
import { useLayoutEffect } from "preact/hooks";

const MIN = 0.1, MAX = 3, STEP = 1.25, DRAG_PX = 4, READABLE = 0.6;
const clamp = (k) => Math.min(MAX, Math.max(MIN, k));

function IconBtn({ icon, label, onClick, pressed }) {
  return html`<button type="button" class="btn btn-tertiary btn-sm btn-icon" aria-label=${label} data-tip=${label}
    aria-pressed=${pressed} onClick=${onClick}><i class=${`ph ph-${icon}`} aria-hidden="true"></i></button>`;
}

/* tools: what the bar shows left of the zoom buttons (the view switch). fitKey: refit when it
   changes (new content). reveal: {id, n}, centre the element with data-node=id. fill: content
   takes the viewport's width (Levels, which wraps), else its own (System). */
export function Viewport({ tools, fitKey, reveal, fill, label, children }) {
  const card = useRef(null), port = useRef(null), inner = useRef(null);
  const [t, setT] = useState({ k: 1, x: 0, y: 0 });
  const [fs, setFs] = useState(false);      // fullscreen, by the API or the overlay
  const [overlay, setOverlay] = useState(false);
  const tRef = useRef(t);
  tRef.current = t;

  const size = () => {
    const el = inner.current && inner.current.firstElementChild;
    return el ? { w: el.scrollWidth || el.getBoundingClientRect().width / tRef.current.k, h: el.scrollHeight || el.getBoundingClientRect().height / tRef.current.k } : { w: 1, h: 1 };
  };
  const view = () => { const r = port.current.getBoundingClientRect(); return { w: r.width, h: r.height, r }; };
  const fit = () => {
    if (!port.current) return;
    const v = view(), c = size();
    const k = clamp(Math.min(1, v.w / c.w, v.h / c.h));
    setT({ k, x: Math.max(0, (v.w - c.w * k) / 2), y: Math.max(0, (v.h - c.h * k) / 2) });
  };
  const zoomAt = (factor, px, py) => setT((o) => {
    const k = clamp(o.k * factor), f = k / o.k;
    return { k, x: px - (px - o.x) * f, y: py - (py - o.y) * f };
  });
  const zoomMid = (factor) => { const v = view(); zoomAt(factor, v.w / 2, v.h / 2); };
  const reset = () => setT({ k: 1, x: 0, y: 0 });

  // System starts fitted when it is wider than the card; Levels starts at its natural size.
  useLayoutEffect(() => {
    if (!port.current) return;
    const v = view(), c = size();
    // Too big for the card: fit it, unless that makes it unreadable, then start readable at the top left.
    if (fill || (c.w <= v.w && c.h <= v.h)) return reset();
    const k = Math.min(v.w / c.w, v.h / c.h);
    if (k >= READABLE) fit(); else setT({ k: READABLE, x: 0, y: 0 });
  }, [fitKey]);

  // Bring a node into the middle and mark it, after a jump from the other view.
  useEffect(() => {
    if (!reveal || !reveal.id || !port.current) return;
    const timer = setTimeout(() => {
      const el = inner.current.querySelector(`[data-node="${CSS.escape(reveal.id)}"]`);
      if (!el) return;
      const v = view(), r = el.getBoundingClientRect(), o = tRef.current;
      const k = Math.max(o.k, fill ? 1 : 0.8);
      const cx = (r.left - v.r.left - o.x) / o.k + r.width / o.k / 2, cy = (r.top - v.r.top - o.y) / o.k + r.height / o.k / 2;
      setT({ k, x: v.w / 2 - cx * k, y: v.h / 2 - cy * k });
      el.classList.add("is-revealed");
      setTimeout(() => el.classList.remove("is-revealed"), 2400);
    }, 120);
    return () => clearTimeout(timer);
  }, [reveal && reveal.n]);

  // Wheel and pointers. Wheel needs passive: false to stop the page scrolling under it.
  useEffect(() => {
    const el = port.current;
    if (!el) return;
    const local = (ev) => { const r = el.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
    const wheel = (ev) => {
      ev.preventDefault();
      const [px, py] = local(ev);
      if (ev.ctrlKey || !ev.shiftKey) zoomAt(Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015)), px, py);
      else setT((o) => ({ ...o, x: o.x - ev.deltaY }));
    };
    const pts = new Map();
    let start = null, moved = false, pinch = null;
    const down = (ev) => {
      if (ev.button !== 0 && ev.pointerType === "mouse") return;
      pts.set(ev.pointerId, local(ev));
      if (pts.size === 1) { start = { p: local(ev), t: tRef.current }; moved = false; }
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], t: tRef.current };
        moved = true;
      }
    };
    const move = (ev) => {
      if (!pts.has(ev.pointerId)) return;
      pts.set(ev.pointerId, local(ev));
      if (pinch && pts.size >= 2) {
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]), o = pinch.t;
        const k = clamp(o.k * d / pinch.d), f = k / o.k;
        const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        setT({ k, x: mid[0] - (pinch.mid[0] - o.x) * f, y: mid[1] - (pinch.mid[1] - o.y) * f });
        return;
      }
      if (!start) return;
      const [x, y] = local(ev), dx = x - start.p[0], dy = y - start.p[1];
      if (!moved && Math.hypot(dx, dy) < DRAG_PX) return;
      if (!moved) { moved = true; el.setPointerCapture(ev.pointerId); el.classList.add("is-panning"); }
      setT({ ...start.t, x: start.t.x + dx, y: start.t.y + dy });
    };
    const up = (ev) => {
      pts.delete(ev.pointerId);
      if (pts.size < 2) pinch = null;
      if (!pts.size) { start = null; el.classList.remove("is-panning"); }
    };
    // A drag ends in a click on whatever is under it; swallow that one.
    const click = (ev) => { if (moved) { ev.stopPropagation(); ev.preventDefault(); moved = false; } };
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("click", click, true);
    return () => {
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      el.removeEventListener("click", click, true);
    };
  }, []);

  // Fullscreen: the API where it exists, the overlay where it does not. Esc leaves both.
  useEffect(() => {
    const change = () => setFs(document.fullscreenElement === card.current || overlay);
    const key = (ev) => ev.key === "Escape" && overlay && setOverlay(false);
    document.addEventListener("fullscreenchange", change);
    document.addEventListener("keydown", key);
    change();
    return () => { document.removeEventListener("fullscreenchange", change); document.removeEventListener("keydown", key); };
  }, [overlay]);
  useEffect(() => { document.documentElement.classList.toggle("dg-overlay-open", overlay); }, [overlay]);
  // Entering or leaving fullscreen changes the room, so refit then (not on first render).
  const fsSeen = useRef(false);
  useEffect(() => {
    if (!fsSeen.current) { fsSeen.current = true; return; }
    const id = setTimeout(fit, 60);
    return () => clearTimeout(id);
  }, [fs]);
  const toggleFs = () => {
    if (document.fullscreenElement) return document.exitFullscreen();
    if (overlay) return setOverlay(false);
    const el = card.current;
    if (el.requestFullscreen && document.fullscreenEnabled) el.requestFullscreen().catch(() => setOverlay(true));
    else setOverlay(true);
  };

  return html`<div class=${`card dg-canvas ${fs ? "is-full" : ""} ${overlay ? "is-overlay" : ""}`} ref=${card}>
    <div class="dg-bar">
      ${tools}
      <span class="dg-bar-zoom">
        <${IconBtn} icon="magnifying-glass-minus" label="Zoom out" onClick=${() => zoomMid(1 / STEP)} />
        <span class="num small muted dg-zoom-pct">${Math.round(t.k * 100)}%</span>
        <${IconBtn} icon="magnifying-glass-plus" label="Zoom in" onClick=${() => zoomMid(STEP)} />
        <${IconBtn} icon="arrow-counter-clockwise" label="Reset zoom" onClick=${reset} />
        <button type="button" class="btn btn-tertiary btn-sm" onClick=${fit}>Fit whole diagram</button>
        <${IconBtn} icon=${fs ? "corners-in" : "corners-out"} label=${fs ? "Leave fullscreen" : "Fullscreen"} onClick=${toggleFs} pressed=${fs} />
      </span>
    </div>
    <div class="dg-port" ref=${port} role="group" aria-label=${label}>
      <div class=${`dg-inner ${fill ? "is-fill" : ""}`} ref=${inner}
        style=${{ transform: `translate(${t.x}px, ${t.y}px) scale(${t.k})` }}>${children}</div>
    </div>
  </div>`;
}
