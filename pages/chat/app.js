// Chat: the conversation with Voice, the brain's agent, in the browser. It is
// the apps' `app` session (g-command-apple Kit/Sources/GCommandCore/Chat.swift),
// so a conversation started on the Mac or iPhone carries on here and back.
// Contract: core/panels/CLAUDE.md, "Chat replies". Routes: pages/voice/api.py.
//   GET  /api/voice/history?session=app  the turns since the 4am London reset
//   POST /api/voice/chat/stream          NDJSON delta, tool, then done or error
//   POST /api/voice/tts                  one sentence to WAV, for Read replies aloud
// The mic is the browser's speech recogniser: words fill the box and the
// message sends when the speaker stops. It is the only chat page: /voice is a
// 301 here, and the live call (speech to speech) is the apps' alone.
// The server owns history and the reset; this page only draws what it returns
// and keeps the one message it is sending until the server has it.
import { html, useState, useEffect, useRef, useCallback, Button, ErrorState, SkeletonRows, toast, mount, getJson } from "../../core/app/boot.js";
import { Blocks } from "./blocks.js";
import { Markdown } from "./markdown.js";
import "./app.css";

const SESSION = "app";
const HISTORY = `/api/voice/history?session=${SESSION}&limit=200`;
const POLL_MS = 15000;
// The Voice service answers a failed turn with 200 and this prefix (Chat.swift).
const FAILURE = "(error:";
// History keeps `[photo]` and `[file: name]` for the model; the attachment shows instead.
const MARKS = /\s*\[(photo|file: [^\]]*)\]/g;

const toolName = (t) => String(t).replace(/_/g, " ");
const timeOf = (ts) => {
  const d = ts ? new Date(ts) : null;
  return d && !isNaN(d) ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
};

/* Server turns as this page draws them. Ids come from time and role, as the apps do. */
function fromServer(body) {
  const seen = {};
  return (body.turns || []).filter((t) => t.role === "user" || t.role === "assistant").map((t) => {
    const key = `s:${t.ts || ""}|${t.role}`;
    const n = (seen[key] = (seen[key] || 0) + 1);
    const attachments = Array.isArray(t.attachments) ? t.attachments : [];
    return {
      id: n === 1 ? key : `${key}|${n - 1}`, role: t.role, ts: t.ts,
      text: attachments.length ? String(t.text || "").replace(MARKS, "").trim() : String(t.text || ""),
      blocks: Array.isArray(t.blocks) ? t.blocks : [], attachments, tools: [],
    };
  });
}

/* The server's turns, plus what only this page holds: the turn in flight and a
   message that failed. A streamed reply keeps its tools once the server has it. */
function merge(server, local) {
  const out = server.map((t) => {
    if (t.role !== "assistant") return t;
    const mine = local.find((l) => l.role === "assistant" && l.tools.length && l.text.trim() === t.text.trim());
    return mine ? { ...t, tools: mine.tools } : t;
  });
  const held = local.filter((l) => l.local && !server.some((s) => s.role === l.role && s.text.trim() === l.text.trim()));
  return out.concat(held);
}

function Attachment({ a }) {
  if (a.kind === "image") return html`<a class="chat-att" href=${a.url} target="_blank" rel="noopener"><img src=${a.url} alt=${a.name || "Photo"} loading="lazy" /></a>`;
  return html`<a class="chat-att chat-file" href=${a.url} target="_blank" rel="noopener"><i class="ph ph-file-text" aria-hidden="true"></i><span class="ellipsis">${a.name}</span></a>`;
}

function Tools({ names, live }) {
  if (!names.length) return null;
  return html`<div class="chat-tools" aria-label="Tools used">
    <i class=${`ph ${live ? "ph-gear-six chat-spin" : "ph-wrench"}`} aria-hidden="true"></i>
    ${names.map((n) => html`<span class="badge badge-plain">${toolName(n)}</span>`)}
  </div>`;
}

