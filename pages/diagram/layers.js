// Layers: the whole G-System as bands, one per g-level plus what runs, where, and outside.
// Every node gcore's graph returns lands in exactly one band; what no band claims lands in
// Unknown, so the page shows what it cannot place instead of dropping it. Groups inside a band
// collapse, and focusing a part draws its links across the bands.
import { html, useState, useRef, Badge, Button } from "../../core/app/boot.js";
import { useMemo, useLayoutEffect } from "preact/hooks";

const plain = (t) => (window.g && window.g.plain ? window.g.plain(t) : String(t ?? ""));

export const BANDS = [
  { id: "L3", title: "L3 charters", sub: "Hold the gates and say where they fire", kinds: ["charter"] },
  { id: "L2", title: "L2 gates", sub: "Each checks one principle for one class of flaw", kinds: ["gate"] },
  { id: "L1", title: "L1 agents", sub: "Skills, subagents and hooks the agents run with", kinds: ["skill", "agent", "hook"] },
  { id: "L0", title: "L0 code", sub: "The system's own repos, then every project", kinds: ["repo", "project"] },
  { id: "run", title: "Running", sub: "Services, the domains that reach them and Studio's clients", kinds: ["service", "domain", "client"] },
  { id: "where", title: "Hosts and workspaces", sub: "The machines, and the Mac workspaces that face them", kinds: ["host", "workspace"] },
  { id: "outside", title: "Outside", sub: "Providers and the APIs the projects depend on", kinds: ["provider", "dependency"] },
  { id: "unknown", title: "Unknown", sub: "Named somewhere, not in the manifest or any checkout", kinds: ["unknown"] },
];
const BAND_OF = Object.fromEntries(BANDS.flatMap((b) => b.kinds.map((k) => [k, b.id])));

// One phrase per edge kind, read from the side it starts on.
const WORDS = {
  runs_on: ["runs on", "runs"], has_service: ["has service", "is a service of"], routes: ["routes to", "is reached by"],
  depends: ["depends on", "is depended on by"], connects: ["connects to", "is connected from"],
  works_on: ["works on", "is worked on in"], hosted_by: ["is hosted by", "hosts"], part_of: ["is part of", "includes"],
  provides: ["provides", "is provided by"], checks_with: ["checks with", "is the skill for"],
  holds: ["holds", "is held by"], extends: ["extends", "is extended by"], governs: ["governs", "is governed by"],
  uses: ["uses", "is used by"],
};
const LAYER = { map: "The map", knowledge: "Knowledge", environment: "Environment", design: "Design",
  command: "Command", starter: "Starters" };
const KIND_WORD = { skill: "Skills", agent: "Subagents", hook: "Hooks", service: "Services", domain: "Domains",
  client: "Studio clients", host: "Hosts", workspace: "Workspaces", provider: "Providers", dependency: "APIs",
  charter: "Charters", unknown: "Unknown" };

const stateOf = (n) => {
  const s = n && n.health && n.health.state;
  return s === "up" ? "ok" : s === "down" ? "down" : s === "warn" || s === "paused" ? "warn" : "unknown";
};
const DOT = { ok: "var(--ok)", warn: "var(--warn)", down: "var(--danger)", unknown: "var(--text-placeholder)" };
const HEALTHFUL = new Set(["service", "project", "repo", "host", "dependency", "workspace"]);
const RANK = { down: 3, warn: 2, ok: 1, unknown: 0 };

export function chipLabel(n) {
  if (n.kind === "gate") return n.name.replace(/^(correct|design)\./, "");
  if (n.kind === "workspace") return plain(n.label);
  if (["service", "domain", "dependency", "host", "provider", "charter"].includes(n.kind)) return n.kind === "provider" ? plain(n.label) : n.name;
  return n.name;
}

