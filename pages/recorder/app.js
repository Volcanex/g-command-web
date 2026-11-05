// Recorder: Gabriel's cursor takes for the G-Studio landing page. The landing runs in
// record mode in an iframe and streams pointer and keys here over postMessage (the
// gs-cursor-take/1 contract: hello, ready, anchors, start, events, stop, stopped, play,
// played, halt). A take is replayed with an overlay cursor over the iframe or by the
// landing itself, then kept in g-content as a cursor-take piece through /api/recorder
// (api.py, which holds the token) or thrown away. Kept takes are rated in Showcase.
import {
  html, useState, useEffect, useRef, useCallback, PageHead, Badge, Button, Empty, ErrorState,
  Field, Confirm, SkeletonRows, toastOk, toast, mount, cursorSvgs, cursorRgb, ownCursorColor,
} from "../../core/app/boot.js";
import "./app.css";

const API = "/api/recorder";
const px = (u) => (typeof u === "string" && u.startsWith("/api/") ? API + u.slice(4) : u);
const LANDING = "https://studio.gabrielpenman.com/?record=1";
const KINDS = [["gabriel", "Gabriel"], ["you", "You"], ["agent", "Agent"]];
const KIND_LABEL = Object.fromEntries(KINDS);
const HELLO_EVERY_MS = 1000;
const HELLO_FOR_MS = 10000;
const STOP_WAIT_MS = 2000;

/* Loopback page and loopback override only, so a dev run can frame a mock landing.
   Production always frames the real one. */
const LOOP = (h) => h === "127.0.0.1" || h === "localhost" || h === "[::1]";
function landingSrc() {
  const o = new URLSearchParams(location.search).get("landing");
  if (!o || !LOOP(location.hostname)) return LANDING;
  try { const u = new URL(o); return LOOP(u.hostname) && /^https?:$/.test(u.protocol) ? u.href : LANDING; } catch { return LANDING; }
}
const SRC = landingSrc();
const ORIGIN = new URL(SRC).origin;
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

/* Same error reading as Showcase: {code, message}, g-content's {error: {...}} included. */
async function call(url, opts) {
  let r;
  try {
    r = await fetch(url, { credentials: "same-origin", ...opts });
  } catch {
    throw { code: "offline", message: "Command is not answering." };
  }
  let body = null;
  try { body = await r.json(); } catch { /* handled below */ }
  if (body && body.error && typeof body.error === "object") throw body.error;
  if (!r.ok || (body && typeof body.error === "string")) {
    const msg = (body && (typeof body.error === "string" ? body.error : body.detail)) || `Command answered ${r.status}.`;
    throw { code: r.status === 404 ? "not_found" : "http", message: typeof msg === "string" ? msg : JSON.stringify(msg) };
  }
  return body;
}

const fmtMs = (ms) => {
  const s = Math.max(0, ms || 0) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};
const BANNED = /[—–·;]/;
function nameError(n) {
  const v = n.trim();
  if (!v) return "Give the take a name to keep it.";
  if (v.length > 80) return "Keep the name to 80 characters.";
  if (BANNED.test(v)) return "Names can't have an em dash, a middle dot or a semicolon.";
  return "";
}

/* ------------------------------------------------------------- the landing link */

/* Owns the iframe conversation: hello until ready, the latest layout, and the
   events of the current recording. `on` gets every message for this session. */
function useLanding(frame) {
  const [conn, setConn] = useState("connecting");
  const session = useRef(uuid());
  const layout = useRef(null);
  const handlers = useRef({});
  const timer = useRef(null);

  const post = useCallback((msg) => {
    const w = frame.current && frame.current.contentWindow;
    if (w) w.postMessage({ gsr: 1, session: session.current, ...msg }, ORIGIN);
  }, []);

  const hello = useCallback(() => {
    clearInterval(timer.current);
    session.current = uuid();
    setConn("connecting");
    const t0 = Date.now();
    post({ type: "hello" });
    timer.current = setInterval(() => {
      if (Date.now() - t0 >= HELLO_FOR_MS) { clearInterval(timer.current); setConn((c) => (c === "ready" ? c : "silent")); return; }
      post({ type: "hello" });
    }, HELLO_EVERY_MS);
  }, [post]);

  useEffect(() => {
    const on = (e) => {
      if (e.origin !== ORIGIN || !frame.current || e.source !== frame.current.contentWindow) return;
      const d = e.data;
      if (!d || d.gsr !== 1 || d.session !== session.current) return;
      if (d.type === "ready" || d.type === "anchors") {
        layout.current = { rev: d.rev ?? (layout.current && layout.current.rev), viewport: d.viewport, scroll: d.scroll, anchors: d.anchors || [] };
      }
      if (d.type === "ready") { clearInterval(timer.current); setConn("ready"); }
      const h = handlers.current[d.type];
      if (h) h(d);
    };
    addEventListener("message", on);
    return () => { removeEventListener("message", on); clearInterval(timer.current); };
  }, []);

  return { conn, post, hello, layout, handlers };
}

