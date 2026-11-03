// Diagram: the G-System as a flow diagram. Hosts are regions, projects, repos,
// services and dependencies are nodes, and each declared or observed connects
// edge shows what moves (via is the line style, flow is the hover text). Data:
// GET /api/diagram (core/api/diagram.py), which joins gcore's graph with live
// health, edge liveness and Studio's client projects. Layout: elkjs, vendored
// through package.json and bundled by esbuild.
import { html, useState, useEffect, useRef, Badge, Button, ErrorState, Empty, mount, getJson } from "../../core/app/boot.js";
import { useMemo } from "preact/hooks";
import ELK from "elkjs/lib/elk.bundled.js";
import { BANDS, Layers, Links, world } from "./layers.js";
import "./app.css";

const API = "/api/diagram";
const REFRESH_MS = 30000;
const elk = new ELK();

// Health reads through the status tokens. The API speaks the brain's states.
const HEALTH = {
  ok:      { color: "var(--ok)",               label: "Healthy" },
  warn:    { color: "var(--warn)",             label: "Degraded" },
  down:    { color: "var(--danger)",           label: "Down" },
  unknown: { color: "var(--text-placeholder)", label: "No health signal" },
};
const healthOf = (n) => {
  const s = n && n.health && n.health.state;
  return s === "up" ? "ok" : s === "down" ? "down" : s === "warn" || s === "paused" ? "warn" : "unknown";
};

// The via is the line style. Request and stream edges carry a moving dash.
const VIA = {
  http:      { dash: "",          label: "HTTP" },
  sse:       { dash: "",          label: "Server-sent events" },
  websocket: { dash: "",          label: "WebSocket" },
  ssh:       { dash: "10 4 2 4",  label: "SSH" },
  file:      { dash: "6 4",       label: "File or path" },
  path:      { dash: "6 4",       label: "File or path" },
  db:        { dash: "10 3",      label: "Database" },
  vendor:    { dash: "1 4",       label: "Vendored or imported" },
  import:    { dash: "1 4",       label: "Vendored or imported" },
  depends:   { dash: "2 3",       label: "Declared dependency" },
  uses:      { dash: "",          label: "Client uses block" },
  rests:     { dash: "1 4",       label: "Block rests on" },
};
const MOVING = new Set(["http", "sse", "websocket"]);
const KINDS = [["project", "Projects"], ["repo", "Repos"], ["service", "Services"], ["dependency", "Dependencies"], ["domain", "Domains"]];
const DEFAULT_KINDS = new Set(["project", "repo", "service", "dependency"]);
const EXTERNAL = "lane:external", CODE = "lane:code";

const plain = (t) => (window.g && window.g.plain ? window.g.plain(t) : String(t ?? ""));
const short = (n) => plain(n.kind === "repo" || n.kind === "project" ? n.name : n.label || n.name);
const flowText = (e) => (Array.isArray(e.flow) ? e.flow : e.flow ? [e.flow] : []).map(plain);

/* ---- model: the payload as lanes, nodes and edges -------------------------------------------- */