/* All parts and links, from the payload. Studio clients come in as nodes of their own. */
export function world(data) {
  const nodes = new Map(data.nodes.map((n) => [n.id, n]));
  const edges = data.edges.map((e, i) => ({ ...e, key: `${e.kind}:${e.from}>${e.to}:${e.via || ""}:${i}` }));
  const studio = nodes.get("project:g-studio");
  if (studio && Array.isArray(studio.clients)) for (const p of studio.clients) {
    if (p.archived) continue;
    const id = `client:${p.id}`;
    nodes.set(id, { id, kind: "client", name: p.id, label: plain(p.name || p.id), health: null });
    edges.push({ kind: "uses", from: id, to: studio.id, key: `uses:${id}` });
  }
  const flagged = new Map();
  for (const p of data.problems || []) if (p.node) (flagged.get(p.node) || flagged.set(p.node, []).get(p.node)).push(plain(p.problem));
  for (const n of nodes.values()) if (n.duplicate_of && !flagged.has(n.id)) flagged.set(n.id, [`Same repo as ${n.duplicate_of}`]);
  // where each part lives, for grouping by host
  const hostOf = new Map();
  for (const e of edges) if (e.kind === "runs_on" || e.kind === "works_on") hostOf.set(e.from, e.to);
  for (const e of edges) if (e.kind === "has_service" && hostOf.get(e.to) && !hostOf.has(e.from)) hostOf.set(e.from, hostOf.get(e.to));
  for (const e of edges) if (e.kind === "routes" && hostOf.get(e.to)) hostOf.set(e.from, hostOf.get(e.to));
  for (const n of nodes.values()) if (n.host && nodes.has(`host:${n.host}`) && !hostOf.has(n.id)) hostOf.set(n.id, `host:${n.host}`);
  for (const e of edges) if (e.kind === "provides" && hostOf.get(e.from) && !hostOf.has(e.to)) hostOf.set(e.to, hostOf.get(e.from));
  const providerOf = new Map();
  for (const e of edges) if (e.kind === "provides") providerOf.set(e.to, e.from);
  return { nodes, edges, flagged, hostOf, providerOf };
}

function groupOf(w, n, by) {
  if (by === "host") {
    if (n.kind === "host") return ["host", "Hosts"];
    const h = w.hostOf.get(n.id);
    return h ? [h, `On ${h.replace(/^host:/, "")}`] : ["nowhere", "No host"];
  }
  switch (n.kind) {
    case "repo": return [`layer:${n.layer || "other"}`, `System: ${(LAYER[n.layer] || "other").toLowerCase()}`];
    case "project": { const h = w.hostOf.get(n.id); return h ? [h, `Projects on ${h.replace(/^host:/, "")}`] : ["code", "Projects with no host"]; }
    case "gate": { const area = n.name.split(".")[1] || "other"; return [`area:${area}`, area[0].toUpperCase() + area.slice(1)]; }
    case "skill": case "agent": case "hook": {
      const from = w.providerOf.get(n.id); const owner = from && w.nodes.get(from);
      return [`${n.kind}:${from}`, `${KIND_WORD[n.kind]} from ${owner ? owner.name : "nowhere"}`];
    }
    case "service": case "domain": { const h = w.hostOf.get(n.id); return [`${n.kind}:${h}`, `${KIND_WORD[n.kind]} on ${h ? h.replace(/^host:/, "") : "no host"}`]; }
    default: return [n.kind, KIND_WORD[n.kind] || n.kind];
  }
}

/* The bands, each a list of groups, each a list of nodes, after the filters. */
export function bands(w, { by, query, problemsOnly, hidden }) {
  const q = query && query.toLowerCase();
  const out = BANDS.map((b) => ({ ...b, groups: new Map(), count: 0 }));
  const idx = Object.fromEntries(out.map((b, i) => [b.id, i]));
  for (const n of w.nodes.values()) {
    const band = out[idx[BAND_OF[n.kind] || "unknown"]];
    if (hidden.has(band.id)) continue;
    if (problemsOnly && !w.flagged.has(n.id) && n.kind !== "unknown" && !["down", "warn"].includes(stateOf(n))) continue;
    if (q && !`${n.name} ${n.label || ""}`.toLowerCase().includes(q)) continue;
    const [gid, title] = groupOf(w, n, by);
    const g = band.groups.get(gid) || band.groups.set(gid, { id: `${band.id}/${gid}`, title, nodes: [] }).get(gid);
    g.nodes.push(n);
    band.count++;
  }
  for (const b of out) {
    b.groups = [...b.groups.values()].sort((a, c) => a.title.localeCompare(c.title));
    for (const g of b.groups) g.nodes.sort((a, c) => chipLabel(a).localeCompare(chipLabel(c)));
  }
  return out;
}

