// Nerves: the CLAUDE.md / AGENTS.md web across all repos and how each pair sits.
// Preact owns the head, filters, legend and detail card; d3 owns the svg, as
// it did before the port. Data: ${BRAIN_API}/api/nerves.
import { html, useState, useEffect, useRef, PageHead, Badge, Button, ErrorState, mount, getJson, loadScript } from "../../core/app/boot.js";
import "./app.css";

const BRAIN = window.BRAIN_API || "/api/brain";
const D3 = "https://d3js.org/d3.v7.min.js";
const HEIGHT = 660;

// Pair state is status, so it reads through the status tokens. agents_only is
// rare enough to earn a categorical colour rather than a severity.
const STATE = {
  symlink:     { color: "var(--ok)",               label: "Symlinked" },
  copy_synced: { color: "var(--info-text)",        label: "Copied, in sync" },
  copy_drift:  { color: "var(--danger)",           label: "Copied, drifted" },
  claude_only: { color: "var(--warn)",             label: "No AGENTS.md" },
  agents_only: { color: "var(--chart-2)",          label: "No CLAUDE.md" },
  unknown:     { color: "var(--text-placeholder)", label: "Not yet resynced" },
  none:        { color: "var(--border-strong)",    label: "No nerve" },
};
const PROBLEM = new Set(["copy_drift", "claude_only", "agents_only"]);
const FILTERS = [["all", "All"], ["unpaired", "Unpaired"], ["drift", "Drifted"]];

const stateOf = (d) => STATE[d.pair] || STATE.none;
const radius = (d) => (d.type === "repo" ? 9 : d.pair === "none" ? 3.5 : 5.5);
// Repo titles are lifted from the first heading of a CLAUDE.md, so they arrive
// carrying markdown; flatten before they reach a plain slot.
const plain = (t) => (window.g && window.g.plain ? window.g.plain(t) : String(t ?? ""));

// brain/nerves/ is the brain's synced-from-GitHub copy of every repo's nerves, so
// the API walks it as ~1500 dirs under one repo: every other repo a second time,
// all pulled into a single grid cell where the charge piles them into a blob that
// swamps the web and keeps the reframe jittering. Fold it to its root dir and count
// the summary from what is drawn, so the mirror neither renders nor double-counts.
const MIRROR = { repo: "brain", root: "nerves" };
const inMirror = (id, byId) => {
  const d = byId.get(id);
  return !!d && d.repo === MIRROR.repo && (d.path || "").startsWith(MIRROR.root + "/");
};
function foldMirror({ nodes, links, summary }) {
  const byId = new Map(nodes.map((d) => [d.id, d]));
  const kept = nodes.filter((d) => !inMirror(d.id, byId)).map((d) =>
    d.repo === MIRROR.repo && d.path === MIRROR.root ? { ...d, label: "nerves (mirror)", mirror: true } : d);
  if (kept.length === nodes.length) return { nodes, links, summary };
  const keptLinks = links.filter((l) => !inMirror(l.source.id || l.source, byId) && !inMirror(l.target.id || l.target, byId));
  const counts = {};
  kept.forEach((d) => { if (d.pair && d.pair !== "none") counts[d.pair] = (counts[d.pair] || 0) + 1; });
  const nerve_dirs = Object.values(counts).reduce((a, b) => a + b, 0);
  return { nodes: kept, links: keptLinks, summary: { ...summary, ...Object.fromEntries(Object.keys(STATE).map((k) => [k, counts[k] || 0])), nerve_dirs } };
}

function matches(d, mode, query) {
  if (query && !`${d.repo}/${d.path || ""}`.toLowerCase().includes(query)) return false;
  if (mode === "unpaired") return PROBLEM.has(d.pair);
  if (mode === "drift") return d.pair === "copy_drift";
  return true;
}

