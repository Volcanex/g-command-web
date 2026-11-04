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
import { Viewport } from "./viewport.js";
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
  part:      { dash: "2 3",       label: "Part of" },
  git:       { dash: "4 3",       label: "Git push and pull" },
  uses:      { dash: "",          label: "Client uses block" },
  rests:     { dash: "1 4",       label: "Block rests on" },
};
const MOVING = new Set(["http", "sse", "websocket"]);
const KINDS = [["project", "Projects"], ["repo", "Repos"], ["dependency", "APIs"], ["domain", "Domains"]];
const DEFAULT_KINDS = new Set(["project", "repo", "dependency"]);
const INTERNET = "lane:internet", EDGE = "lane:edge", CODE = "lane:code", EXTERNAL = "lane:external";
// The reverse proxies a host's public traffic enters through. These name software, not hosts:
// whichever host the manifest puts them on is the host they front.
const INGRESS = ["nginx", "caddy", "cloudflared"];
// Flows Gabriel named as real. Each is drawn only when gcore declares it (connects, depends or
// part_of); until then it is listed under Undeclared rather than invented as an edge.
const EXPECTED = [
  { from: ["service:g-backup"], to: ["dependency:cloudflare-r2", "provider:cloudflare"], what: "g-backup sends the backups to Cloudflare R2" },
  { from: null, to: ["provider:anthropic"], what: "The agents call the Anthropic API" },
  { from: ["provider:namecheap"], to: ["provider:cloudflare"], what: "Namecheap registers the domains Cloudflare serves" },
  { from: ["service:voice", "repo:gbrain"], to: ["dependency:telnyx"], what: "Voice talks to Telnyx" },
  { from: ["provider:cloudflare"], to: ["service:cloudflared"], what: "Which domains ride the cloudflared tunnel" },
];

const plain = (t) => (window.g && window.g.plain ? window.g.plain(t) : String(t ?? ""));
const short = (n) => plain(n.kind === "repo" || n.kind === "project" ? n.name : n.label || n.name);
const flowText = (e) => (Array.isArray(e.flow) ? e.flow : e.flow ? [e.flow] : []).map(plain);
const plural = (k, one, many) => `${k} ${k === 1 ? one : many}`;
const ROLE_ORDER = { server: 0, runner: 1, spare: 2 };

/* ---- model: the payload as lanes, nodes and edges -------------------------------------------- */