function Chip({ n, w, focus, near, setFocus, byArea }) {
  const s = HEALTHFUL.has(n.kind) ? stateOf(n) : null;
  const flags = w.flagged.get(n.id);
  const tip = [`${plain(n.label || n.name)} (${n.kind})`, ...(flags || [])].join("\n");
  return html`<button type="button" data-node=${n.id} title=${tip}
      class=${`dg-chip dg-c-${n.kind} ${focus === n.id ? "is-focus" : ""} ${near && !near.has(n.id) ? "dim" : ""} ${flags || n.kind === "unknown" ? "is-flagged" : ""} ${n.duplicate_of ? "is-dup" : ""}`}
      onClick=${() => setFocus(focus === n.id ? null : n.id)}>
    ${s && html`<i class="dg-dot" style=${{ background: DOT[s] }}></i>`}
    <span>${byArea && n.kind === "gate" ? n.name.split(".").slice(2).join(".") : chipLabel(n)}</span>
    ${(flags || n.kind === "unknown") && html`<b class="dg-chip-flag" aria-label="Flagged">!</b>`}
  </button>`;
}

export function Layers({ data, w, focus, setFocus, filters, collapsed, toggle }) {
  const view = useMemo(() => bands(w, filters), [w, filters.by, filters.query, filters.problemsOnly, filters.hidden]);
  const links = useMemo(() => (focus ? w.edges.filter((e) => e.from === focus || e.to === focus) : []), [w, focus]);
  const near = useMemo(() => (focus ? new Set([focus, ...links.flatMap((e) => [e.from, e.to])]) : null), [focus, links]);
  const box = useRef(null);
  const [lines, setLines] = useState([]);

  // The focused part's links as lines across the bands. A neighbour in a collapsed group is
  // drawn to that group's header.
  useLayoutEffect(() => {
    const root = box.current;
    if (!root || !focus) { setLines([]); return; }
    const measure = () => {
      const o = root.getBoundingClientRect();
      const at = (id) => {
        const el = root.querySelector(`[data-node="${CSS.escape(id)}"]`) || root.querySelector(`[data-holds~="${CSS.escape(id)}"]`);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.left - o.left + r.width / 2, y: r.top - o.top + r.height / 2 };
      };
      const a = at(focus);
      if (!a) { setLines([]); return; }
      setLines(links.map((e) => {
        const b = at(e.from === focus ? e.to : e.from);
        return b && (b.x !== a.x || b.y !== a.y) ? { key: e.key, a, b, out: e.from === focus } : null;
      }).filter(Boolean));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    return () => ro.disconnect();
  }, [focus, links, view, collapsed]);

  const levels = data.levels || {};
  return html`<div class="dg-bands" ref=${box}>
    <svg class="dg-wires" aria-hidden="true">
      ${lines.map((l) => { const my = (l.a.y + l.b.y) / 2;
        return html`<path key=${l.key} class=${`dg-wire ${l.out ? "out" : "in"}`} d=${`M${l.a.x},${l.a.y} C${l.a.x},${my} ${l.b.x},${my} ${l.b.x},${l.b.y}`} />`; })}
    </svg>
    ${view.filter((b) => b.count || b.id !== "unknown").map((b) => {
      const shut = collapsed.has(b.id);
      return html`<section class="dg-band" key=${b.id} aria-label=${b.title}>
        <button type="button" class="dg-band-head g-tree-row" aria-expanded=${!shut} onClick=${() => toggle(b.id)}>
          <span class="g-tree-caret"></span>
          <span class="dg-band-title">${b.title}</span>
          <span class="num muted small">${b.count}</span>
          <span class="muted small dg-band-sub">${levels[b.id] ? `From ${levels[b.id]}` : b.sub}</span>
        </button>
        ${!shut && html`<div class="dg-groups">
          ${b.groups.length ? b.groups.map((g) => {
            const gshut = collapsed.has(g.id);
            const worst = g.nodes.map(stateOf).reduce((x, y) => (RANK[y] > RANK[x] ? y : x), "unknown");
            const nflag = g.nodes.filter((n) => w.flagged.has(n.id) || n.kind === "unknown").length;
            return html`<div class=${`dg-group-box ${near && !g.nodes.some((n) => near.has(n.id)) ? "dim" : ""}`} key=${g.id}>
              <button type="button" class="dg-group-head" aria-expanded=${!gshut} onClick=${() => toggle(g.id)}
                  data-holds=${gshut ? g.nodes.map((n) => n.id).join(" ") : undefined}>
                <span class="g-tree-caret"></span>
                ${gshut && g.nodes.some((n) => HEALTHFUL.has(n.kind)) && html`<i class="dg-dot" style=${{ background: DOT[worst] }}></i>`}
                <span>${g.title}</span>
                <span class="num muted">${g.nodes.length}</span>
                ${nflag > 0 && html`<${Badge} kind="warn" class="num">${nflag} flagged<//>`}
              </button>
              ${!gshut && html`<div class="dg-chipset">${g.nodes.map((n) => html`<${Chip} key=${n.id} n=${n} w=${w} focus=${focus} near=${near} setFocus=${setFocus} byArea=${filters.by === "natural"} />`)}</div>`}
            </div>`;
          }) : html`<p class="muted small">Nothing here passes the filters.</p>`}
        </div>`}
      </section>`;
    })}
  </div>`;
}