/* The force graph. Built once per data load; filters only toggle classes. */
function drawGraph(svgEl, { nodes, links }, onPick) {
  const d3 = window.d3;
  const width = svgEl.clientWidth || 900;
  const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${HEIGHT}`);
  svg.selectAll("*").remove();

  const g = svg.append("g");
  let zoomedIn = false, filtering = false;
  const syncLabels = () => g.classed("show-dirs", zoomedIn || filtering);
  let userMoved = false;
  const zoom = d3.zoom().scaleExtent([0.15, 5]).on("zoom", (e) => {
    if (e.sourceEvent) userMoved = true;  // a person zoomed or panned: stop reframing under them
    g.attr("transform", e.transform);
    zoomedIn = e.transform.k > 1.15;
    syncLabels();
  });
  svg.call(zoom);

  // Every repo is its own disconnected tree, so a single centre force just
  // flings the islands off-canvas. Give each repo a grid cell and pull its
  // subtree there instead; the web then reads as a wall of small trees.
  const repos = [...new Set(nodes.map((d) => d.repo))].sort();
  const cols = Math.ceil(Math.sqrt(repos.length));
  const rows = Math.ceil(repos.length / cols);
  const cellW = width / cols, cellH = HEIGHT / rows;
  const cell = new Map(repos.map((r, i) => [r, { x: (i % cols + 0.5) * cellW, y: (Math.floor(i / cols) + 0.5) * cellH }]));
  nodes.forEach((d) => { const c = cell.get(d.repo); d.x = c.x; d.y = c.y; });

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id).distance((d) => (d.source.type === "repo" ? 34 : 22)).strength(0.9))
    .force("charge", d3.forceManyBody().strength(-38).distanceMax(180))
    .force("x", d3.forceX((d) => cell.get(d.repo).x).strength(0.35))
    .force("y", d3.forceY((d) => cell.get(d.repo).y).strength(0.35))
    .force("collide", d3.forceCollide().radius((d) => radius(d) + 4))
    // Walls at the card's edge: a node flung by the charge stops there instead of dragging the
    // framing out until the web is a speck in the middle. Room on the right for a label.
    .force("bounds", () => nodes.forEach((d) => {
      d.x = Math.max(12, Math.min(width - 72, d.x));
      d.y = Math.max(12, Math.min(HEIGHT - 12, d.y));
    }));

  const link = g.append("g").selectAll("line").data(links).enter().append("line").attr("class", "link");
  const node = g.append("g").selectAll("circle").data(nodes).enter().append("circle")
    .attr("class", "node").attr("r", radius).attr("fill", (d) => stateOf(d).color)
    .attr("stroke", "var(--bg-panel)").attr("stroke-width", 1.5)
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on("click", (_, d) => onPick(d));
  node.append("title").text((d) => `${d.type === "repo" ? `${d.label} (root)` : `${d.repo}/${d.path}`}\n${stateOf(d).label}`);

  // Only repos and nerve-carrying dirs get a label; the rest would be noise.
  const label = g.append("g").selectAll("text")
    .data(nodes.filter((d) => d.type === "repo" || d.pair !== "none")).enter().append("text")
    .attr("class", (d) => (d.type === "repo" ? "label label-repo" : "label label-dir"))
    .attr("dx", (d) => radius(d) + 3).attr("dy", 3).text((d) => d.label);

  sim.on("tick", () => {
    link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
    node.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
    label.attr("x", (d) => d.x).attr("y", (d) => d.y);
  });

  // Keep the whole web inside its card while it settles, then frame it once more at rest,
  // so nodes and labels never sit past the card's edge. Labels run right of their node.
  const fit = (animate) => {
    const xs = nodes.map((d) => d.x), ys = nodes.map((d) => d.y), pad = 24;
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad + 64;
    const y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const k = Math.min(width / (x1 - x0), HEIGHT / (y1 - y0), 1.6);
    const t = d3.zoomIdentity.translate(width / 2, HEIGHT / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    (animate ? svg.transition().duration(400) : svg).call(zoom.transform, t);
  };
  let ticks = 0;
  sim.on("tick.fit", () => { if (!userMoved && ++ticks % 10 === 1) fit(false); });
  sim.on("end.fit", () => { if (!userMoved) fit(true); });

  return {
    filter(mode, query) {
      filtering = mode !== "all" || !!query;
      syncLabels();
      const keep = new Set(nodes.filter((d) => matches(d, mode, query)).map((d) => d.id));
      node.classed("dim", (d) => !keep.has(d.id));
      label.classed("dim", (d) => !keep.has(d.id));
      link.classed("dim", (d) => !keep.has(d.source.id) && !keep.has(d.target.id));
    },
    stop: () => sim.stop(),
  };
}

function Legend({ summary }) {
  return html`<div class="nerves-legend">
    ${Object.entries(STATE)
      .filter(([k]) => k !== "none" && (k !== "unknown" || summary.unknown))
      .map(([k, s]) => html`<span class="swatch" key=${k}><span class="dot" style=${{ background: s.color }}></span>${s.label}<span class="n num">${summary[k] ?? 0}</span></span>`)}
    <span class="swatch"><span class="dot" style=${{ background: STATE.none.color }}></span>Directory with no nerve</span>
  </div>`;
}

function Detail({ d }) {
  const s = stateOf(d);
  const isRepo = d.type === "repo";
  const href = `https://github.com/Volcanex/${encodeURIComponent(d.repo)}${isRepo || !d.path ? "" : "/tree/HEAD/" + d.path}`;
  return html`<aside class="nerves-detail">
    <h3>${plain(d.label)}</h3>
    <dl>
      <dt>Repo</dt><dd>${plain(d.repo)}</dd>
      <dt>Path</dt><dd class="path">${isRepo || !d.path ? "(root)" : plain(d.path) + "/"}</dd>
      <dt>Pair</dt><dd style=${{ color: s.color }}>${s.label}</dd>
      ${isRepo && html`<dt>About</dt><dd>${plain(d.title)}</dd>
        <dt>Nerve dirs</dt><dd class="num">${d.nerve_dirs}</dd>
        <dt>Compliant</dt><dd>${d.compliant ? "Yes" : "No"}</dd>`}
    </dl>
    <a class="btn btn-sm btn-secondary" target="_blank" rel="noopener" href=${href}>Open on GitHub</a>
  </aside>`;
}

