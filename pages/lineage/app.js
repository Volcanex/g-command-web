// Lineage: starter and design language provenance across repos, from
// [tool.g-core] (or [tool.gcore]) in each pyproject.toml. Preact owns the head
// and legend; d3 owns the svg, as it did before the port.
// Data: ${BRAIN_API}/api/lineage.
import { html, useState, useEffect, useRef, Badge, ErrorState, mount, getJson, loadScript } from "../../core/app/boot.js";
import "./app.css";

const BRAIN = window.BRAIN_API || "/api/brain";
const D3 = "https://d3js.org/d3.v7.min.js";
const HEIGHT = 560;

/* Node and edge colours come from the derived chart palette so both themes
   clear contrast. */
const REPO = "var(--chart-2)";
const SOURCE = "var(--chart-1)";
const DESIGN = "var(--chart-4)";
const LEGEND = [["Repo", REPO], ["Starter or design", SOURCE], ["Starter edge", SOURCE], ["Design edge", DESIGN]];

const nodeColor = (d) => (d.type === "source" ? SOURCE : REPO);
const nodeR = (d) => (d.type === "source" ? 12 : 8);

function drawGraph(svgEl, { nodes, links }) {
  const d3 = window.d3;
  const width = svgEl.clientWidth || 900;
  const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${HEIGHT}`);
  svg.selectAll("*").remove();

  const g = svg.append("g");
  let userMoved = false;
  const zoom = d3.zoom().scaleExtent([0.3, 4]).on("zoom", (e) => {
    if (e.sourceEvent) userMoved = true;  // a person zoomed or panned: stop reframing under them
    g.attr("transform", e.transform);
  });
  svg.call(zoom);

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id).distance(100).strength(0.8))
    .force("charge", d3.forceManyBody().strength(-200))
    .force("center", d3.forceCenter(width / 2, HEIGHT / 2))
    .force("collide", d3.forceCollide().radius((d) => nodeR(d) + 8))
    // Walls at the card's edge, with room on the right for a label, so nothing drifts out of view.
    .force("bounds", () => nodes.forEach((d) => {
      d.x = Math.max(16, Math.min(width - 140, d.x));
      d.y = Math.max(16, Math.min(HEIGHT - 16, d.y));
    }));

  const link = g.append("g").selectAll("line").data(links).enter().append("line")
    .attr("class", (d) => `link-${d.rel}`);

  const node = g.append("g").selectAll("circle").data(nodes).enter().append("circle")
    .attr("class", "node").attr("r", nodeR).attr("fill", nodeColor)
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on("click", (_, d) => {
      if (d.type === "repo") window.open(`https://github.com/Volcanex/${d.label}`, "_blank");
    });
  node.append("title").text((d) => (d.type === "source" ? d.label : `${d.label}\nclick to open GitHub`));

  const label = g.append("g").selectAll("text").data(nodes).enter().append("text")
    .attr("class", "label").attr("dx", (d) => nodeR(d) + 3).attr("dy", 3).text((d) => d.label);

  sim.on("tick", () => {
    link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
    node.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
    label.attr("x", (d) => d.x).attr("y", (d) => d.y);
  });

  // Keep every node and label inside the card while it settles, then frame it at rest.
  // A label runs right of its node, so the right edge gets the room of the longest one.
  const longest = Math.max(0, ...nodes.map((d) => String(d.label || "").length)) * 6 + 16;
  const fit = (animate) => {
    const xs = nodes.map((d) => d.x), ys = nodes.map((d) => d.y), pad = 24;
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + longest;
    const y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const k = Math.min(width / (x1 - x0), HEIGHT / (y1 - y0), 1.6);
    const t = d3.zoomIdentity.translate(width / 2, HEIGHT / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    (animate ? svg.transition().duration(400) : svg).call(zoom.transform, t);
  };
  let ticks = 0;
  sim.on("tick.fit", () => { if (!userMoved && ++ticks % 10 === 1) fit(false); });
  sim.on("end.fit", () => { if (!userMoved) fit(true); });
  return { stop: () => sim.stop() };
}

function Lineage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const svgRef = useRef(null);

  useEffect(() => {
    let live = true;
    setError(null);
    Promise.all([getJson(`${BRAIN}/api/lineage`), loadScript(D3)])
      .then(([d]) => live && setData(d), (e) => live && setError(e));
    return () => { live = false; };
  }, [tick]);

  useEffect(() => {
    if (!data || !svgRef.current) return;
    const graph = drawGraph(svgRef.current, data);
    return () => graph.stop();
  }, [data]);

  const stats = error ? "Unavailable" : data
    ? `${data.nodes.filter((n) => n.type === "repo").length} repos, ${data.nodes.filter((n) => n.type === "source").length} sources, ${data.links.length} edges`
    : "Loading";

  return html`
    <div class="page-head">
      <div class="page-head-text">
        <div class="row-tight">
          <h1 class="sr-only">Lineage</h1>
          <${Badge} kind="plain">Layer 4<//>
          <${Badge} kind="plain" class="num">${stats}<//>
        </div>
        <p class="page-sub">Starter and design language provenance from <code>[tool.g-core]</code> (or <code>[tool.gcore]</code>) in each repo's <code>pyproject.toml</code>.</p>
      </div>
      <div class="page-actions">
        <span class="lineage-legend">
          ${LEGEND.map(([label, color]) => html`<span class="swatch" key=${label}><span class="dot" style=${{ background: color }}></span>${label}</span>`)}
        </span>
      </div>
    </div>
    ${error
      ? html`<section class="card"><${ErrorState} error=${error} title="Could not load the lineage" retry=${() => setTick((t) => t + 1)} /></section>`
      : html`<div class="card lineage-graph">
          <svg ref=${svgRef} width="100%" height=${HEIGHT} role="img" aria-label="Lineage graph"></svg>
        </div>`}`;
}

mount(Lineage);
