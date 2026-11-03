// Graph: the brain's wikilinks in 3D. Preact owns the head, legend and the
// error states; 3d-force-graph (the same CDN build as before the port) owns the
// canvas, wrapped in one component. Data: ${BRAIN_API}/api/graph.
import { html, useState, useEffect, useRef, Badge, ErrorState, mount, getJson, loadScript } from "../../core/app/boot.js";
import "./app.css";

const BRAIN = window.BRAIN_API || "/api/brain";
const LIB = "https://cdn.jsdelivr.net/npm/3d-force-graph@1.79.0/dist/3d-force-graph.min.js";
// The UMD build reads process.env.NODE_ENV, which browsers lack.
window.process = window.process || { env: { NODE_ENV: "production" } };

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const hasWebgl = () => {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl") || c.getContext("experimental-webgl")); }
  catch (e) { return false; }
};

/* WebGL needs concrete colours, not CSS vars. The theme's tokens are oklch,
   which the scene's colour parser rejects, so paint each into a 1px canvas
   and read it back as rgb; again on a theme flip. */
const FALLBACK = ["#2f6fe0", "#c2410c", "#4d8b3f", "#b7791f", "#7c4dbd", "#2a8a8a"];
const px = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
function resolve(name, fb) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!v) return fb;
  px.clearRect(0, 0, 1, 1);
  px.fillStyle = fb;
  px.fillStyle = v;
  px.fillRect(0, 0, 1, 1);
  const [r, g, b] = px.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}
const palette = () => [1, 2, 3, 4, 5, 6].map((i) => resolve(`--chart-${i}`, FALLBACK[i - 1]));

/* The 3D scene, built once per data load. Returns a teardown. */
function drawScene(el, { nodes, links }, slot) {
  // Size by link degree, counted before the library swaps ids for objects.
  const degree = {};
  links.forEach((l) => {
    degree[l.source] = (degree[l.source] || 0) + 1;
    degree[l.target] = (degree[l.target] || 0) + 1;
  });
  nodes.forEach((n) => { n.val = degree[n.id] || 1; });

  let colors = palette();
  let linkGrey = resolve("--text-placeholder", "#696e77");
  const label = (n) => `${window.g.plain(n.title)}, ${n.kind}${n.status === "broken" ? ", broken" : ""}`;

  const graph = window.ForceGraph3D()(el)
    .width(el.clientWidth)
    .height(el.clientHeight)
    .backgroundColor(resolve("--surface-1", "#111113"))
    .showNavInfo(false)
    .nodeRelSize(4)
    .nodeLabel(label)
    .nodeColor((n) => colors[slot(n.kind)])
    .linkColor(() => linkGrey)
    .linkOpacity(0.35)
    .onNodeClick((n) => { window.location.href = `/note/${n.id}`; })
    .graphData({ nodes, links });

  try { graph.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); } catch (e) {}

  graph.controls().autoRotate = true;
  graph.controls().autoRotateSpeed = 0.5;
  el.addEventListener("pointerdown", () => { graph.controls().autoRotate = false; }, { once: true });

  const ro = new ResizeObserver(() => graph.width(el.clientWidth).height(el.clientHeight));
  ro.observe(el);
  const mo = new MutationObserver(() => {
    colors = palette();
    linkGrey = resolve("--text-placeholder", "#696e77");
    graph.backgroundColor(resolve("--surface-1", "#111113"))
      .nodeColor((n) => colors[slot(n.kind)])
      .linkColor(() => linkGrey);
  });
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  return () => { ro.disconnect(); mo.disconnect(); try { graph._destructor(); } catch (e) {} };
}

function ForceGraph({ data, slot }) {
  const ref = useRef(null);
  useEffect(() => (ref.current ? drawScene(ref.current, data, slot) : undefined), [data]);
  return html`<div ref=${ref} class="graph-canvas" role="img" aria-label="Wikilink graph"></div>`;
}

function Graph({ embedded = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const webgl = useRef(hasWebgl()).current;

  useEffect(() => {
    if (!webgl) return;
    let live = true;
    setError(null);
    Promise.all([getJson(`${BRAIN}/api/graph`), loadScript(LIB)]).then(([d]) => {
      if (!live) return;
      if (typeof window.ForceGraph3D !== "function") throw new Error("The 3D graph library did not load.");
      setData(d);
    }).catch((e) => live && setError(e));
    return () => { live = false; };
  }, [tick]);

  const kinds = data ? Array.from(new Set(data.nodes.map((n) => n.kind))).sort() : [];
  const slot = (kind) => kinds.indexOf(kind) % 6;
  const stats = !webgl || error ? "Unavailable" : data ? `${data.nodes.length} nodes, ${data.links.length} links` : "Loading";

  let body;
  if (!webgl) body = html`<p class="graph-msg">This browser has no WebGL, so the 3D graph cannot draw.</p>`;
  else if (error) body = html`<${ErrorState} error=${error} title="Could not load the graph" retry=${() => setTick((t) => t + 1)} />`;
  else if (data) body = html`<${ForceGraph} data=${data} slot=${slot} />`;
  else body = html`<div class="graph-canvas"></div>`;

  const legend = html`<span class="graph-legend">
    ${kinds.map((k) => html`<span class="swatch" key=${k}><span class="dot" style=${{ background: `var(--chart-${slot(k) + 1})` }}></span>${cap(k)}</span>`)}
  </span>`;
  if (embedded) {
    return html`<section class="card graph-wrap graph-panel" aria-label="Graph">
      <div class="graph-panel-head">
        <a class="card-title" href="/graph">Graph</a>
        <${Badge} kind="plain" class="num">${stats}<//>
        <span class="grow"></span>
        ${legend}
      </div>
      ${body}
    </section>`;
  }

  return html`
    <div class="page-head">
      <div class="page-head-text">
        <div class="row-tight">
          <h1 class="sr-only">Graph</h1>
          <${Badge} kind="plain" class="num">${stats}<//>
        </div>
        <p class="page-sub">Drag to orbit, scroll to zoom, hover for titles, click to open.</p>
      </div>
      <div class="page-actions">
        <span class="graph-legend">
          ${kinds.map((k) => html`<span class="swatch" key=${k}><span class="dot" style=${{ background: `var(--chart-${slot(k) + 1})` }}></span>${cap(k)}</span>`)}
        </span>
      </div>
    </div>
    <div class="card graph-wrap">${body}</div>`;
}

// On /graph it is the page; on Brain it is a panel in the slot Brain leaves.
if (document.querySelector("[data-graph-panel]")) mount(Graph, { embedded: true }, "[data-graph-panel]");
else mount(Graph);