function Turn({ turn, onRetry }) {
  if (turn.role === "user") {
    return html`<li class=${`chat-turn chat-me${turn.failed ? " is-failed" : ""}`}>
      ${turn.attachments.length > 0 && html`<div class="chat-atts">${turn.attachments.map((a) => html`<${Attachment} a=${a} />`)}</div>`}
      ${turn.text && html`<div class="chat-bubble">${turn.text}</div>`}
      <div class="chat-meta num">
        ${turn.failed
          ? html`<span class="chat-fail">Not sent. Voice did not answer.</span><${Button} size="sm" kind="tertiary" onClick=${() => onRetry(turn)}>Send again</${Button}>`
          : turn.local ? html`<span>Sending</span>` : html`<span>${timeOf(turn.ts)}</span>`}
      </div>
    </li>`;
  }
  const waiting = turn.streaming && !turn.text;
  return html`<li class="chat-turn chat-voice">
    <${Tools} names=${turn.tools} live=${turn.streaming} />
    ${waiting
      ? html`<div class="chat-typing muted" aria-live="polite">${turn.tools.length ? `Using ${toolName(turn.tools[turn.tools.length - 1])}` : "Thinking"}</div>`
      : html`<${Markdown} text=${turn.text} />`}
    ${turn.blocks.length > 0 && html`<${Blocks} blocks=${turn.blocks} />`}
    ${!turn.streaming && turn.ts && html`<div class="chat-meta num"><span>${timeOf(turn.ts)}</span></div>`}
  </li>`;
}

/* Speech in: the browser's own recogniser (Chrome, Edge, Safari). Words land in
   the box as they are heard and the message sends when the speaker stops. */
const Recognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
const MIC_ERRORS = {
  "not-allowed": ["Microphone blocked", "Allow the microphone for this site in the browser's settings, or type instead."],
  "service-not-allowed": ["Microphone blocked", "Allow the microphone for this site in the browser's settings, or type instead."],
  "no-speech": ["Heard nothing", "Tap the mic and speak again."],
  "audio-capture": ["No microphone found", "Plug one in or type instead."],
  network: ["Speech input is offline", "The browser's speech service did not answer. Type instead."],
};

function useDictation(onHeard, onFinal) {
  const [listening, setListening] = useState(false);
  const rec = useRef(null);
  const stop = useCallback(() => { if (rec.current) rec.current.stop(); }, []);
  const start = useCallback(() => {
    if (!Recognition || rec.current) return;
    const r = new Recognition();
    r.lang = navigator.language || "en-GB";
    r.interimResults = true;
    r.continuous = false;
    let said = "";
    r.onresult = (e) => {
      said = Array.from(e.results).map((x) => x[0].transcript).join("");
      onHeard(said);
    };
    r.onerror = (e) => {
      const [title, desc] = MIC_ERRORS[e.error] || (e.error === "aborted" ? [] : ["Speech input stopped", "Tap the mic to try again, or type instead."]);
      if (title) toast({ title, desc, kind: "danger" });
      said = "";
    };
    r.onend = () => {
      rec.current = null;
      setListening(false);
      if (said.trim()) onFinal(said.trim());
    };
    rec.current = r;
    setListening(true);
    try { r.start(); } catch { rec.current = null; setListening(false); }
  }, [onHeard, onFinal]);
  useEffect(() => () => { if (rec.current) rec.current.abort(); }, []);
  return { listening, start, stop };
}

/* Speech out: Voice's own text to speech (/api/voice/tts, Kokoro on h), one
   sentence a request, the next fetched while this one plays. */
const ALOUD_KEY = "chat-read-aloud";
const sentences = (text) => (String(text).replace(/\s+/g, " ").match(/[^.!?]+[.!?]*\s*/g) || [])
  .map((s) => s.trim()).filter(Boolean).flatMap((s) => s.match(/.{1,380}(\s|$)/g) || [s]);