/* ------------------------------------------------------------- replay overlay */

/* Anchor fractions to overlay px in the iframe's current layout. "page" is the
   viewport itself. An anchor missing from the layout drops its events. */
function placer(layout) {
  const rects = {};
  for (const a of (layout && layout.anchors) || []) rects[a.id] = a.rect;
  const sy = (layout && layout.scroll && layout.scroll.y) || 0;
  const vp = (layout && layout.viewport) || { w: 0, h: 0 };
  return (ev) => {
    if (typeof ev.x !== "number" || typeof ev.y !== "number") return null;
    if (ev.a === "page" || ev.a == null) return [ev.x * vp.w, ev.y * vp.h];
    const r = rects[ev.a];
    return r ? [r.x + ev.x * r.w, r.y - sy + ev.y * r.h] : null;
  };
}

function useReplay(layoutRef) {
  const [view, setView] = useState(null); // {x, y, down, p}
  const [playing, setPlaying] = useState(false);
  const raf = useRef(0);
  const stop = useCallback(() => { cancelAnimationFrame(raf.current); setPlaying(false); setView(null); }, []);
  const play = useCallback((take) => {
    cancelAnimationFrame(raf.current);
    const at = placer(layoutRef.current);
    const pts = [];
    let down = false;
    for (const ev of take.events || []) {
      if (ev.k === "down") down = true;
      if (ev.k === "up") down = false;
      const p = at(ev);
      if (p) pts.push({ t: ev.t, x: p[0], y: p[1], down });
    }
    if (!pts.length) { toast({ title: "Nothing to replay", desc: "No event in this take lands on the page as it is laid out now.", kind: "error" }); return; }
    const dur = Math.max(take.duration_ms || 0, pts[pts.length - 1].t);
    const start = performance.now() - pts[0].t;
    let i = 0;
    setPlaying(true);
    const frame = (now) => {
      const t = now - start;
      while (i < pts.length - 1 && pts[i + 1].t <= t) i++;
      const a = pts[i], b = pts[Math.min(i + 1, pts.length - 1)];
      const f = b.t > a.t ? Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t))) : 0;
      setView({ x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, down: a.down, p: dur ? Math.min(1, t / dur) : 1 });
      if (t < dur) raf.current = requestAnimationFrame(frame);
      else { setPlaying(false); setView((v) => v && { ...v, down: false, p: 1 }); }
    };
    raf.current = requestAnimationFrame(frame);
  }, []);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  return { view, playing, play, stop };
}

function Overlay({ view }) {
  const [arrow] = useState(() => {
    const [svg, hx, hy] = cursorSvgs(cursorRgb(ownCursorColor()) || "rgb(229,72,77)").arrow;
    return { src: `data:image/svg+xml,${encodeURIComponent(svg)}`, hx, hy };
  });
  if (!view) return html`<div class="rc-overlay" aria-hidden="true"></div>`;
  return html`<div class="rc-overlay" aria-hidden="true">
    <div class="rc-tip" style=${{ transform: `translate(${view.x}px, ${view.y}px)` }}>
      ${view.down && html`<span class="rc-press"></span>`}
      <img class="rc-arrow" src=${arrow.src} alt="" style=${{ left: `${-arrow.hx}px`, top: `${-arrow.hy}px` }} />
    </div>
  </div>`;
}

/* ------------------------------------------------------------- the stage */

/* The iframe at its own CSS size (no scaling, so pointer coordinates match),
   16:10 within the width, never taller than the window allows. */
function useStageSize(box) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const fit = () => {
      const el = box.current;
      if (!el) return;
      const w = Math.floor(el.clientWidth);
      const room = Math.max(240, innerHeight - el.getBoundingClientRect().top - 120);
      const h = Math.floor(Math.min(w * 10 / 16, room));
      setSize((s) => (s.w === w && s.h === h ? s : { w, h }));
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(box.current);
    addEventListener("resize", fit);
    return () => { ro.disconnect(); removeEventListener("resize", fit); };
  }, []);
  return size;
}