// expand: draw each service. Otherwise a service with an owning project or repo is drawn as that
// owner, so a host shows what lives on it rather than every unit; flows land on the owner.
function model(data, expand) {
  const nodes = new Map(data.nodes.map((n) => [n.id, n]));
  const svcHost = new Map(), owner = new Map();
  for (const e of data.edges) if (e.kind === "runs_on") svcHost.set(e.from, e.to.replace(/^host:/, ""));
  for (const e of data.edges) if (e.kind === "has_service") owner.set(e.to, e.from);
  const ownerHost = new Map();
  for (const e of data.edges) if (e.kind === "has_service" && svcHost.get(e.to) && !ownerHost.has(e.from)) ownerHost.set(e.from, svcHost.get(e.to));
  const rep = (id) => (!expand && owner.has(id) ? owner.get(id) : id);
  // Where a thing runs beats where its checkout is: a project sits with its services (Studio's
  // checkout is on h, its services on h2), and its own host field is only the fallback.
  const hostOf = (n) => svcHost.get(n.id) || ownerHost.get(n.id) || n.host;
  const add = (n) => (nodes.set(n.id, { health: null, ...n }), n.id);

  const cloudflare = nodes.has("provider:cloudflare") ? "provider:cloudflare" : null;
  const inEdge = new Set([cloudflare, "dependency:cloudflare-access"].filter(Boolean));
  const laneOf = (n) => {
    if (n.lane) return n.lane;
    if (inEdge.has(n.id) || n.kind === "domain") return cloudflare ? EDGE : EXTERNAL;
    if (n.kind === "dependency" || n.kind === "provider") return EXTERNAL;
    const h = hostOf(n);
    return h && nodes.has(`host:${h}`) ? `host:${h}` : CODE;
  };

  // Hosts as containers, servers first. A host with nothing on it stays, drawn faintly.
  const hosts = data.nodes.filter((n) => n.kind === "host")
    .sort((a, b) => (ROLE_ORDER[a.role] ?? 3) - (ROLE_ORDER[b.role] ?? 3));
  const occupied = new Set();
  for (const n of data.nodes) if (["service", "project"].includes(n.kind) && hostOf(n)) occupied.add(`host:${hostOf(n)}`);
  const lanes = [
    { id: INTERNET, title: "Internet", sub: "Where public traffic starts" },
    ...(cloudflare ? [{ id: EDGE, title: plain(nodes.get(cloudflare).label), sub: "DNS for every zone, and Access in front of private pages" }] : []),
    ...hosts.map((n) => ({ id: n.id, title: n.name, sub: `${plain(n.label)}${n.role ? `, ${n.role}` : ""}`, empty: !occupied.has(n.id) })),
    { id: CODE, title: "Code only", sub: "Checkouts with no service of their own" },
    { id: EXTERNAL, title: "Outside", sub: "Providers and the APIs the projects call" },
  ];
  for (const l of lanes) if (l.empty)
    add({ id: `empty:${l.id}`, kind: "empty", name: "empty", label: "Nothing declared here", sub: "no services or projects", lane: l.id });

  const edges = [];
  const seen = new Set();
  const push = (e) => {
    const from = rep(e.from), to = rep(e.to);
    if (from === to) return;
    const key = `${e.kind}:${from}>${to}:${e.via}`;
    const had = edges.find((x) => x.id === key);
    if (had) { for (const f of e.flow) if (!had.flow.includes(f)) had.flow.push(f); return; }
    edges.push({ drift: null, live: null, sources: ["declared"], evidence: [], ...e, id: key, from, to });
  };
  for (const e of data.edges) {
    if (e.kind === "connects") {
      seen.add(`${rep(e.from)}>${rep(e.to)}`);
      push({ via: e.via || "http", kind: "connects", flow: flowText(e), drift: e.drift || null, live: e.live || null,
        sources: e.sources || [], evidence: e.evidence || [], from: e.from, to: e.to });
    }
  }
  const dependedOn = new Set();
  for (const e of data.edges) {
    if (e.kind === "depends" && !seen.has(`${rep(e.from)}>${rep(e.to)}`)) {
      dependedOn.add(e.to);
      push({ from: e.from, to: e.to, via: "depends", kind: "depends", flow: [] });
    }
  }
  // A dependency that is part of a provider (R2 and Access are Cloudflare) points at it.
  for (const e of data.edges)
    if (e.kind === "part_of") push({ from: e.from, to: e.to, via: "part", kind: "part", flow: [`${short(nodes.get(e.from) || { name: e.from })} is part of ${short(nodes.get(e.to) || { name: e.to })}`] });

  // The way in: the internet, Cloudflare's DNS, each host's ingress, then the service.
  const ingressOn = new Map();
  for (const name of INGRESS) for (const n of data.nodes)
    if (n.kind === "service" && n.name === name && n.host && !ingressOn.has(n.host)) ingressOn.set(n.host, n.id);
  const routed = new Map();   // service id -> its domains
  for (const e of data.edges) if (e.kind === "routes") (routed.get(e.to) || routed.set(e.to, []).get(e.to)).push(e.from.replace(/^domain:/, ""));
  if (cloudflare && routed.size) {
    const visitors = add({ id: "net:visitors", kind: "net", name: "visitors", label: "Visitors", sub: "browsers, apps and bots", lane: INTERNET });
    push({ from: visitors, to: cloudflare, via: "http", kind: "ingress", flow: [`resolves and reaches ${plural(new Set([...routed.values()].flat()).size, "domain", "domains")}`] });
  }
  const perHost = new Map();
  const behind = new Map();   // what an ingress routes to -> that ingress
  for (const [sid, names] of routed) {
    const n = nodes.get(sid);
    if (!n) continue;
    const gate = n.host && ingressOn.get(n.host);
    perHost.set(n.host, (perHost.get(n.host) || 0) + names.length);
    if (gate && gate !== sid) { push({ from: gate, to: sid, via: "http", kind: "ingress", flow: names }); if (rep(sid) !== gate) behind.set(rep(sid), gate); }
    if (cloudflare) push({ from: cloudflare, to: gate || sid, via: "http", kind: "ingress", flow: gate ? [] : names });
  }
  for (const [h, k] of perHost) {
    const gate = ingressOn.get(h);
    const e = gate && edges.find((x) => x.id === `ingress:${cloudflare}>${rep(gate)}:http`);
    if (e) e.flow.unshift(`${plural(k, "domain", "domains")} served on ${h}`);
  }
  // Domains drawn as their own boxes: each one between Cloudflare and what it reaches.
  for (const e of data.edges) if (e.kind === "routes") push({ from: e.from, to: e.to, via: "http", kind: "routes", flow: ["the name this service answers on"] });

  // Code: every project checked out on a host pushes to and pulls from where its url is hosted.
  const hostedBy = new Map();
  for (const e of data.edges) if (e.kind === "hosted_by" && e.from.startsWith("project:")) hostedBy.set(e.from, e.to);
  const code = new Map();
  for (const [pid, prov] of hostedBy) {
    const h = (nodes.get(pid) || {}).host;
    if (!h || !nodes.has(`host:${h}`)) continue;
    const k = `${h}>${prov}`;
    code.set(k, [...(code.get(k) || []), pid]);
  }
  for (const [k, pids] of code) {
    const [h, prov] = k.split(">");
    const id = add({ id: `code:${h}`, kind: "code", name: `code on ${h}`, label: "Checkouts", sub: plural(pids.length, "repo", "repos"), lane: `host:${h}` });
    push({ from: id, to: prov, via: "git", kind: "git", flow: [`${plural(pids.length, "repo", "repos")} on ${h}: ${pids.map((p) => p.replace(/^project:/, "")).join(", ")}`] });
  }

  // What Gabriel named as real but gcore does not declare.
  const raw = data.edges.filter((e) => ["connects", "depends", "part_of"].includes(e.kind));
  const partOf = new Map(data.edges.filter((e) => e.kind === "part_of").map((e) => [e.from, e.to]));
  const undeclared = [];
  for (const x of EXPECTED) {
    const hit = raw.some((e) => (x.to.includes(e.to) || x.to.includes(partOf.get(e.to)))
      && (!x.from || x.from.includes(e.from) || x.from.includes(owner.get(e.from)) || x.from.some((f) => owner.get(f) === e.from)));
    if (!hit) undeclared.push({ key: x.what, what: x.what, ids: [...(x.from || []), ...x.to].filter((id) => nodes.has(id)) });
  }
  const reached = new Set(edges.map((e) => e.to));
  for (const p of data.nodes) if (p.kind === "provider" && !reached.has(p.id) && !undeclared.some((u) => u.ids.includes(p.id)))
    undeclared.push({ key: p.id, what: `${plain(p.label)}: nothing declares a flow to it`, sub: (p.serves || []).map(plain).join(", "), ids: [p.id] });
  for (const p of data.nodes) if (p.kind === "dependency" && !reached.has(p.id))
    undeclared.push({ key: p.id, what: `${short(p)}: in the catalog, no repo declares it`, sub: plain(p.powers), ids: [p.id] });

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
  return { nodes, lanes, laneOf, edges, inner, clients, studio, undeclared, behind };
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

const ALWAYS = new Set(["service", "provider", "net", "code", "empty"]);

function visible(m, f, flagged) {
  const edgeOk = (e) => ["connects", "ingress", "git", "part"].includes(e.kind)
    || (["uses", "rests"].includes(e.kind) && f.clients && f.blocks)
    || (e.kind === "depends" && f.kinds.has("dependency"))
    || (e.kind === "routes" && f.kinds.has("domain"));
  const nodeOk = (id) => {
    if (id.startsWith("client:") || id.startsWith("block:")) return !f.host || f.host === m.laneOf(m.studio || {});
    if (id.startsWith("host:")) return !f.host || f.host === id;
    const n = m.nodes.get(id);
    if (!n || !(ALWAYS.has(n.kind) || f.kinds.has(n.kind))) return false;
    // A host filter keeps that host and what it talks to across its border.
    return true;
  };
  const inHost = (id) => {
    const n = m.nodes.get(id) || (id.startsWith("client:") || id.startsWith("block:") ? m.studio : null);
    return id === f.host || (n && m.laneOf(n) === f.host);
  };
  let edges = m.edges.filter((e) => edgeOk(e) && nodeOk(e.from) && nodeOk(e.to) && (!f.host || inHost(e.from) || inHost(e.to)));
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
  if (ids.has("project:g-studio") && !f.problems && !f.query && f.clients) for (const x of m.inner) if (x.kind === "client" || f.blocks) ids.add(x.id);
  if (!f.problems && !f.query) for (const l of m.lanes) if (l.empty && (!f.host || f.host === l.id)) ids.add(`empty:${l.id}`);
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

// Lanes sit in fixed columns, left to right in the order traffic travels: the internet, Cloudflare,
// the hosts stacked, code with no service, then outside. elkjs lays out each lane on its own, so a
// lane reads as a tidy box, and a flow between lanes is a curve from one box's side to the other's.
const COLUMN = (id) => (id === INTERNET ? 0 : id === EDGE ? 1 : id.startsWith("host:") ? 2 : id === CODE ? 3 : 4);
const LANE_PAD = { top: 52, side: 16, bottom: 16 };   // room for the lane's title and sub line
const COL_GAP = 120, LANE_GAP = 24;
const LANE_OPTS = {
  "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.spacing.nodeNodeBetweenLayers": "48", "elk.spacing.nodeNode": "12", "elk.spacing.edgeEdge": "8",
  "elk.layered.spacing.edgeNodeBetweenLayers": "16", "elk.spacing.componentComponent": "16",
  "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
  "elk.padding": `[top=${LANE_PAD.top},left=${LANE_PAD.side},bottom=${LANE_PAD.bottom},right=${LANE_PAD.side}]`,
};

async function layout(m, vis) {
  const all = new Map();
  for (const id of vis.ids) {
    const n = m.nodes.get(id) || m.inner.find((x) => x.id === id);
    if (n) all.set(id, n);
  }
  const studioOpen = vis.ids.has("project:g-studio") && m.inner.some((x) => vis.ids.has(x.id));
  const laneOfId = new Map();   // node id -> lane id, for every top-level node
  const graphs = new Map();
  for (const l of m.lanes) graphs.set(l.id, { id: l.id, children: [], edges: [], layoutOptions: LANE_OPTS });
  const GROUP_PAD = "[top=56,left=16,bottom=16,right=16]";
  const packed = { "elk.algorithm": "rectpacking", "elk.aspectRatio": "2.4", "elk.spacing.nodeNode": "8", "elk.padding": GROUP_PAD };
  // Each host's ingress (nginx) is a box holding what it routes to, packed, so a host does not
  // become one tall column of fan-out. Studio is a box holding its client sites.
  const gates = new Map();   // gate id -> its box
  const boxOf = new Map();   // id -> the elk box
  const groups = [];
  for (const [id, n] of all) {
    if (n.parent || graphs.has(id)) continue;   // a host is its lane, not a box inside one
    const b = { id, ...size(n) };
    boxOf.set(id, b);
    if ([...m.behind.values()].includes(id) && [...m.behind].some(([x, g]) => g === id && all.has(x))) {
      delete b.width; delete b.height;
      Object.assign(b, { children: [], edges: [], layoutOptions: packed });
      gates.set(id, b);
      groups.push({ id, kind: "gate" });
    }
    if (id === "project:g-studio" && studioOpen) {
      const blocks = [...all.values()].some((x) => x.kind === "block");
      delete b.width; delete b.height;
      Object.assign(b, { children: [], edges: [], layoutOptions: blocks ? { ...LANE_OPTS, "elk.padding": GROUP_PAD } : packed });
      groups.push({ id, kind: "studio" });
    }
  }
  const within = new Map();   // a node inside a group box -> that box's id
  for (const [id, n] of all) {
    const b = boxOf.get(id);
    if (!b) continue;
    const gate = m.behind.get(id);
    if (gate && gates.has(gate) && !gates.has(id)) { gates.get(gate).children.push(b); within.set(id, gate); continue; }
    const g = graphs.get(m.laneOf(n));
    if (!g) continue;
    g.children.push(b);
    laneOfId.set(id, g.id);
  }
  const studioBox = studioOpen ? boxOf.get("project:g-studio") : null;
  if (studioBox) for (const [id, n] of all) if (n.parent) { studioBox.children.push({ id, ...size(n) }); within.set(id, "project:g-studio"); }
  // An edge inside one lane or one group is routed by elk; a gate's edge to what it holds is the
  // box itself; every other edge is a curve.
  const cross = [];
  for (const e of vis.edges) {
    if (within.get(e.to) === e.from || within.get(e.from) === e.to) continue;
    if (within.has(e.from) && within.get(e.from) === within.get(e.to)) boxOf.get(within.get(e.from)).edges.push({ id: e.id, sources: [e.from], targets: [e.to] });
    else if (!within.has(e.from) && !within.has(e.to) && laneOfId.has(e.from) && laneOfId.get(e.from) === laneOfId.get(e.to)) graphs.get(laneOfId.get(e.from)).edges.push({ id: e.id, sources: [e.from], targets: [e.to] });
    else cross.push(e);
  }
  const used = m.lanes.filter((l) => graphs.get(l.id).children.length);
  const done = await Promise.all(used.map((l) => elk.layout(graphs.get(l.id))));

  // Columns: each as wide as its widest lane, lanes stacked in it.
  const cols = [[], [], [], [], []];
  used.forEach((l, i) => cols[COLUMN(l.id)].push(done[i]));
  const pos = new Map(), paths = new Map();
  let x = 0, height = 0;
  for (const col of cols) {
    if (!col.length) continue;
    const w = Math.max(...col.map((g) => g.width));
    let y = 0;
    for (const g of col) {
      pos.set(g.id, { x, y, w, h: g.height });
      const walk = (b, ox, oy) => { for (const c of b.children || []) { const cx = ox + c.x, cy = oy + c.y; pos.set(c.id, { x: cx, y: cy, w: c.width, h: c.height }); walk(c, cx, cy); } };
      walk(g, x, y);
      const collect = (b) => {
        const o = b === g ? { x, y } : pos.get(b.id);
        for (const e of b.edges || []) {
          const s = e.sections && e.sections[0];
          if (s) paths.set(e.id, [s.startPoint, ...(s.bendPoints || []), s.endPoint].map((p) => [p.x + o.x, p.y + o.y]));
        }
        for (const c of b.children || []) collect(c);
      };
      collect(g);
      y += g.height + LANE_GAP;
    }
    height = Math.max(height, y - LANE_GAP);
    x += w + COL_GAP;
  }
  const curves = new Map();
  for (const e of cross) {
    const a = pos.get(e.from), b = pos.get(e.to);
    if (a && b) curves.set(e.id, curve(a, b));
  }
  return { width: x - COL_GAP, height, pos, paths, curves, studioOpen, groups };
}

/* A curve from one box's side to another's: out of the right, into the left, or round the side
   when both sit in one column. Returns the path and the point halfway along it. */
function curve(a, b) {
  let p0, p3, c1, c2;
  if (b.x >= a.x + a.w) { p0 = [a.x + a.w, a.y + a.h / 2]; p3 = [b.x, b.y + b.h / 2]; const d = Math.max(40, (p3[0] - p0[0]) / 2); c1 = [p0[0] + d, p0[1]]; c2 = [p3[0] - d, p3[1]]; }
  else if (b.x + b.w <= a.x) { p0 = [a.x, a.y + a.h / 2]; p3 = [b.x + b.w, b.y + b.h / 2]; const d = Math.max(40, (p0[0] - p3[0]) / 2); c1 = [p0[0] - d, p0[1]]; c2 = [p3[0] + d, p3[1]]; }
  else { p0 = [a.x + a.w, a.y + a.h / 2]; p3 = [b.x + b.w, b.y + b.h / 2]; const r = Math.max(a.x + a.w, b.x + b.w) + 48; c1 = [r, p0[1]]; c2 = [r, p3[1]]; }
  const at = (t) => [0, 1].map((k) => (1 - t) ** 3 * p0[k] + 3 * (1 - t) ** 2 * t * c1[k] + 3 * (1 - t) * t ** 2 * c2[k] + t ** 3 * p3[k]);
  return { d: `M${p0[0]},${p0[1]} C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${p3[0]},${p3[1]}`, mid: at(0.5) };
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

function Canvas({ m, lay, vis, focus, setFocus }) {
  const near = useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    for (const e of vis.edges) if (e.from === focus || e.to === focus) { s.add(e.from); s.add(e.to); }
    return s;
  }, [focus, vis]);
  const nodeOf = (id) => m.nodes.get(id) || m.inner.find((x) => x.id === id);
  const W = Math.ceil(lay.width), H = Math.ceil(lay.height);
  // Drawn at its natural size; the Viewport zooms and pans it.
  return html`<svg class="dg-svg" viewBox=${`0 0 ${W} ${H}`} width=${W} height=${H}
      role="img" aria-label="G-System flow diagram" onClick=${(ev) => ev.target === ev.currentTarget && setFocus(null)}>
    <defs>
      ${["plain", "drift", "down", "hot"].map((t) => html`<marker id=${`dg-arrow-${t}`} key=${t} class=${`dg-arrow dg-arrow-${t}`}
        viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,1 L9,5 L0,9 z" /></marker>`)}
    </defs>
    ${m.lanes.filter((l) => lay.pos.has(l.id)).map((l) => { const p = lay.pos.get(l.id); return html`<g class=${`dg-lane ${l.empty ? "is-empty" : ""} ${l.id.startsWith("host:") ? "is-host" : ""}`} key=${l.id}>
      <rect x=${p.x} y=${p.y} width=${p.w} height=${p.h} rx="8" />
      <text x=${p.x + 16} y=${p.y + 22} class="dg-lane-title">${l.title}</text>
      <text x=${p.x + 16} y=${p.y + 36} class="dg-lane-sub">${l.sub}</text></g>`; })}
    ${lay.groups.filter((g) => g.kind === "gate" && lay.pos.has(g.id)).map((g) => { const p = lay.pos.get(g.id); const n = m.nodes.get(g.id); const h = healthOf(n);
      const held = [...m.behind].filter(([, x]) => x === g.id).length;
      return html`<g key=${g.id} data-node=${g.id} class=${`dg-group dg-gate ${near && !near.has(g.id) ? "dim" : ""} ${focus === g.id ? "is-focus" : ""}`} onClick=${() => setFocus(g.id)}>
        <rect x=${p.x} y=${p.y} width=${p.w} height=${p.h} rx="8" />
        <circle cx=${p.x + 20} cy=${p.y + 20} r="5" fill=${HEALTH[h].color}><title>${HEALTH[h].label}</title></circle>
        <text x=${p.x + 32} y=${p.y + 24} class="dg-label">${short(n)}</text>
        <text x=${p.x + 16} y=${p.y + 42} class="dg-sub">The way in on ${n.host}: routes public names to the ${plural(held, "part", "parts")} inside</text></g>`; })}
    ${lay.studioOpen && lay.pos.has("project:g-studio") && (() => { const p = lay.pos.get("project:g-studio"); const n = m.nodes.get("project:g-studio"); const h = healthOf(n);
      const dim = near && !near.has(n.id) && ![...near].some((id) => nodeOf(id)?.parent);
      return html`<g data-node=${n.id} class=${`dg-group ${dim ? "dim" : ""} ${focus === n.id ? "is-focus" : ""}`} onClick=${(ev) => (ev.stopPropagation(), setFocus(n.id))}>
        <rect x=${p.x} y=${p.y} width=${p.w} height=${p.h} rx="8" />
        <circle cx=${p.x + 20} cy=${p.y + 20} r="5" fill=${HEALTH[h].color}><title>${HEALTH[h].label}</title></circle>
        <text x=${p.x + 32} y=${p.y + 24} class="dg-label">g-studio</text>
        <text x=${p.x + 16} y=${p.y + 42} class="dg-sub">${plural(m.inner.filter((x) => x.kind === "client").length, "client site", "client sites")} and the Studio blocks each one uses</text></g>`; })()}
    <g class="dg-edges">
      ${vis.edges.filter((e) => lay.paths.has(e.id) || lay.curves.has(e.id)).map((e) => {
        const pts = lay.paths.get(e.id), cv = lay.curves.get(e.id), t = tone(e);
        const hot = focus && (e.from === focus || e.to === focus);
        const dim = near && !hot;
        const [mx, my] = cv ? cv.mid : midpoint(pts);
        const d = cv ? cv.d : pathD(pts);
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
    ${[...lay.pos.entries()].filter(([id]) => !id.startsWith("lane:") && !id.startsWith("host:") && id !== "root" && !(id === "project:g-studio" && lay.studioOpen) && !lay.groups.some((g) => g.id === id)).map(([id, p]) => {
      const n = nodeOf(id);
      if (!n) return null;
      const h = ["client", "block", "net", "code", "empty", "provider"].includes(n.kind) ? null : healthOf(n);
      const label = n.kind === "client" || n.kind === "block" ? n.label : short(n);
      const sub = n.sub || (n.kind === "dependency" && n.criticality ? `API, ${n.criticality}` : n.kind === "service" && n.target ? `service, ${n.target}` : n.kind);
      return html`<g key=${id} data-node=${id} class=${`dg-node dg-n-${n.kind} ${h === "down" ? "is-down" : ""} ${focus === id ? "is-focus" : ""} ${near && !near.has(id) ? "dim" : ""}`}
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
    <span>${line("", "4 3")}Git, to where the code is hosted</span>
    <span>${line("", "2 3")}Declared dependency or part of</span>
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

function Focus({ id, m, edges, setFocus, jump }) {
  const n = m.nodes.get(id) || m.inner.find((x) => x.id === id);
  if (!n) return null;
  const h = n.kind === "client" || n.kind === "block" ? null : healthOf(n);
  const outs = edges.filter((e) => e.from === id), ins = edges.filter((e) => e.to === id);
  const services = n.health && n.health.services ? Object.entries(n.health.services) : [];
  return html`<section class="card dg-focus">
    <div class="card-head"><h2 class="card-title">${n.kind === "client" || n.kind === "block" ? n.label : short(n)}</h2>
      <span class="row-tight">
        ${(n.kind === "project" || n.kind === "repo") && html`<${Button} size="sm" kind="secondary" onClick=${() => jump(id)}>Open in Levels<//>`}
        <${Button} size="sm" kind="tertiary" onClick=${() => setFocus(null)}>Clear focus<//></span></div>
    <dl class="facts">
      <dt>Kind</dt><dd>${n.kind}</dd>
      ${h && html`<dt>Health</dt><dd style=${{ color: HEALTH[h].color }}>${HEALTH[h].label}${n.health && n.health.detail ? `, ${plain(n.health.detail)}` : ""}</dd>`}
      ${services.length > 0 && html`<dt>Services</dt><dd>${services.map(([s, st]) => `${s} ${st || "unknown"}`).join(", ")}</dd>`}
      ${n.powers && html`<dt>Powers</dt><dd>${plain(n.powers)}</dd>`}
      ${n.target && html`<dt>Runs as</dt><dd>${[n.target, n.runs_as].filter(Boolean).join(", ")}</dd>`}
      ${n.ports && n.ports.length > 0 && html`<dt>Ports</dt><dd class="num dg-wrap">${n.ports.join(", ")}</dd>`}
      ${n.domains && n.domains.length > 0 && html`<dt>Domains</dt><dd class="dg-wrap">${n.domains.join(", ")}</dd>`}
      ${n.surface && html`<dt>Surface</dt><dd>${n.surface}</dd>`}
      ${n.serves && n.serves.length > 0 && html`<dt>Serves</dt><dd>${n.serves.map(plain).join(", ")}</dd>`}
      ${n.kind === "host" && n.notes && html`<dt>Notes</dt><dd>${plain(n.notes)}</dd>`}
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

function Undeclared({ list, setFocus }) {
  return html`<section class="card dg-undeclared">
    <div class="card-head"><h2 class="card-title">Undeclared <span class="num muted">${list.length}</span></h2></div>
    <p class="muted small">Real flows gcore does not declare, so they are not drawn. Declare them in the repo's connects or depends to draw them.</p>
    ${list.length ? html`<div class="list">${list.map((u) => html`<div class="list-item" key=${u.key}>
        <div class="main">
          ${u.ids.length ? html`<button type="button" class="dg-link" onClick=${() => setFocus(u.ids[0])}>${u.what}</button>` : html`<span>${u.what}</span>`}
          ${u.sub && html`<span class="sub">${u.sub}</span>`}
        </div></div>`)}</div>`
      : html`<p class="muted small">Every flow named here is declared.</p>`}
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
  const [expand, setExpand] = useState(false);
  const [clientsOn, setClientsOn] = useState(true);
  const [blocksOn, setBlocksOn] = useState(false);
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState(null);
  const [reveal, setReveal] = useState(null);
  // System is the default; ?view=levels or #levels opens Levels, and switching keeps the URL in step.
  const [mode, setModeState] = useState(() => {
    const q = new URLSearchParams(location.search).get("view");
    return q === "levels" || location.hash === "#levels" ? "levels" : "system";
  });
  const setMode = (v) => {
    setModeState(v);
    const u = new URL(location.href);
    u.hash = "";
    if (v === "levels") u.searchParams.set("view", "levels"); else u.searchParams.delete("view");
    history.replaceState(null, "", u);
  };
  const [by, setBy] = useState("natural");
  const [hidden, setHidden] = useState(() => new Set());
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [lay, setLay] = useState(null);
  const [layError, setLayError] = useState(null);

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

  const m = useMemo(() => (data && data.nodes ? model(data, expand) : null), [data, expand]);
  const flagged = useMemo(() => (m ? problems(m, data) : []), [m]);
  const w = useMemo(() => (data && data.nodes ? world(data) : null), [data]);
  const toggleIn = (set) => (k) => set((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const collapseAll = () => setCollapsed(collapsed.size ? new Set() : new Set(BANDS.map((b) => b.id)));
  const f = { kinds, host, problems: onlyProblems, query, clients: clientsOn, blocks: blocksOn };
  const vis = useMemo(() => (m ? visible(m, f) : null), [m, kinds, host, onlyProblems, query, clientsOn, blocksOn]);
  // Re-lay out only when the drawn structure changes, not on every health refresh.
  const shape = vis ? [...vis.ids].sort().join(",") + "|" + vis.edges.map((e) => e.id).sort().join(",") : "";
  useEffect(() => {
    if (!vis || !vis.edges.length) { setLay(null); return; }
    let live = true;
    layout(m, vis).then((l) => live && (setLay(l), setLayError(null)), (e) => live && setLayError(e));
    return () => { live = false; };
  }, [shape]);

  // A project is the key both views share: open it in the other view, focused and centred.
  const jump = (id) => { setMode(mode === "levels" ? "system" : "levels"); setFocus(id); setReveal({ id, n: Date.now() }); };

  const toggleKind = (k) => setKinds((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const s = data && data.summary;
  const studioWhy = data && data.sources && data.sources.clients && !data.sources.clients.ok ? data.sources.clients.reason : null;
  const stats = error && !data ? "Unavailable" : s
    ? mode === "levels" ? `${s.nodes} parts, ${s.edges} links, ${flagged.length} flagged`
    : `${m ? m.lanes.filter((l) => l.id.startsWith("host:")).length : 0} hosts, ${vis ? vis.edges.length : 0} flows, ${s.live_down} down` : "Loading";
  const viewSwitch = () => seg("View", mode, (v) => { setMode(v); setFocus(null); }, [["system", "System"], ["levels", "Levels"]]);
  const seg = (name, value, set, opts) => html`<div class="g-segmented g-segmented-sm" role="radiogroup" aria-label=${name}>
    ${opts.map(([v, label]) => html`<label key=${v}><input type="radio" name=${name} value=${v} checked=${value === v} onChange=${() => set(v)} />${label}</label>`)}</div>`;

  return html`
    <div class="page-head">
      <div class="page-head-text">
        <div class="row-tight">
          <h1 class="sr-only">Diagram</h1>
          <${Badge} kind="plain" class="num">${stats}<//>
        </div>
        <p class="page-sub">${mode === "levels"
          ? "The whole G-System, one band per level, read from gcore's manifest, g-levels and every checkout. Health is live, refreshed every 30 seconds. Choose a part to draw its links."
          : "The G-System as it runs: traffic from the internet through Cloudflare to each host's edge and its services, and what flows out to the providers. Drawn from gcore's manifest, every repo's declared connects and depends, and what gcore observes in the code. Node colour is live health, refreshed every 30 seconds."}</p>
      </div>
    </div>
    ${error && !data
      ? html`<section class="card"><${ErrorState} error=${error} title="Could not load the diagram" retry=${() => setTick((t) => t + 1)} /></section>`
      : html`
      ${mode === "levels" ? html`
      <div class="dg-filters">
        <input class="input dg-q" type="search" placeholder="Search parts" aria-label="Search parts"
          value=${query} onInput=${(e) => setQuery(e.currentTarget.value.trim().toLowerCase())} />
        ${seg("Group by", by, setBy, [["natural", "Group by kind"], ["host", "Group by host"]])}
        <span class="dg-chips" role="group" aria-label="Bands">
          ${BANDS.map((b) => html`<${Button} key=${b.id} size="sm" kind=${hidden.has(b.id) ? "secondary" : "primary"} aria-pressed=${!hidden.has(b.id)} onClick=${() => toggleIn(setHidden)(b.id)}>${b.title}<//>`)}
        </span>
        <${Button} size="sm" kind=${onlyProblems ? "primary" : "secondary"} aria-pressed=${onlyProblems} onClick=${() => setOnlyProblems(!onlyProblems)}>Only problems<//>
        <${Button} size="sm" kind="tertiary" onClick=${collapseAll}>${collapsed.size ? "Expand all" : "Collapse all"}<//>
      </div>
      ${error && html`<p class="small dg-stale">The last refresh failed, so this is the previous reading. It tries again in 30 seconds.</p>`}
      <div class="dg-layout">
        <${Viewport} key="levels" tools=${viewSwitch()} fill label="The G-System by level" fitKey=${mode} reveal=${reveal}>
          ${!w ? html`<p class="muted small dg-pad">Loading the graph</p>`
            : html`<div class="dg-pad"><${Layers} data=${data} w=${w} focus=${focus} setFocus=${setFocus} collapsed=${collapsed} toggle=${toggleIn(setCollapsed)}
                filters=${{ by, query, problemsOnly: onlyProblems, hidden }} /></div>`}
        <//>
        <div class="dg-side">
          ${focus && w && html`<${Links} id=${focus} w=${w} setFocus=${setFocus} jump=${jump} />`}
          <${Flagged} list=${flagged} setFocus=${setFocus} />
        </div>
      </div>` : html`
      <div class="dg-filters">
        <input class="input dg-q" type="search" placeholder="Search nodes" aria-label="Search nodes"
          value=${query} onInput=${(e) => setQuery(e.currentTarget.value.trim().toLowerCase())} />
        <span class="select-wrap"><select class="input select" aria-label="Host" value=${host} onChange=${(e) => setHost(e.currentTarget.value)}>
          <option value="">All hosts</option>
          ${m && m.lanes.filter((l) => l.id.startsWith("host:")).map((l) => html`<option key=${l.id} value=${l.id}>${l.id.startsWith("host:") ? `Host ${l.title}` : l.title}</option>`)}
        </select></span>
        <span class="dg-chips" role="group" aria-label="Kinds">
          <${Button} size="sm" kind=${expand ? "primary" : "secondary"} aria-pressed=${expand} onClick=${() => setExpand(!expand)}>Each service<//>
          ${KINDS.map(([k, label]) => html`<${Button} key=${k} size="sm" kind=${kinds.has(k) ? "primary" : "secondary"} aria-pressed=${kinds.has(k)} onClick=${() => toggleKind(k)}>${label}<//>`)}
        </span>
        ${m && m.clients && html`<${Button} size="sm" kind=${clientsOn ? "primary" : "secondary"} aria-pressed=${clientsOn} onClick=${() => setClientsOn(!clientsOn)}>Studio clients<//>`}
        ${m && m.clients && clientsOn && html`<${Button} size="sm" kind=${blocksOn ? "primary" : "secondary"} aria-pressed=${blocksOn} onClick=${() => setBlocksOn(!blocksOn)}>Their blocks<//>`}
        <${Button} size="sm" kind=${onlyProblems ? "primary" : "secondary"} aria-pressed=${onlyProblems} onClick=${() => setOnlyProblems(!onlyProblems)}>Only problems<//>
      </div>
      ${error && html`<p class="small dg-stale">The last refresh failed, so this is the previous reading. It tries again in 30 seconds.</p>`}
      ${studioWhy && html`<p class="small muted">Studio's clients are not shown: its machine API did not answer (${plain(studioWhy)}).</p>`}
      <${Legend} />
      <div class="dg-layout">
        <${Viewport} key="system" tools=${viewSwitch()} label="The G-System as it runs" fitKey=${lay ? `${mode}|${shape}` : ""} reveal=${reveal}>
          ${!data ? html`<p class="muted small dg-pad">Loading the graph</p>`
            : layError ? html`<${ErrorState} error=${layError} title="Could not lay out the diagram" retry=${() => setTick((t) => t + 1)} />`
            : !vis || !vis.edges.length ? html`<${Empty} icon="funnel" title="Nothing matches" desc="No flows pass these filters. Clear the search or turn a kind back on." />`
            : lay ? html`<${Canvas} m=${m} lay=${lay} vis=${vis} focus=${focus} setFocus=${setFocus} />`
            : html`<p class="muted small dg-pad">Laying out</p>`}
        <//>
        <div class="dg-side">
          ${focus && m && html`<${Focus} id=${focus} m=${m} edges=${m.edges} setFocus=${setFocus} jump=${jump} />`}
          <${Flagged} list=${flagged} setFocus=${setFocus} />
          ${m && html`<${Undeclared} list=${m.undeclared} setFocus=${setFocus} />`}
        </div>
        ${m && vis && html`<${FlowList} m=${m} edges=${vis.edges} setFocus=${setFocus} />`}
      </div>`}`}`;
}

mount(Diagram);