function model(data) {
  const nodes = new Map(data.nodes.map((n) => [n.id, n]));
  const svcHost = new Map();
  for (const e of data.edges) if (e.kind === "runs_on") svcHost.set(e.from, e.to.replace(/^host:/, ""));
  const ownerHost = new Map();
  for (const e of data.edges) if (e.kind === "has_service" && svcHost.get(e.to)) ownerHost.set(e.from, svcHost.get(e.to));
  const laneOf = (n) => {
    if (n.kind === "dependency") return EXTERNAL;
    const h = n.host || svcHost.get(n.id) || ownerHost.get(n.id);
    if (n.kind === "domain") return EXTERNAL;
    return h && nodes.has(`host:${h}`) ? `host:${h}` : CODE;
  };
  const lanes = [
    ...data.nodes.filter((n) => n.kind === "host").map((n) => ({ id: n.id, title: n.name, sub: plain(n.label) })),
    { id: CODE, title: "Code only", sub: "Checkouts with no service of their own" },
    { id: EXTERNAL, title: "Outside", sub: "Dependencies and public domains" },
  ];

  const edges = [];
  const seen = new Set();
  for (const e of data.edges) {
    if (e.kind === "connects") {
      seen.add(`${e.from}>${e.to}`);
      edges.push({ id: `c:${e.from}>${e.to}:${e.via}`, from: e.from, to: e.to, via: e.via || "http", kind: "connects",
        flow: flowText(e), drift: e.drift || null, live: e.live || null, sources: e.sources || [], evidence: e.evidence || [] });
    }
  }
  for (const e of data.edges) {
    if (e.kind === "depends" && !seen.has(`${e.from}>${e.to}`))
      edges.push({ id: `d:${e.from}>${e.to}`, from: e.from, to: e.to, via: "depends", kind: "depends", flow: [], sources: ["declared"] });
    if (e.kind === "routes")
      edges.push({ id: `r:${e.from}>${e.to}`, from: e.from, to: e.to, via: "http", kind: "routes", flow: ["public traffic through nginx"], sources: ["declared"] });
  }

  // Studio's clients: client -> block it uses -> what the block rests on.
  const studio = nodes.get("project:g-studio");
  const clients = studio && Array.isArray(studio.clients) ? studio.clients : null;
  const inner = [];
  if (clients && studio.blocks) {
    const used = new Set();
    for (const p of clients) {
      if (p.archived) continue;
      inner.push({ id: `client:${p.id}`, kind: "client", name: p.id, label: plain(p.name || p.id), sub: plain(p.kind || "client"), parent: studio.id });
      for (const b of p.blocks || []) {
        used.add(b.id);
        edges.push({ id: `u:${p.id}>${b.id}`, from: `client:${p.id}`, to: `block:${b.id}`, via: "uses", kind: "uses", flow: [`uses ${plain(studio.blocks[b.id]?.label || b.id)}`] });
      }
    }
    for (const id of used) {
      const b = studio.blocks[id] || {};
      const r = b.rests_on || {};
      const target = r.edge && ["dependency", "project", "repo", "service"].map((k) => `${k}:${r.edge}`).find((t) => nodes.has(t));
      inner.push({ id: `block:${id}`, kind: "block", name: id, label: plain(b.label || id), sub: r.module ? r.module : r.edge ? `rests on ${r.edge}` : "", parent: studio.id });
      if (target) edges.push({ id: `b:${id}>${target}`, from: `block:${id}`, to: target, via: "rests", kind: "rests", flow: [`${plain(b.label || id)} rests on ${r.edge} over ${r.via || "a declared edge"}`] });
    }
  }
  return { nodes, lanes, laneOf, edges, inner, clients, studio };
}

/* What the page flags, each with the reason in words. */
function problems(m, data) {
  const out = [];
  const name = (id) => { const n = m.nodes.get(id); return n ? short(n) : id; };
  for (const e of m.edges) {
    if (e.kind !== "connects") continue;
    const pair = `${name(e.from)} to ${name(e.to)}`;
    if (e.drift === "unobserved")
      out.push({ key: e.id, tone: "warn", edge: e, title: pair, why: `Declared over ${e.via} but not observed in the code.` });
    else if (e.drift)
      out.push({ key: e.id, tone: "warn", edge: e, title: pair, why: `Observed over ${e.via} but not declared in connects${e.evidence[0] ? `: ${plain(e.evidence[0])}` : "."}` });
    if (e.live === "down")
      out.push({ key: e.id + ":live", tone: "down", edge: e, title: pair, why: `${name(e.to)} is down, so this ${e.via} flow is not getting through.` });
  }
  for (const n of m.nodes.values()) {
    if (!["service", "dependency", "project", "repo"].includes(n.kind)) continue;
    const h = healthOf(n);
    if (h === "down" || h === "warn")
      out.push({ key: n.id, tone: h, node: n.id, title: short(n), why: `${HEALTH[h].label}${n.health.detail ? `: ${plain(n.health.detail)}` : "."}` });
  }
  const src = data.sources || {};
  if (src.status && !src.status.ok) out.push({ key: "src:status", tone: "unknown", title: "Health unavailable", why: `The brain status did not answer (${plain(src.status.reason)}), so nodes show no health.` });
  if (src.clients && !src.clients.ok) out.push({ key: "src:clients", tone: "unknown", title: "Studio clients unavailable", why: `Studio's machine API did not answer (${plain(src.clients.reason)}), so g-studio is drawn without its clients.` });
  if (src.gcore && !src.gcore.ok) out.push({ key: "src:gcore", tone: "down", title: "Graph unavailable", why: `gcore's graph did not assemble (${plain(src.gcore.reason)}).` });
  for (const p of data.problems || []) {
    const n = p.node && m.nodes.get(p.node);
    out.push({ key: `gp:${JSON.stringify(p)}`, tone: "warn", node: n ? p.node : undefined, title: n ? short(n) : plain(p.node || "gcore"),
      why: plain(typeof p === "string" ? p : p.problem || p.text || p.message || JSON.stringify(p)) });
  }
  const rank = { down: 0, warn: 1, unknown: 2 };
  return out.sort((a, b) => rank[a.tone] - rank[b.tone]);
}

/* ---- which nodes and edges are on the canvas -------------------------------------------------- */