function useReadAloud() {
  const [on, setOn] = useState(() => { try { return localStorage.getItem(ALOUD_KEY) === "1"; } catch { return false; } });
  const run = useRef(0);
  const audio = useRef(null);
  const quiet = useCallback(() => { run.current += 1; if (audio.current) { audio.current.pause(); audio.current = null; } }, []);
  const toggle = useCallback(() => setOn((v) => {
    try { localStorage.setItem(ALOUD_KEY, v ? "0" : "1"); } catch { /* storage off */ }
    if (v) quiet();
    return !v;
  }), [quiet]);
  const say = useCallback(async (text) => {
    if (!on) return;
    quiet();
    const mine = run.current;
    const fetchOne = (s) => fetch("/api/voice/tts", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: s }),
    }).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob(); });
    const parts = sentences(text);
    try {
      let next = parts.length ? fetchOne(parts[0]) : null;
      for (let i = 0; i < parts.length && mine === run.current; i++) {
        const blob = await next;
        next = i + 1 < parts.length ? fetchOne(parts[i + 1]) : null;
        if (mine !== run.current) break;
        const url = URL.createObjectURL(blob);
        const a = new Audio(url);
        audio.current = a;
        await new Promise((done) => { a.onended = a.onerror = a.onpause = done; a.play().catch(done); });
        URL.revokeObjectURL(url);
      }
    } catch {
      if (mine === run.current) toast({ title: "Reply not read aloud", desc: "The speech service did not answer. The reply is on screen.", kind: "danger" });
    }
  }, [on, quiet]);
  useEffect(() => quiet, [quiet]);
  return { on, toggle, say, quiet };
}