/* The focused part, with every link it has, in words. */
export function Links({ id, w, setFocus }) {
  const n = w.nodes.get(id);
  if (!n) return null;
  const links = w.edges.filter((e) => e.from === id || e.to === id);
  const by = new Map();
  for (const e of links) {
    const out = e.from === id;
    const word = (WORDS[e.kind] || [e.kind, `${e.kind} from`])[out ? 0 : 1];
    (by.get(word) || by.set(word, []).get(word)).push({ e, other: out ? e.to : e.from });
  }
  const facts = [
    ["Kind", n.kind], ["Level", n.level], ["Health", n.health && n.health.state ? `${n.health.state}${n.health.detail ? `, ${plain(n.health.detail)}` : ""}` : null],
    ["About", n.label && n.label !== n.name ? plain(n.label) : null], ["Role", n.role], ["Layer", n.layer && LAYER[n.layer]],
    ["Scope", n.scope], ["Sensor", n.sensor], ["Trigger", n.trigger], ["Events", n.events && n.events.join(", ")],
    ["Serves", n.serves && n.serves.join(", ")], ["Path", n.path], ["Same as", n.duplicate_of],
  ].filter(([, v]) => v);
  const flags = w.flagged.get(id) || [];
  return html`<section class="card dg-focus">
    <div class="card-head"><h2 class="card-title">${chipLabel(n)}</h2>
      <${Button} size="sm" kind="tertiary" onClick=${() => setFocus(null)}>Clear focus<//></div>
    <dl class="facts">${facts.map(([k, v]) => html`<dt key=${k}>${k}</dt><dd class="dg-wrap">${v}</dd>`)}</dl>
    ${flags.map((f, i) => html`<p class="small dg-stale" key=${i}>${f}</p>`)}
    ${n.principles && n.principles.length > 0 && html`<h3 class="dg-h3">Principles</h3>
      <div class="list">${n.principles.map((p, i) => html`<div class="list-item" key=${i}><div class="main"><span class="sub">${plain(p)}</span></div></div>`)}</div>`}
    ${[...by.entries()].map(([word, rows]) => html`<div key=${word}>
      <h3 class="dg-h3">${word[0].toUpperCase() + word.slice(1)} <span class="num muted">${rows.length}</span></h3>
      <div class="list">${rows.map(({ e, other }) => { const o = w.nodes.get(other);
        return html`<div class="list-item" key=${e.key}><div class="main">
          <button type="button" class="dg-link" onClick=${() => setFocus(other)}>${o ? chipLabel(o) : other}</button>
          ${e.flow && e.flow.length > 0 && html`<span class="sub">${[].concat(e.flow).map(plain).join(", ")}</span>`}</div>
          <div class="end">${e.blocking && html`<${Badge} kind="warn">Blocking<//>`}${e.via && html`<${Badge} kind="plain">${e.via}<//>`}</div></div>`; })}</div>
    </div>`)}
    ${!links.length && html`<p class="muted small">Nothing links here.</p>`}
  </section>`;
}