function visible(m, f, flagged) {
  const edgeOk = (e) => e.kind === "connects" || e.kind === "uses" || e.kind === "rests"
    || (e.kind === "depends" && f.kinds.has("dependency") && f.depends)
    || (e.kind === "routes" && f.kinds.has("domain"));
  const nodeOk = (id) => {
    if (id.startsWith("client:") || id.startsWith("block:")) return true;
    const n = m.nodes.get(id);
    if (!n || !f.kinds.has(n.kind)) return false;
    return !f.host || m.laneOf(n) === f.host;
  };
  let edges = m.edges.filter((e) => edgeOk(e) && nodeOk(e.from) && nodeOk(e.to));
  if (f.problems) {
    const bad = (e) => e.drift || e.live === "down";
    const badNode = (id) => ["down", "warn"].includes(healthOf(m.nodes.get(id)));
    edges = edges.filter((e) => bad(e) || badNode(e.to) || badNode(e.from));
  }
  if (f.query) {
    const hit = (id) => { const n = m.nodes.get(id) || m.inner.find((x) => x.id === id); return n && `${n.name} ${n.label || ""}`.toLowerCase().includes(f.query); };
    edges = edges.filter((e) => hit(e.from) || hit(e.to));
  }
  // Studio's inner edges need a path back to Studio's outer world to be worth drawing.
  const ids = new Set();
  for (const e of edges) { ids.add(e.from); ids.add(e.to); }
  if ([...ids].some((id) => id.startsWith("client:") || id.startsWith("block:"))) ids.add("project:g-studio");
  if (ids.has("project:g-studio") && !f.problems && !f.query) for (const x of m.inner) ids.add(x.id);
  return { ids, edges: edges.filter((e) => ids.has(e.from) && ids.has(e.to)) };
}

/* ---- layout (elkjs, layered, left to right) --------------------------------------------------- */

const CH = 7.6;   // px per character at 12px Inter, near enough for box widths
const size = (n) => {
  const label = n.kind === "client" || n.kind === "block" ? n.label : short(n);
  const sub = n.sub || n.kind;
  const w = Math.max(label.length * CH + 40, sub.length * 6 + 28);
  return { width: Math.round(Math.min(Math.max(w, 112), 232)), height: n.kind === "client" ? 36 : 44 };
};

async function layout(m, vis) {
  const all = new Map();
  for (const id of vis.ids) {
    const n = m.nodes.get(id) || m.inner.find((x) => x.id === id);
    if (n) all.set(id, n);
  }
  const studioOpen = vis.ids.has("project:g-studio") && m.inner.some((x) => vis.ids.has(x.id));
  const parentOf = new Map();
  const tree = { id: "root", children: [], edges: [], layoutOptions: {
    "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.edgeRouting": "ORTHOGONAL", "elk.layered.spacing.nodeNodeBetweenLayers": "48",
    "elk.spacing.nodeNode": "16", "elk.layered.spacing.edgeNodeBetweenLayers": "16", "elk.spacing.edgeEdge": "8",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF", "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    "elk.spacing.componentComponent": "32",
  } };
  const box = (id, extra = {}) => ({ id, ...extra });
  const lanes = new Map();
  for (const l of m.lanes) lanes.set(l.id, box(l.id, { children: [], edges: [], layoutOptions: { "elk.padding": "[top=44,left=16,bottom=16,right=16]" } }));
  let studioBox = null;
  for (const [id, n] of all) {
    if (n.parent) continue;
    const lane = lanes.get(m.laneOf(n));
    const b = box(id, size(n));
    if (id === "project:g-studio" && studioOpen) {
      delete b.width; delete b.height;
      b.children = []; b.edges = [];
      b.layoutOptions = { "elk.padding": "[top=52,left=12,bottom=12,right=12]" };
      studioBox = b;
    }
    lane.children.push(b);
    parentOf.set(id, lane.id);
  }
  if (studioBox) for (const [id, n] of all) if (n.parent) { studioBox.children.push(box(id, size(n))); parentOf.set(id, "project:g-studio"); }
  for (const l of m.lanes) if (lanes.get(l.id).children.length) { tree.children.push(lanes.get(l.id)); parentOf.set(l.id, "root"); }

  // Each edge goes in its lowest common container, so its points come back in that frame.
  const chain = (id) => { const c = []; let p = parentOf.get(id); while (p) { c.push(p); p = parentOf.get(p); } return c; };
  const boxes = new Map([["root", tree]]);
  const index = (b) => { for (const c of b.children || []) { boxes.set(c.id, c); index(c); } };
  index(tree);
  for (const e of vis.edges) {
    if (!boxes.has(e.from) || !boxes.has(e.to)) continue;
    const up = chain(e.to);
    const lca = chain(e.from).find((c) => up.includes(c)) || "root";
    boxes.get(lca).edges.push({ id: e.id, sources: [e.from], targets: [e.to] });
  }
  const out = await elk.layout(tree);

  const pos = new Map();
  const walk = (b, ox, oy) => {
    const x = ox + (b.x || 0), y = oy + (b.y || 0);
    pos.set(b.id, { x, y, w: b.width, h: b.height });
    for (const c of b.children || []) walk(c, x, y);
  };
  walk(out, -out.x || 0, -out.y || 0);
  const paths = new Map();
  const collect = (b) => {
    const o = pos.get(b.id);
    for (const e of b.edges || []) {
      const s = e.sections && e.sections[0];
      if (!s) continue;
      const frame = e.container ? pos.get(e.container) || o : o;
      const pts = [s.startPoint, ...(s.bendPoints || []), s.endPoint].map((p) => [p.x + frame.x, p.y + frame.y]);
      paths.set(e.id, pts);
    }
    for (const c of b.children || []) collect(c);
  };
  collect(out);
  return { width: out.width, height: out.height, pos, paths, studioOpen };
}