function Composer({ busy, onSend, aloud }) {
  const [text, setText] = useState("");
  const ref = useRef(null);
  const grow = () => { const el = ref.current; if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 200)}px`; } };
  useEffect(grow, [text]);
  const send = () => {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  };
  const heard = useCallback((t) => setText(t), []);
  const spoken = useCallback((t) => { setText(""); onSend(t); }, [onSend]);
  const mic = useDictation(heard, spoken);
  const micLabel = !Recognition ? "This browser has no speech input, type instead" : mic.listening ? "Stop listening" : "Speak a message";
  return html`<form class="chat-composer" onSubmit=${(e) => { e.preventDefault(); send(); }}>
    <button type="button" class=${`btn btn-icon chat-mic ${mic.listening ? "btn-primary is-listening" : "btn-secondary"}`}
      aria-label=${micLabel} data-tip=${micLabel} aria-pressed=${mic.listening ? "true" : "false"}
      disabled=${!Recognition || busy} onClick=${() => { aloud.quiet(); mic.listening ? mic.stop() : mic.start(); }}>
      <i class=${`ph ${mic.listening ? "ph-microphone-fill" : "ph-microphone"}`} aria-hidden="true"></i>
    </button>
    <textarea ref=${ref} class="input chat-input" rows="1" placeholder=${mic.listening ? "Listening" : "Message Voice"} aria-label="Message"
      value=${text} onInput=${(e) => setText(e.currentTarget.value)}
      onKeyDown=${(e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } }}></textarea>
    <button type="button" class="btn btn-tertiary btn-icon chat-aloud" aria-pressed=${aloud.on ? "true" : "false"}
      aria-label=${aloud.on ? "Stop reading replies aloud" : "Read replies aloud"} data-tip=${aloud.on ? "Replies are read aloud" : "Read replies aloud"}
      onClick=${aloud.toggle}>
      <i class=${`ph ${aloud.on ? "ph-speaker-high" : "ph-speaker-slash"}`} aria-hidden="true"></i>
    </button>
    <${Button} type="submit" kind="primary" busy=${busy} disabled=${!text.trim() || busy}>Send</${Button}>
  </form>`;
}

function Chat() {
  const [server, setServer] = useState(null);
  const [local, setLocal] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const logRef = useRef(null);
  const stick = useRef(true);
  const aloud = useReadAloud();
  const sayRef = useRef(aloud.say);
  sayRef.current = aloud.say;

  const load = useCallback(async () => {
    try {
      const body = await getJson(HISTORY);
      if (!busyRef.current) setServer(fromServer(body));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);

  // History on open, then a poll while the tab is visible so a turn sent from
  // the Mac shows here. The 4am reset arrives the same way: the server's
  // history is empty after it.
  useEffect(() => {
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
    const vis = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", vis); };
  }, [load]);

  const turns = server ? merge(server, local) : [];

  // Follow the conversation unless the reader has scrolled up.
  useEffect(() => {
    const el = logRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  });
  const onScroll = (e) => {
    const el = e.currentTarget;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  const send = useCallback(async (text, retryOf) => {
    busyRef.current = true;
    setBusy(true);
    stick.current = true;
    aloud.quiet();
    const mine = { id: `l:${Date.now()}`, role: "user", text, attachments: [], blocks: [], tools: [], local: true, ts: new Date().toISOString() };
    const reply = { id: `r:${Date.now()}`, role: "assistant", text: "", blocks: [], tools: [], local: true, streaming: true };
    const patch = (fn) => setLocal((l) => l.map((t) => (t.id === reply.id ? fn(t) : t)));
    setLocal((l) => l.filter((t) => t.id !== retryOf).concat(mine, reply));
    let ok = false;
    try {
      const r = await fetch("/api/voice/chat/stream", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session: SESSION }),
      });
      if (!r.ok || !r.body) throw new Error(`stream answered ${r.status}`);
      const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (value) buf += value;
        const lines = buf.split("\n");
        buf = done ? "" : lines.pop();
        for (const line of lines) {
          let ev;
          try { ev = JSON.parse(line); } catch { continue; }
          if (ev.t === "delta" && ev.text) patch((t) => ({ ...t, text: t.text + ev.text }));
          else if (ev.t === "tool" && ev.name) patch((t) => ({ ...t, tools: t.tools.includes(ev.name) ? t.tools : [...t.tools, ev.name] }));
          else if (ev.t === "done") {
            const text = String(ev.reply || "");
            if (text.trim().startsWith(FAILURE)) throw new Error("voice failed");
            ok = true;
            patch((t) => ({ ...t, text, blocks: Array.isArray(ev.blocks) ? ev.blocks : [], tools: ev.tools || t.tools, streaming: false }));
            sayRef.current(text);
          } else if (ev.t === "error") throw new Error("voice failed");
        }
        if (done) break;
      }
      if (!ok) throw new Error("stream ended early");
    } catch (e) {
      setLocal((l) => l.filter((t) => t.id !== reply.id).map((t) => (t.id === mine.id ? { ...t, failed: true } : t)));
      toast({ title: "Message not sent", desc: "Voice did not answer. Send it again from the message.", kind: "danger" });
    }
    busyRef.current = false;
    setBusy(false);
    // The server now holds both turns; its history replaces the local copies.
    if (ok) {
      try {
        const fresh = fromServer(await getJson(HISTORY));
        setServer(fresh);
        // The reply stays only to lend the server's copy its tools (merge).
        setLocal((l) => l.filter((t) => t.id !== mine.id).map((t) => (t.id === reply.id ? { ...t, local: false } : t)));
      } catch { /* the poll picks it up */ }
    }
  }, [aloud.quiet]);

  if (!server && error) return html`<div class="chat-wrap"><${ErrorState} error=${error} retry=${load} title="Chat did not load" /></div>`;

  return html`<div class="chat-wrap">
    <div class="chat-log" ref=${logRef} onScroll=${onScroll} aria-live="polite">
      ${!server
        ? html`<${SkeletonRows} rows=${4} height=${48} />`
        : turns.length === 0
          ? html`<div class="chat-empty">
              <i class="ph ph-chats-circle" aria-hidden="true"></i>
              <p class="chat-empty-title">Nothing said since 4am</p>
              <p class="muted">Type, or tap the mic and speak. Voice reads and changes your calendar, todos and notes, and shows every change under its reply.</p>
              <p class="muted">The chat starts fresh at 4am London time. It is the same conversation as the Mac and iPhone apps.</p>
            </div>`
          : html`<ol class="chat-turns">${turns.map((t) => html`<${Turn} key=${t.id} turn=${t} onRetry=${(x) => send(x.text, x.id)} />`)}</ol>`}
    </div>
    ${error && server && html`<p class="chat-offline muted">Could not refresh the conversation. Trying again in a few seconds.</p>`}
    <${Composer} busy=${busy} onSend=${send} aloud=${aloud} />
  </div>`;
}

mount(Chat);