function StageNote({ conn, retry }) {
  if (conn === "ready") return null;
  return html`<div class=${`rc-note ${conn === "silent" ? "rc-cover" : ""}`} role="status">
    ${conn === "connecting"
      ? html`<span class="muted">Waiting for the landing page to answer</span>`
      : html`<span>The landing page's record mode is not answering yet. It may not be live, or it may not allow this page to frame it.</span>
          <${Button} size="sm" onClick=${retry}>Retry<//>`}
  </div>`;
}

/* ------------------------------------------------------------- saved takes */

function TakeCard({ t, busy, onReplay, onPlay, onDelete, canPlay }) {
  const [broken, setBroken] = useState(false);
  const take = t.take || {};
  return html`<div class="card rc-take">
    <div class="rc-poster">
      ${t.poster_url && !broken
        ? html`<img src=${px(t.poster_url)} alt="" loading="lazy" decoding="async" onError=${() => setBroken(true)} />`
        : html`<i class="ph ph-cursor" aria-hidden="true"></i>`}
    </div>
    <div class="rc-take-body">
      <div class="rc-take-title">${t.name || take.name || t.id}</div>
      <div class="rc-take-meta">
        <${Badge} kind="plain">${KIND_LABEL[t.kind || take.kind] || t.kind}<//>
        <span class="num">${fmtMs(take.duration_ms)}</span>
        <span>Your score ${t.owner_score == null ? html`<span class="muted">not yet</span>` : html`<span class="num">${t.owner_score}</span>`}</span>
      </div>
      <div class="rc-take-actions">
        <${Button} size="sm" busy=${busy === "replay"} onClick=${onReplay}><i class="ph ph-play" aria-hidden="true"></i>Replay<//>
        <${Button} size="sm" disabled=${!canPlay} busy=${busy === "play"} onClick=${onPlay}><i class="ph ph-browser" aria-hidden="true"></i>Play in page<//>
        <a class="btn btn-tertiary btn-sm" href=${`/showcase?piece=${encodeURIComponent(t.id)}`}><span>Rate in Showcase</span></a>
        <${Button} size="sm" kind="tertiary" onClick=${onDelete}><i class="ph ph-trash" aria-hidden="true"></i>Delete<//>
      </div>
    </div>
  </div>`;
}

/* ------------------------------------------------------------- page */

function Recorder() {
  const frame = useRef(null);
  const box = useRef(null);
  const size = useStageSize(box);
  const link = useLanding(frame);
  const replay = useReplay(link.layout);

  const [rec, setRec] = useState("idle"); // idle | recording | stopping | stopped
  const [take, setTake] = useState(null); // the unkept take
  const [count, setCount] = useState(0);
  const [clock, setClock] = useState(0);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("gabriel");
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);
  const [kept, setKept] = useState(null); // the last kept piece, for the saved line
  const [inPage, setInPage] = useState(false);
  const [list, setList] = useState({ data: undefined, error: null });
  const [busy, setBusy] = useState({});
  const [doomed, setDoomed] = useState(null);
  const events = useRef([]);
  const t0 = useRef(0);
  const stopTimer = useRef(0);

  const loadList = useCallback(() => {
    setList((s) => ({ ...s, error: null }));
    call(`${API}/takes`).then((d) => setList({ data: d.takes || [], error: null }), (error) => setList({ data: undefined, error }));
  }, []);
  useEffect(loadList, []);

  // A stopped take is finished here: duration from "stopped", else the last event.
  const finish = useCallback((duration) => {
    clearTimeout(stopTimer.current);
    setTake((tk) => tk && { ...tk, duration_ms: duration ?? (events.current.length ? events.current[events.current.length - 1].t : 0), events: events.current });
    setRec("stopped");
  }, []);

  link.handlers.current = {
    events: (d) => {
      if (rec !== "recording" && rec !== "stopping") return;
      if (Array.isArray(d.batch)) { for (const ev of d.batch) events.current.push(ev); setCount(events.current.length); }
    },
    stopped: (d) => { if (rec === "stopping" || rec === "recording") finish(typeof d.duration_ms === "number" ? d.duration_ms : null); },
    played: (d) => {
      setInPage(false);
      if (d.error) toast({ title: "The landing can't play takes yet", desc: "Replay shows it here.", kind: "error" });
    },
  };

  useEffect(() => {
    if (rec !== "recording") return;
    let id = 0;
    const tick = () => { setClock(performance.now() - t0.current); id = requestAnimationFrame(tick); };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [rec]);

  useEffect(() => {
    if (!take || rec === "idle") return;
    const warn = (e) => { e.preventDefault(); e.returnValue = ""; };
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [take, rec]);

  const record = () => {
    if (link.conn !== "ready") return;
    replay.stop();
    const l = link.layout.current || {};
    events.current = [];
    setCount(0);
    setClock(0);
    setKept(null);
    setSaveErr(null);
    setTake({
      schema: "gs-cursor-take/1", name: "", kind, recorded_at: new Date().toISOString(),
      rev: String(l.rev || "").slice(0, 64), viewport: l.viewport, duration_ms: 0, events: [],
      anchors: l.anchors, scroll: l.scroll, page: SRC,
    });
    t0.current = performance.now();
    link.post({ type: "start" });
    setRec("recording");
    frame.current && frame.current.focus();
  };
  const stop = () => {
    setRec("stopping");
    link.post({ type: "stop" });
    stopTimer.current = setTimeout(() => finish(null), STOP_WAIT_MS);
  };
  const discard = () => { replay.stop(); setTake(null); setRec("idle"); setName(""); setTouched(false); setSaveErr(null); };

  // R toggles recording when focus is on this page, never while typing.
  useEffect(() => {
    const on = (e) => {
      if (e.key !== "r" && e.key !== "R") return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      if (rec === "recording") stop(); else if (rec !== "stopping" && link.conn === "ready") record();
    };
    addEventListener("keydown", on);
    return () => removeEventListener("keydown", on);
  });

  const keep = async () => {
    setTouched(true);
    if (nameError(name)) return;
    setSaving(true);
    setSaveErr(null);
    try {
      const piece = await call(`${API}/takes`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...take, name: name.trim(), kind }) });
      replay.stop();
      setKept({ id: piece && piece.id, name: name.trim() });
      setTake(null);
      setRec("idle");
      setName("");
      setTouched(false);
      toastOk("Kept", "It is in g-content now, ready to rate in Showcase.");
      loadList();
    } catch (e) {
      setSaveErr(e);
    } finally {
      setSaving(false);
    }
  };

  const full = async (id) => (await call(`${API}/takes/${id}`)).take;
  const mark = (id, v) => setBusy((b) => ({ ...b, [id]: v }));
  const replaySaved = async (t) => {
    mark(t.id, "replay");
    try { replay.play(await full(t.id)); }
    catch (e) { toast({ title: "The take did not load", desc: e.message || String(e), kind: "error" }); }
    finally { mark(t.id, null); }
  };
  const playIn = (tk) => { link.post({ type: "play", take: tk }); setInPage(true); };
  const playSaved = async (t) => {
    mark(t.id, "play");
    try { playIn(await full(t.id)); }
    catch (e) { toast({ title: "The take did not load", desc: e.message || String(e), kind: "error" }); }
    finally { mark(t.id, null); }
  };
  const halt = () => { link.post({ type: "halt" }); setInPage(false); };
  const remove = async () => {
    await call(`${API}/takes/${doomed.id}`, { method: "DELETE" });
    toastOk("Deleted", doomed.name);
    setList((s) => ({ ...s, data: (s.data || []).filter((x) => x.id !== doomed.id) }));
  };

  const ready = link.conn === "ready";
  const recording = rec === "recording" || rec === "stopping";
  const err = touched ? nameError(name) : "";
  const shown = rec === "stopped" ? take : null;

  return html`<div class="rc-page">
    <${PageHead} title="Recorder" sub="Move and click in the landing page to record a take. Replay it, then keep it or bin it.">
      ${recording
        ? html`<${Button} kind="danger" busy=${rec === "stopping"} onClick=${stop}><i class="ph ph-stop" aria-hidden="true"></i>Stop<//>`
        : html`<${Button} kind="primary" disabled=${!ready || saving} onClick=${record} title="R"><i class="ph ph-record" aria-hidden="true"></i>Record<//>`}
    <//>

    <div class="rc-stage-box" ref=${box}>
      <div class="rc-stage" style=${{ width: `${size.w}px`, height: `${size.h}px` }}>
        <iframe ref=${frame} src=${SRC} title="G-Studio landing page in record mode" width=${size.w} height=${size.h}
          onLoad=${link.hello} allow="clipboard-read"></iframe>
        <${Overlay} view=${replay.view} />
        <${StageNote} conn=${link.conn} retry=${() => { frame.current.src = SRC; }} />
      </div>
      <div class="rc-progress" style=${{ width: `${size.w}px` }} aria-hidden="true">
        <span style=${{ transform: `scaleX(${recording ? 0 : replay.view ? replay.view.p : 0})` }}></span>
      </div>
      <div class="rc-status" style=${{ maxWidth: `${size.w}px` }}>
        ${recording
          ? html`<span class="rc-live"><span class="rc-dot" aria-hidden="true"></span>Recording</span>
              <span class="num">${fmtMs(clock)}</span><span class="num">${count} events</span>`
          : html`<span class="muted">${link.conn === "ready" ? (rec === "stopped" ? "Stopped. Name it, then keep it or bin it." : "Ready. Press Record or R.") : link.conn === "connecting" ? "Connecting" : "Not answering"}</span>
              ${inPage && html`<${Button} size="sm" onClick=${halt}><i class="ph ph-hand" aria-hidden="true"></i>Halt<//>`}`}
      </div>
    </div>

    ${shown && html`<section class="card rc-take-form" aria-label="This take">
      <div class="rc-form-meta"><span class="num">${fmtMs(shown.duration_ms)}</span><span class="num">${shown.events.length} events</span></div>
      <${Field} id="rc-name" label="Name" error=${err} count=${name.trim().length} max=${80}>
        <input id="rc-name" class="input" value=${name} maxlength="120" placeholder="drag the G"
          onInput=${(e) => setName(e.currentTarget.value)} onBlur=${() => setTouched(true)} />
      <//>
      <div class="field">
        <div class="field-top"><span class="label" id="rc-kind">Kind</span></div>
        <div class="g-segmented" role="radiogroup" aria-labelledby="rc-kind">
          ${KINDS.map(([k, label]) => html`<label key=${k}><input type="radio" name="rc-kind" checked=${kind === k} onChange=${() => setKind(k)} />${label}</label>`)}
        </div>
      </div>
      ${saveErr && html`<div class="rc-save-err"><${ErrorState} error=${saveErr} title="The take was not kept" retry=${keep} /></div>`}
      <div class="rc-form-actions">
        <${Button} kind="primary" busy=${saving} onClick=${keep}><i class="ph ph-check" aria-hidden="true"></i>Keep<//>
        <${Button} disabled=${saving} onClick=${() => (replay.playing ? replay.stop() : replay.play(shown))}><i class="ph ph-play" aria-hidden="true"></i>${replay.playing ? "Stop replay" : "Replay"}<//>
        ${inPage ? html`<${Button} onClick=${halt}><i class="ph ph-hand" aria-hidden="true"></i>Halt<//>`
          : html`<${Button} disabled=${!ready || saving} onClick=${() => playIn(shown)}><i class="ph ph-browser" aria-hidden="true"></i>Play in page<//>`}
        <${Button} kind="tertiary" disabled=${saving} onClick=${discard}><i class="ph ph-trash" aria-hidden="true"></i>Delete<//>
      </div>
    </section>`}

    ${kept && !shown && html`<p class="rc-kept" role="status">Kept ${kept.name}.${kept.id && html` <a href=${`/showcase?piece=${encodeURIComponent(kept.id)}`}>Rate it in Showcase</a>`}</p>`}

    <section class="rc-saved">
      <h2>Kept takes</h2>
      ${list.error ? html`<div class="card rc-trouble"><${ErrorState} error=${list.error} retry=${loadList}
          title=${{ unreachable: "Can't reach g-content", no_token: "g-content is not set up here", rejected: "g-content refused Command" }[list.error.code]} /></div>`
        : list.data === undefined ? html`<${SkeletonRows} rows=${3} height=${72} />`
        : list.data.length === 0 ? html`<div class="card"><${Empty} icon="cursor" title="No takes kept yet" desc="Record one above and keep it. It shows here and in Showcase." /></div>`
        : html`<div class="rc-takes">${list.data.map((t) => html`<${TakeCard} key=${t.id} t=${t} busy=${busy[t.id]} canPlay=${ready}
            onReplay=${() => replaySaved(t)} onPlay=${() => playSaved(t)} onDelete=${() => setDoomed(t)} />`)}</div>`}
    </section>

    <${Confirm} open=${!!doomed} onClose=${() => setDoomed(null)} onConfirm=${remove} danger confirmLabel="Delete take"
      title="Delete this take?" desc=${doomed ? `${doomed.name} leaves the library. Its history stays in g-content's git.` : ""} />
  </div>`;
}

mount(Recorder);