/* A rounded orthogonal path through the points, and the point halfway along it. */
function pathD(pts) {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x, y] = pts[i];
    if (i < pts.length - 1) {
      const [px, py] = pts[i - 1], [nx, ny] = pts[i + 1];
      const r = Math.min(6, Math.hypot(x - px, y - py) / 2, Math.hypot(nx - x, ny - y) / 2);
      const ax = x - Math.sign(x - px) * r, ay = y - Math.sign(y - py) * r;
      const bx = x + Math.sign(nx - x) * r, by = y + Math.sign(ny - y) * r;
      d += ` L${ax},${ay} Q${x},${y} ${bx},${by}`;
    } else d += ` L${x},${y}`;
  }
  return d;
}
function midpoint(pts) {
  const segs = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
  let half = segs.reduce((a, b) => a + b, 0) / 2;
  for (let i = 0; i < segs.length; i++) {
    if (half <= segs[i]) { const t = segs[i] ? half / segs[i] : 0; return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t]; }
    half -= segs[i];
  }
  return pts[0];
}

/* ---- drawing ---------------------------------------------------------------------------------- */

const tone = (e) => (e.live === "down" ? "down" : e.drift ? "drift" : "plain");

function Canvas({ m, lay, vis, focus, setFocus, fit, width }) {
  const near = useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    for (const e of vis.edges) if (e.from === focus || e.to === focus) { s.add(e.from); s.add(e.to); }
    return s;
  }, [focus, vis]);
  const nodeOf = (id) => m.nodes.get(id) || m.inner.find((x) => x.id === id);
  const W = Math.ceil(lay.width), H = Math.ceil(lay.height);
  // Readable size shrinks to the card down to 80 %, then scrolls; fit shows the whole thing.
  const room = Math.max(width - 2, 200);
  const k = fit ? Math.min(1, room / W) : Math.min(1, Math.max(room / W, 0.8));
  return html`<svg class="dg-svg" viewBox=${`0 0 ${W} ${H}`} width=${Math.round(W * k)} height=${Math.round(H * k)}
      role="img" aria-label="G-System flow diagram" onClick=${(ev) => ev.target === ev.currentTarget && setFocus(null)}>
    <defs>
      ${["plain", "drift", "down", "hot"].map((t) => html`<marker id=${`dg-arrow-${t}`} key=${t} class=${`dg-arrow dg-arrow-${t}`}
        viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,1 L9,5 L0,9 z" /></marker>`)}
    </defs>
    ${m.lanes.filter((l) => lay.pos.has(l.id)).map((l) => { const p = lay.pos.get(l.id); return html`<g class="dg-lane" key=${l.id}>
      <rect x=${p.x} y=${p.y} width=${p.w} height=${p.h} rx="8" />
      <text x=${p.x + 16} y=${p.y + 22} class="dg-lane-title">${l.title}</text>
      <text x=${p.x + 16} y=${p.y + 36} class="dg-lane-sub">${l.sub}</text></g>`; })}
    ${lay.studioOpen && lay.pos.has("project:g-studio") && (() => { const p = lay.pos.get("project:g-studio"); const n = m.nodes.get("project:g-studio"); const h = healthOf(n);
      const dim = near && !near.has(n.id) && ![...near].some((id) => nodeOf(id)?.parent);
      return html`<g class=${`dg-group ${dim ? "dim" : ""} ${focus === n.id ? "is-focus" : ""}`} onClick=${() => setFocus(n.id)}>
        <rect x=${p.x} y=${p.y} width=${p.w} height=${p.h} rx="8" />
        <circle cx=${p.x + 18} cy=${p.y + 20} r="5" fill=${HEALTH[h].color}><title>${HEALTH[h].label}</title></circle>
        <text x=${p.x + 30} y=${p.y + 24} class="dg-label">g-studio</text>
        <text x=${p.x + 12} y=${p.y + 42} class="dg-sub">Clients and the Studio blocks each one uses</text></g>`; })()}
    <g class="dg-edges">
      ${vis.edges.filter((e) => lay.paths.has(e.id)).map((e) => {
        const pts = lay.paths.get(e.id), t = tone(e);
        const hot = focus && (e.from === focus || e.to === focus);
        const dim = near && !hot;
        const [mx, my] = midpoint(pts);
        const d = pathD(pts);
        const tip = `${short(nodeOf(e.from) || { name: e.from })} to ${short(nodeOf(e.to) || { name: e.to })} (${VIA[e.via]?.label || e.via})${e.flow.length ? "\n" + e.flow.join("\n") : ""}${e.drift === "unobserved" ? "\nDeclared, not observed" : e.drift ? "\nObserved, not declared" : ""}${e.live === "down" ? "\nTarget is down" : ""}`;
        return html`<g key=${e.id} class=${`dg-edge dg-${t} dg-k-${e.kind} ${hot ? "hot" : ""} ${dim ? "dim" : ""}`}>
          <path class="dg-hit" d=${d}><title>${tip}</title></path>
          <path class="dg-line" d=${d} stroke-dasharray=${VIA[e.via]?.dash || undefined}
            marker-end=${`url(#dg-arrow-${hot ? "hot" : t})`} />
          ${MOVING.has(e.via) && e.kind !== "routes" && html`<path class="dg-move" d=${d} />`}
          ${t !== "plain" && html`<g class="dg-flag" transform=${`translate(${mx},${my})`}><circle r="7" /><text y="3.5">${t === "down" ? "×" : "!"}</text></g>`}
        </g>`;
      })}
    </g>
    ${[...lay.pos.entries()].filter(([id]) => !id.startsWith("lane:") && !id.startsWith("host:") && id !== "root" && !(id === "project:g-studio" && lay.studioOpen)).map(([id, p]) => {
      const n = nodeOf(id);
      if (!n) return null;
      const h = n.kind === "client" || n.kind === "block" ? null : healthOf(n);
      const label = n.kind === "client" || n.kind === "block" ? n.label : short(n);
      const sub = n.sub || (n.kind === "dependency" && n.criticality ? `dependency, ${n.criticality}` : n.kind);
      return html`<g key=${id} class=${`dg-node dg-n-${n.kind} ${h === "down" ? "is-down" : ""} ${focus === id ? "is-focus" : ""} ${near && !near.has(id) ? "dim" : ""}`}
          transform=${`translate(${p.x},${p.y})`} onClick=${() => setFocus(id)} tabindex="0" role="button" aria-label=${`${label}, ${h ? HEALTH[h].label : n.kind}`}
          onKeyDown=${(ev) => (ev.key === "Enter" || ev.key === " ") && (ev.preventDefault(), setFocus(id))}>
        <rect width=${p.w} height=${p.h} rx="6" />
        ${h && html`<circle cx="14" cy=${p.h / 2} r="4.5" fill=${HEALTH[h].color}><title>${HEALTH[h].label}</title></circle>`}
        <text x=${h ? 26 : 12} y=${n.kind === "client" ? 15 : 19} class="dg-label">${label}</text>
        <text x=${h ? 26 : 12} y=${n.kind === "client" ? 29 : 34} class="dg-sub">${sub}</text>
      </g>`;
    })}
  </svg>`;
}

function Legend() {
  const line = (cls, dash, moving) => html`<svg width="36" height="10" aria-hidden="true"><path class=${`dg-legend-line ${cls}`} d="M1,5 L35,5" stroke-dasharray=${dash || undefined} />${moving && html`<path class="dg-move" d="M1,5 L35,5" />`}</svg>`;
  return html`<div class="dg-legend" aria-label="Legend">
    ${Object.entries(HEALTH).map(([k, s]) => html`<span key=${k}><i class="dg-dot" style=${{ background: s.color }}></i>${s.label}</span>`)}
    <span>${line("", "", true)}HTTP, SSE or WebSocket</span>
    <span>${line("", "6 4")}File or path</span>
    <span>${line("", "1 4")}Vendored or imported</span>
    <span>${line("", "10 4 2 4")}SSH</span>
    <span>${line("dg-drift", "")}Drift: declared and observed disagree</span>
    <span>${line("dg-down", "")}Target down</span>
  </div>`;
}

function FlowRow({ e, m, dir, setFocus }) {
  const other = dir === "out" ? e.to : e.from;
  const n = m.nodes.get(other) || m.inner.find((x) => x.id === other);
  const t = tone(e);
  return html`<div class="list-item dg-flow">
    <div class="main">
      <button type="button" class="dg-link" onClick=${() => setFocus(other)}>${dir === "out" ? "To" : "From"} ${n ? (n.label && (n.kind === "client" || n.kind === "block") ? n.label : short(n)) : other}</button>
      ${e.flow.map((f, i) => html`<span class="sub" key=${i}>${f}</span>`)}
    </div>
    <div class="end">
      ${t === "drift" && html`<${Badge} kind="warn">${e.drift === "unobserved" ? "Not observed" : "Not declared"}<//>`}
      ${t === "down" && html`<${Badge} kind="danger">Target down<//>`}
      <${Badge} kind="plain">${e.via}<//>
    </div>
  </div>`;
}

function Focus({ id, m, edges, setFocus }) {
  const n = m.nodes.get(id) || m.inner.find((x) => x.id === id);
  if (!n) return null;
  const h = n.kind === "client" || n.kind === "block" ? null : healthOf(n);
  const outs = edges.filter((e) => e.from === id), ins = edges.filter((e) => e.to === id);
  const services = n.health && n.health.services ? Object.entries(n.health.services) : [];
  return html`<section class="card dg-focus">
    <div class="card-head"><h2 class="card-title">${n.kind === "client" || n.kind === "block" ? n.label : short(n)}</h2>
      <${Button} size="sm" kind="tertiary" onClick=${() => setFocus(null)}>Clear focus<//></div>
    <dl class="facts">
      <dt>Kind</dt><dd>${n.kind}</dd>
      ${h && html`<dt>Health</dt><dd style=${{ color: HEALTH[h].color }}>${HEALTH[h].label}${n.health && n.health.detail ? `, ${plain(n.health.detail)}` : ""}</dd>`}
      ${services.length > 0 && html`<dt>Services</dt><dd>${services.map(([s, st]) => `${s} ${st || "unknown"}`).join(", ")}</dd>`}
      ${n.powers && html`<dt>Powers</dt><dd>${plain(n.powers)}</dd>`}
      ${n.kind !== "client" && n.kind !== "block" && n.label && n.label !== n.name && html`<dt>About</dt><dd>${plain(n.label)}</dd>`}
    </dl>
    <h3 class="dg-h3">Flows out <span class="num muted">${outs.length}</span></h3>
    ${outs.length ? html`<div class="list">${outs.map((e) => html`<${FlowRow} key=${e.id} e=${e} m=${m} dir="out" setFocus=${setFocus} />`)}</div>` : html`<p class="muted small">Nothing flows out of here.</p>`}
    <h3 class="dg-h3">Flows in <span class="num muted">${ins.length}</span></h3>
    ${ins.length ? html`<div class="list">${ins.map((e) => html`<${FlowRow} key=${e.id} e=${e} m=${m} dir="in" setFocus=${setFocus} />`)}</div>` : html`<p class="muted small">Nothing flows in.</p>`}
  </section>`;
}

function Flagged({ list, setFocus }) {
  return html`<section class="card dg-flagged">
    <div class="card-head"><h2 class="card-title">Flagged <span class="num muted">${list.length}</span></h2></div>
    ${list.length ? html`<div class="list">${list.map((p) => html`<div class="list-item" key=${p.key}>
        <i class="dg-dot" style=${{ background: HEALTH[p.tone === "drift" ? "warn" : p.tone]?.color || HEALTH.unknown.color }}></i>
        <div class="main">
          ${p.edge || p.node ? html`<button type="button" class="dg-link" onClick=${() => setFocus(p.node || p.edge.from)}>${p.title}</button>` : html`<span>${p.title}</span>`}
          <span class="sub">${p.why}</span>
        </div></div>`)}</div>`
      : html`<p class="muted small">Declared and observed agree everywhere and every target answers.</p>`}
  </section>`;
}

function FlowList({ m, edges, setFocus }) {
  const flows = edges.filter((e) => e.kind === "connects");
  const by = new Map();
  for (const e of flows) (by.get(e.from) || by.set(e.from, []).get(e.from)).push(e);
  return html`<section class="card dg-flows">
    <div class="card-head"><h2 class="card-title">Flows <span class="num muted">${flows.length}</span></h2></div>
    ${[...by.entries()].map(([from, es]) => { const n = m.nodes.get(from); return html`<div class="dg-flow-group" key=${from}>
      <h3 class="dg-h3"><button type="button" class="dg-link" onClick=${() => setFocus(from)}>${n ? short(n) : from}</button></h3>
      <div class="list">${es.map((e) => html`<${FlowRow} key=${e.id} e=${e} m=${m} dir="out" setFocus=${setFocus} />`)}</div></div>`; })}
  </section>`;
}

/* ---- the page --------------------------------------------------------------------------------- */

function Diagram() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const [kinds, setKinds] = useState(DEFAULT_KINDS);
  const [host, setHost] = useState("");
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [depends, setDepends] = useState(false);
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState(null);
  const [fit, setFit] = useState(false);
  const [mode, setMode] = useState("layers");
  const [by, setBy] = useState("natural");
  const [hidden, setHidden] = useState(() => new Set());
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [width, setWidth] = useState(900);
  const [lay, setLay] = useState(null);
  const [layError, setLayError] = useState(null);
  const wrap = useRef(null);

  // Load, then refresh every 30 s while the tab is visible, and at once on return.
  useEffect(() => {
    let live = true;
    getJson(API).then((d) => live && (setData(d), setError(null)), (e) => live && setError(e));
    return () => { live = false; };
  }, [tick]);
  useEffect(() => {
    const t = setInterval(() => document.visibilityState === "visible" && setTick((x) => x + 1), REFRESH_MS);
    const v = () => document.visibilityState === "visible" && setTick((x) => x + 1);
    document.addEventListener("visibilitychange", v);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", v); };
  }, []);

  const m = useMemo(() => (data && data.nodes ? model(data) : null), [data]);
  const flagged = useMemo(() => (m ? problems(m, data) : []), [m]);
  const w = useMemo(() => (data && data.nodes ? world(data) : null), [data]);
  const toggleIn = (set) => (k) => set((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const collapseAll = () => setCollapsed(collapsed.size ? new Set() : new Set(BANDS.map((b) => b.id)));
  const f = { kinds, host, problems: onlyProblems, depends, query };
  const vis = useMemo(() => (m ? visible(m, f) : null), [m, kinds, host, onlyProblems, depends, query]);
  // Re-lay out only when the drawn structure changes, not on every health refresh.
  const shape = vis ? [...vis.ids].sort().join(",") + "|" + vis.edges.map((e) => e.id).sort().join(",") : "";
  useEffect(() => {
    if (!vis || !vis.edges.length) { setLay(null); return; }
    let live = true;
    layout(m, vis).then((l) => live && (setLay(l), setLayError(null)), (e) => live && setLayError(e));
    return () => { live = false; };
  }, [shape]);

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [!!data]);

  const toggleKind = (k) => setKinds((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const s = data && data.summary;
  const studioWhy = data && data.sources && data.sources.clients && !data.sources.clients.ok ? data.sources.clients.reason : null;
  const stats = error && !data ? "Unavailable" : s
    ? mode === "layers" ? `${s.nodes} parts, ${s.edges} links, ${flagged.length} flagged`
    : `${vis ? vis.edges.filter((e) => e.kind === "connects").length : 0} flows, ${s.drift} drifted, ${s.live_down} down` : "Loading";
  const seg = (name, value, set, opts) => html`<div class="g-segmented g-segmented-sm" role="radiogroup" aria-label=${name}>
    ${opts.map(([v, label]) => html`<label key=${v}><input type="radio" name=${name} value=${v} checked=${value === v} onChange=${() => set(v)} />${label}</label>`)}</div>`;

  return html`
    <div class="page-head">
      <div class="page-head-text">
        <div class="row-tight">
          <h1 class="page-title">Diagram</h1>
          <${Badge} kind="plain" class="num">${stats}<//>
        </div>
        <p class="page-sub">${mode === "layers"
          ? "The whole G-System, one band per level, read from gcore's manifest, g-levels and every checkout. Health is live, refreshed every 30 seconds. Choose a part to draw its links."
          : "How the G-System flows, drawn from every repo's declared connects and what gcore observes in the code. Node colour is live health, refreshed every 30 seconds."}</p>
      </div>
    </div>
    ${error && !data
      ? html`<section class="card"><${ErrorState} error=${error} title="Could not load the diagram" retry=${() => setTick((t) => t + 1)} /></section>`
      : html`
      <div class="dg-filters">
        ${seg("View", mode, (v) => { setMode(v); setFocus(null); }, [["layers", "Whole system"], ["flows", "Flows"]])}
      </div>
      ${mode === "layers" ? html`
      <div class="dg-filters">
        <input class="input dg-q" type="search" placeholder="Search parts" aria-label="Search parts"
          value=${query} onInput=${(e) => setQuery(e.currentTarget.value.trim().toLowerCase())} />
        ${seg("Group by", by, setBy, [["natural", "Group by kind"], ["host", "Group by host"]])}
        <span class="dg-chips" role="group" aria-label="Bands">
          ${BANDS.map((b) => html`<${Button} key=${b.id} size="sm" kind=${hidden.has(b.id) ? "secondary" : "primary"} aria-pressed=${!hidden.has(b.id)} onClick=${() => toggleIn(setHidden)(b.id)}>${b.title}<//>`)}
        </span>
        <${Button} size="sm" kind=${onlyProblems ? "primary" : "secondary"} aria-pressed=${onlyProblems} onClick=${() => setOnlyProblems(!onlyProblems)}>Only problems<//>
        <${Button} size="sm" kind="tertiary" class="dg-fit" onClick=${collapseAll}>${collapsed.size ? "Expand all" : "Collapse all"}<//>
      </div>
      ${error && html`<p class="small dg-stale">The last refresh failed, so this is the previous reading. It tries again in 30 seconds.</p>`}
      <div class="dg-layout">
        <div class="card dg-canvas dg-pad">
          ${!w ? html`<p class="muted small">Loading the graph</p>`
            : html`<${Layers} data=${data} w=${w} focus=${focus} setFocus=${setFocus} collapsed=${collapsed} toggle=${toggleIn(setCollapsed)}
                filters=${{ by, query, problemsOnly: onlyProblems, hidden }} />`}
        </div>
        <div class="dg-side">
          ${focus && w && html`<${Links} id=${focus} w=${w} setFocus=${setFocus} />`}
          <${Flagged} list=${flagged} setFocus=${setFocus} />
        </div>
      </div>` : html`
      <div class="dg-filters">
        <input class="input dg-q" type="search" placeholder="Search nodes" aria-label="Search nodes"
          value=${query} onInput=${(e) => setQuery(e.currentTarget.value.trim().toLowerCase())} />
        <span class="select-wrap"><select class="input select" aria-label="Host" value=${host} onChange=${(e) => setHost(e.currentTarget.value)}>
          <option value="">All hosts</option>
          ${m && m.lanes.map((l) => html`<option key=${l.id} value=${l.id}>${l.id.startsWith("host:") ? `Host ${l.title}` : l.title}</option>`)}
        </select></span>
        <span class="dg-chips" role="group" aria-label="Kinds">
          ${KINDS.map(([k, label]) => html`<${Button} key=${k} size="sm" kind=${kinds.has(k) ? "primary" : "secondary"} aria-pressed=${kinds.has(k)} onClick=${() => toggleKind(k)}>${label}<//>`)}
        </span>
        <${Button} size="sm" kind=${depends ? "primary" : "secondary"} aria-pressed=${depends} onClick=${() => setDepends(!depends)}>Declared depends<//>
        <${Button} size="sm" kind=${onlyProblems ? "primary" : "secondary"} aria-pressed=${onlyProblems} onClick=${() => setOnlyProblems(!onlyProblems)}>Only problems<//>
        <${Button} size="sm" kind="tertiary" class="dg-fit" onClick=${() => setFit(!fit)}>${fit ? "Readable size" : "Fit whole diagram"}<//>
      </div>
      ${error && html`<p class="small dg-stale">The last refresh failed, so this is the previous reading. It tries again in 30 seconds.</p>`}
      ${studioWhy && html`<p class="small muted">Studio's clients are not shown: its machine API did not answer (${plain(studioWhy)}).</p>`}
      <${Legend} />
      <div class="dg-layout">
        <div class="card dg-canvas" ref=${wrap}>
          ${!data ? html`<p class="muted small dg-pad">Loading the graph</p>`
            : layError ? html`<${ErrorState} error=${layError} title="Could not lay out the diagram" retry=${() => setTick((t) => t + 1)} />`
            : !vis || !vis.edges.length ? html`<${Empty} icon="funnel" title="Nothing matches" desc="No flows pass these filters. Clear the search or turn a kind back on." />`
            : lay ? html`<${Canvas} m=${m} lay=${lay} vis=${vis} focus=${focus} setFocus=${setFocus} fit=${fit} width=${width} />`
            : html`<p class="muted small dg-pad">Laying out</p>`}
        </div>
        <div class="dg-side">
          ${focus && m && html`<${Focus} id=${focus} m=${m} edges=${m.edges} setFocus=${setFocus} />`}
          <${Flagged} list=${flagged} setFocus=${setFocus} />
        </div>
        ${m && vis && html`<${FlowList} m=${m} edges=${vis.edges} setFocus=${setFocus} />`}
      </div>`}`}`;
}

mount(Diagram);