function Nerves() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const [mode, setMode] = useState("all");
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState(null);
  const svgRef = useRef(null);
  const graph = useRef(null);

  useEffect(() => {
    let live = true;
    setError(null);
    Promise.all([getJson(`${BRAIN}/api/nerves`), loadScript(D3)])
      .then(([d]) => live && setData(foldMirror(d)), (e) => live && setError(e));
    return () => { live = false; };
  }, [tick]);

  useEffect(() => {
    if (!data || !svgRef.current) return;
    graph.current = drawGraph(svgRef.current, data, setPicked);
    return () => graph.current && graph.current.stop();
  }, [data]);

  useEffect(() => { graph.current && graph.current.filter(mode, query); }, [data, mode, query]);

  const summary = data && data.summary;
  const problems = summary ? (summary.copy_drift || 0) + (summary.claude_only || 0) + (summary.agents_only || 0) : 0;
  const stats = error ? "Unavailable" : summary
    ? `${summary.repos} repos, ${summary.nerve_dirs} nerve dirs, ${problems} unpaired` : "Loading";

  return html`
    <div class="page-head">
      <div class="page-head-text">
        <div class="row-tight">
          <h1 class="sr-only">Nerves</h1>
          <${Badge} kind="plain">Layer 3<//>
          <${Badge} kind="plain" class="num">${stats}<//>
        </div>
        <p class="page-sub">Every directory carrying a CLAUDE.md or an AGENTS.md, nested at full depth. Node colour is how the pair sits.</p>
      </div>
      <div class="page-actions">
        <input class="input nerves-q" type="search" placeholder="Filter repo or path" aria-label="Filter repo or path"
          value=${query} onInput=${(e) => setQuery(e.currentTarget.value.trim().toLowerCase())} />
        <span class="nerves-filters" role="group" aria-label="Pair filter">
          ${FILTERS.map(([k, label]) => html`<${Button} key=${k} size="sm" kind=${mode === k ? "primary" : "secondary"}
            aria-pressed=${mode === k} onClick=${() => setMode(k)}>${label}<//>`)}
        </span>
      </div>
    </div>
    ${error
      ? html`<section class="card"><${ErrorState} error=${error} title="Could not load the web" retry=${() => setTick((t) => t + 1)} /></section>`
      : html`
        ${summary && html`<${Legend} summary=${summary} />`}
        <div class="card nerves-graph">
          <svg ref=${svgRef} width="100%" height=${HEIGHT} role="img" aria-label="Nerves web"></svg>
          ${picked && html`<${Detail} d=${picked} />`}
        </div>`}`;
}

mount(Nerves);
