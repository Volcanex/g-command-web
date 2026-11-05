// Showcase: what the g-content recipes have made, each piece at full size with
// how it was made and what the judge said, Gabriel's 1 to 10 rating, and where
// he and the judge disagree. Everything comes through /api/showcase (api.py),
// which holds g-content's token. URLs in g-content's answers are its own paths:
// `px` turns them into the proxy's, the one place that does.
import {
  html, useState, useEffect, useRef, useCallback, PageHead, Badge, Button, Empty, ErrorState,
  SkeletonRows, toastOk, toast, escapeHtml, mount,
} from "../../core/app/boot.js";
import "./app.css";

const API = "/api/showcase";
const px = (u) => (typeof u === "string" && u.startsWith("/api/") ? API + u.slice(4) : u);
const fileUrl = (id, name) => `${API}/pieces/${id}/files/${encodeURIComponent(name)}`;

const MODES = [["pieces", "Pieces"], ["recipes", "Recipes"], ["disagree", "Disagreements"]];
const STATUSES = [["all", "All"], ["candidate", "Candidates"], ["unjudged", "Unjudged"], ["rejected", "Rejected"]];
const STATUS_BADGE = { candidate: ["ok", "Candidate"], rejected: ["danger", "Rejected"], unjudged: ["plain", "Unjudged"] };
const GATE_BADGE = { met: "ok", attempted: "warn", waived: "info", impossible: "danger" };

/* An error the page can talk about: {code, message}. getJson in boot.js flattens
   g-content's {error: {...}} to a string, so this page reads its own answers. */
async function call(url, opts) {
  let r;
  try {
    r = await fetch(url, { credentials: "same-origin", ...opts });
  } catch {
    throw { code: "offline", message: "Command is not answering." };
  }
  let body = null;
  try { body = await r.json(); } catch { /* a non-JSON answer is handled below */ }
  if (body && body.error && typeof body.error === "object") throw body.error;
  if (!r.ok || (body && typeof body.error === "string")) {
    const msg = (body && (typeof body.error === "string" ? body.error : body.detail)) || `Command answered ${r.status}.`;
    throw { code: r.status === 404 ? "not_found" : "http", message: typeof msg === "string" ? msg : JSON.stringify(msg) };
  }
  return body;
}

function useLoad(url) {
  const [state, setState] = useState({ data: undefined, error: null });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    if (!url) return;
    let live = true;
    setState((s) => ({ data: s.url === url ? s.data : undefined, error: null, url }));
    call(url).then((data) => live && setState({ data, error: null, url }),
      (error) => live && setState({ data: undefined, error, url }));
    return () => { live = false; };
  }, [url, tick]);
  return { ...state, reload, setData: (data) => setState((s) => ({ ...s, data })) };
}

/* URL state: ?view, ?collection, ?recipe, ?status, ?piece. Back and forward work. */
function useQuery() {
  const read = () => Object.fromEntries(new URLSearchParams(location.search));
  const [q, setQ] = useState(read);
  useEffect(() => {
    const on = () => setQ(read());
    addEventListener("popstate", on);
    return () => removeEventListener("popstate", on);
  }, []);
  const go = useCallback((patch, replace = false) => {
    const next = { ...read(), ...patch };
    for (const k of Object.keys(next)) if (next[k] == null || next[k] === "" || next[k] === "all") delete next[k];
    const s = new URLSearchParams(next).toString();
    history[replace ? "replaceState" : "pushState"](null, "", location.pathname + (s ? "?" + s : ""));
    setQ(next);
    if (!replace) scrollTo(0, 0);
  }, []);
  return [q, go];
}

const sameError = (e) => (e && e.code === "unreachable" || e && e.code === "no_token" || e && e.code === "rejected");
function Trouble({ error, retry }) {
  const title = { unreachable: "Can't reach g-content", no_token: "g-content is not set up here", rejected: "g-content refused Command" }[error.code];
  return html`<div class="card sc-trouble"><${ErrorState} error=${error} retry=${retry} title=${title} /></div>`;
}

/* --------------------------------------------------------------- small parts */

const score = (v) => (v == null ? html`<span class="sc-none">not yet</span>` : html`<span class="num">${v}</span>`);

function Scores({ judge, owner }) {
  return html`<dl class="sc-scores">
    <div><dt>Judge</dt><dd>${score(judge)}</dd></div>
    <div><dt>You</dt><dd>${score(owner)}</dd></div>
  </dl>`;
}

function Status({ status }) {
  const [kind, label] = STATUS_BADGE[status] || ["plain", status || "Unknown"];
  return html`<${Badge} kind=${kind}>${label}<//>`;
}

/* A preview keeps its slot before it loads, and says so when the file is gone. */
function Preview({ src, alt, format }) {
  const [broken, setBroken] = useState(false);
  const icon = format === "model" ? "cube" : format === "video" ? "film-strip" : format === "html" ? "browser" : "image";
  return html`<div class="sc-preview">
    ${src && !broken
      ? html`<img src=${px(src)} alt=${alt} loading="lazy" decoding="async" onError=${() => setBroken(true)} />`
      : html`<div class="sc-preview-none"><i class=${`ph ph-${broken ? "image-broken" : icon}`} aria-hidden="true"></i>
          <span>${broken ? "Preview file missing" : "No preview"}</span></div>`}
  </div>`;
}

/* --------------------------------------------------------------- collections */

/* Items split by collection in the API's order. Titles and lines come from
   g-content. Anything whose collection is unknown goes under Other, last. */
function byCollection(items, cols) {
  if (!cols.length) return [{ c: null, items }];
  const known = new Set(cols.map((c) => c.id));
  const out = cols.map((c) => ({ c, items: items.filter((x) => x.collection === c.id) }));
  const other = items.filter((x) => !known.has(x.collection));
  if (other.length) out.push({ c: { id: "", title: "Other" }, items: other });
  return out;
}

function Collection({ c, children }) {
  if (!c) return children;
  return html`<section class="sc-coll" aria-labelledby=${`sc-coll-${c.id || "other"}`}>
    <div class="sc-coll-head">
      <h2 id=${`sc-coll-${c.id || "other"}`}>${c.title || c.id}</h2>
      ${c.line && html`<p class="muted">${c.line}</p>`}
    </div>
    ${children}
  </section>`;
}

/* --------------------------------------------------------------- pieces */

function PieceCard({ p, open }) {
  return html`<a class="card sc-card" href=${`?piece=${p.id}`} onClick=${(e) => { if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); open(p.id); } }}>
    <${Preview} src=${p.hero_url || p.poster_url} alt="" format=${p.format} />
    <div class="sc-card-body">
      <div class="sc-card-title">${p.title || p.id}</div>
      <div class="sc-card-meta"><span>${p.recipe}</span><span class="sc-fmt">${p.format}</span></div>
      <div class="sc-card-foot"><${Scores} judge=${p.judge_score} owner=${p.owner_score} /><${Status} status=${p.status} /></div>
    </div>
  </a>`;
}

function Pieces({ pieces, cols, q, go, open }) {
  const byRecipe = q.recipe ? pieces.filter((p) => p.recipe === q.recipe) : pieces;
  const coll = q.collection && (cols.find((c) => c.id === q.collection) || { id: q.collection, title: q.collection });
  const inColl = coll ? byRecipe.filter((p) => p.collection === coll.id) : byRecipe;
  const byStatus = q.status ? byRecipe.filter((p) => p.status === q.status) : byRecipe;
  const shown = coll ? byStatus.filter((p) => p.collection === coll.id) : byStatus;
  const count = (s) => (s === "all" ? inColl.length : inColl.filter((p) => p.status === s).length);
  const groups = coll ? [{ c: coll, items: shown }] : byCollection(shown, cols).filter((g) => g.items.length);
  return html`
    ${cols.length > 0 && html`<div class="sc-filters sc-filters-coll" role="radiogroup" aria-label="Collection">
      ${[{ id: "all", title: "All" }, ...cols].map((c) => html`<button type="button" key=${c.id} role="radio"
          aria-checked=${(q.collection || "all") === c.id} class=${`sc-chip ${(q.collection || "all") === c.id ? "on" : ""}`}
          onClick=${() => go({ collection: c.id })}>${c.title || c.id}<span class="num">${c.id === "all" ? byStatus.length
            : byStatus.filter((p) => p.collection === c.id).length}</span></button>`)}
    </div>`}
    <div class="sc-filters" role="radiogroup" aria-label="Status">
      ${STATUSES.map(([k, label]) => html`<button type="button" key=${k} role="radio"
          aria-checked=${(q.status || "all") === k} class=${`sc-chip ${(q.status || "all") === k ? "on" : ""}`}
          onClick=${() => go({ status: k }, true)}>${label}<span class="num">${count(k)}</span></button>`)}
    </div>
    ${pieces.length === 0
      ? html`<div class="card"><${Empty} icon="info" title="No pieces yet"
          desc="When a recipe makes something it lands here. Run one with g-content make <recipe>." /></div>`
      : coll && inColl.length === 0
        ? html`<${Collection} c=${coll}><div class="card"><${Empty} icon="info" title="Nothing here yet"
            desc="No piece belongs to this collection so far."><${Button} size="sm" onClick=${() => go({ collection: "" })}>Show all collections<//><//></div><//>`
      : shown.length === 0
        ? html`<${Collection} c=${coll || null}><div class="card"><${Empty} icon="info" title="Nothing matches"
            desc="No piece has this recipe and status."><${Button} size="sm" onClick=${() => go({ status: "all", recipe: "" }, true)}>Show every piece<//><//></div><//>`
        : html`<div class="sc-colls">${groups.map((g) => html`<${Collection} key=${g.c ? g.c.id : ""} c=${g.c}>
            <div class="sc-grid">${g.items.map((p) => html`<${PieceCard} key=${p.id} p=${p} open=${open} />`)}</div><//>`)}</div>`}`;
}

/* --------------------------------------------------------------- recipe.md */

/* A small markdown renderer: escape first, then headings, lists, code, links. */
function renderMd(md) {
  const inline = (s) => escapeHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const out = [];
  let list = null, para = [], code = null;
  const flush = () => {
    if (para.length) out.push(`<p>${inline(para.join(" "))}</p>`);
    para = [];
    if (list) out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`);
    list = null;
  };
  for (const line of String(md || "").split("\n")) {
    if (code) {
      if (/^```/.test(line)) { out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`); code = null; } else code.push(line);
      continue;
    }
    if (/^```/.test(line)) { flush(); code = []; continue; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    const li = line.match(/^\s*([-*]|\d+\.)\s+(.*)$/);
    if (h) { flush(); const n = Math.min(h[1].length + 1, 4); out.push(`<h${n}>${inline(h[2])}</h${n}>`); }
    else if (li) {
      const tag = /\d/.test(li[1]) ? "ol" : "ul";
      if (para.length || (list && list.tag !== tag)) flush();
      (list ||= { tag, items: [] }).items.push(li[2]);
    } else if (!line.trim()) flush();
    else if (list && /^\s+/.test(line)) list.items[list.items.length - 1] += " " + line.trim();
    else { if (list) flush(); para.push(line.trim()); }
  }
  if (code) out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
  flush();
  return out.join("\n");
}

function RecipeDoc({ id }) {
  const st = useLoad(`${API}/recipes/${id}`);
  if (st.error) return html`<${ErrorState} error=${st.error} retry=${st.reload} title="The recipe did not load" />`;
  if (!st.data) return html`<${SkeletonRows} rows=${5} height=${16} />`;
  if (!st.data.recipe_md) return html`<p class="muted">This recipe has no recipe.md.</p>`;
  return html`<div class="prose sc-md" dangerouslySetInnerHTML=${{ __html: renderMd(st.data.recipe_md) }}></div>`;
}

function Recipes({ recipes, cols, go }) {
  const [openId, setOpen] = useState(null);
  if (!recipes.length) return html`<div class="card"><${Empty} icon="info" title="No recipes yet"
    desc="A recipe is a folder under recipes/ in g-content. Its pieces show here once it has run." /></div>`;
  return html`<div class="sc-colls">${byCollection(recipes, cols).filter((g) => g.items.length).map((g) => html`<${Collection} key=${g.c ? g.c.id : ""} c=${g.c}>
    <div class="sc-recipes">${g.items.map((r) => html`<div class="card sc-recipe" key=${r.id}>
    <div class="sc-recipe-head">
      <div class="sc-recipe-text">
        <div class="sc-card-title">${r.title || r.id}</div>
        <p class="muted">${r.summary}</p>
        <div class="sc-recipe-meta">
          <span><i class="ph ph-cpu" aria-hidden="true"></i>${r.runner}</span>
          <span><i class="ph ph-file" aria-hidden="true"></i>${r.format}</span>
          <span class="num">${r.piece_count} ${r.piece_count === 1 ? "piece" : "pieces"}</span>
          <span>Best ${r.best ? html`<span class="num">${r.best.judge ?? "none"}</span> judge, <span class="num">${r.best.owner ?? "none"}</span> you` : "none yet"}</span>
        </div>
      </div>
      <div class="sc-recipe-actions">
        ${r.piece_count > 0 && html`<${Button} size="sm" kind="tertiary" onClick=${() => go({ view: "", recipe: r.id, collection: r.collection || "" })}>See pieces<//>`}
        <${Button} size="sm" aria-expanded=${openId === r.id}
          onClick=${() => setOpen(openId === r.id ? null : r.id)}><i class=${`ph ph-caret-${openId === r.id ? "up" : "down"}`} aria-hidden="true"></i>${openId === r.id ? "Hide recipe.md" : "Read recipe.md"}<//>
      </div>
    </div>
    ${openId === r.id && html`<div class="sc-recipe-doc"><${RecipeDoc} id=${r.id} /></div>`}
  </div>`)}</div><//>`)}</div>`;
}

/* --------------------------------------------------------------- disagreements */

const sc = (v) => (v && typeof v === "object" ? v.score : v);
function Disagreements({ cal, open }) {
  const rows = (cal.disagreements || cal.pieces || []).map((d) => ({
    ...d, judge: sc(d.judge), owner: sc(d.owner),
    judge_notes: d.judge_notes ?? (d.judge && d.judge.notes), owner_note: d.owner_note ?? (d.owner && d.owner.note),
  })).filter((d) => d.judge != null && d.owner != null && Math.abs(d.owner - d.judge) >= 2);
  const by = Object.entries(cal.by_recipe || {});
  return html`
    <section class="sc-section">
      <h2>Mean gap by recipe</h2>
      ${by.length === 0 ? html`<p class="muted">No rated pieces yet. Rate a few and the gap shows here.</p>`
        : html`<div class="card sc-flush"><div class="table-wrap"><table class="table">
          <thead><tr><th>Recipe</th><th class="r">Rated</th><th class="r">Mean gap</th><th class="r">Mean size</th></tr></thead>
          <tbody>${by.map(([id, v]) => html`<tr key=${id}><td>${id}</td><td class="r num">${v.n}</td>
            <td class="r num">${fmtGap(v.mean_delta)}</td><td class="r num">${v.mean_abs_delta == null ? "" : v.mean_abs_delta.toFixed(1)}</td></tr>`)}</tbody>
        </table></div></div>
        <p class="muted sc-note">Gap is your score less the judge's, so a minus means the judge rated higher.</p>`}
    </section>
    <section class="sc-section">
      <h2>Pieces two or more apart</h2>
      ${rows.length === 0
        ? html`<div class="card"><${Empty} icon="info" title="You and the judge agree so far"
            desc="A piece shows here when your score and the judge's are two or more apart." /></div>`
        : html`<div class="sc-dis">${rows.map((d) => html`<a class="card sc-dis-row" key=${d.id} href=${`?piece=${d.id}`}
            onClick=${(e) => { if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); open(d.id); } }}>
            <div class="sc-dis-head"><span class="sc-card-title">${d.title || d.id}</span><span class="muted">${d.recipe}</span></div>
            <div class="sc-dis-grid">
              <div><div class="sc-dis-label">Judge <span class="num sc-big">${d.judge}</span></div><p>${d.judge_notes || "No notes."}</p></div>
              <div><div class="sc-dis-label">You <span class="num sc-big">${d.owner}</span></div><p>${d.owner_note || "No note."}</p></div>
            </div>
            <div class="sc-dis-gap num">${fmtGap(d.delta ?? d.owner - d.judge)}</div>
          </a>`)}</div>`}
    </section>`;
}
const fmtGap = (v) => (v == null ? "" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(Number.isInteger(v) ? 0 : 1)}`);

/* --------------------------------------------------------------- piece detail */

const isModel = (f) => /\.glb$/.test(f.name) || /gltf/.test(f.type || "");
const kindOf = (f) => (isModel(f) ? "model" : f.type === "image/svg+xml" ? "svg" : (f.type || "").startsWith("image/") ? "image"
  : (f.type || "").startsWith("video/") ? "video" : f.type === "text/html" ? "html" : "file");
const ratio = (f) => (f.width && f.height ? `${f.width} / ${f.height}` : null);

function webglOk() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

/* The 3D viewer: three is never bundled. The iframe's import map points at the
   proxy's /vendor/three and it renders only when the camera moves. The frame
   runs only this code (a .glb is data, parsed by three), so it keeps Command's
   origin: the proxy's cookie travels and the modules load without CORS. */
function modelDoc(src, bg) {
  const V = `${location.origin}${API}/vendor/three`;
  return `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%;background:${bg};overflow:hidden}canvas{display:block;width:100%;height:100%}</style>
<script type="importmap">{"imports":{"three":"${V}/build/three.module.js","three/addons/":"${V}/examples/jsm/"}}</script></head><body>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
const say = (m) => parent.postMessage({ scModel: m }, "*");
try {
  const r = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  r.setClearColor(0x000000, 0);
  r.setPixelRatio(Math.min(devicePixelRatio, 2));
  r.toneMapping = THREE.ACESFilmicToneMapping;
  document.body.appendChild(r.domElement);
  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture;
  const cam = new THREE.PerspectiveCamera(40, 1, 0.01, 1000);
  const ctl = new OrbitControls(cam, r.domElement);
  const draw = () => r.render(scene, cam);
  const size = () => { r.setSize(innerWidth, innerHeight, false); cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); draw(); };
  ctl.addEventListener("change", draw);
  addEventListener("resize", size);
  const res = await fetch(${JSON.stringify(src)}, { credentials: "same-origin" });
  if (!res.ok) throw new Error("the model file answered " + res.status);
  const gltf = await new GLTFLoader().parseAsync(await res.arrayBuffer(), "");
  const box = new THREE.Box3().setFromObject(gltf.scene), c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3()).length() || 1;
  gltf.scene.position.sub(c);
  scene.add(gltf.scene);
  cam.position.set(s * 0.75, s * 0.55, s * 1.0);
  cam.near = s / 100; cam.far = s * 100; cam.updateProjectionMatrix();
  ctl.update();
  size();
  say("ready");
} catch (e) { say("failed: " + (e && e.message || e)); }
</script></body></html>`;
}

function ModelView({ piece, file, still }) {
  const [state, setState] = useState(webglOk() ? "loading" : "nowebgl");
  const ref = useRef(null);
  useEffect(() => {
    const on = (e) => {
      if (!ref.current || e.source !== ref.current.contentWindow || !e.data || !e.data.scModel) return;
      setState(e.data.scModel === "ready" ? "ready" : e.data.scModel);
    };
    addEventListener("message", on);
    return () => removeEventListener("message", on);
  }, []);
  const bg = getComputedStyle(document.body).getPropertyValue("--bg").trim() || "#111";
  if (state === "nowebgl" || state.startsWith("failed")) {
    return html`<div class="sc-model-fallback">
      ${still ? html`<img src=${still} alt=${`Still of ${piece.title}`} />` : html`<div class="sc-preview-none"><i class="ph ph-cube" aria-hidden="true"></i></div>`}
      <p class="muted">${state === "nowebgl" ? "This browser has no WebGL, so here is the still instead." : `The model did not open (${state.slice(8)}), so here is the still instead.`}</p>
    </div>`;
  }
  return html`<div class="sc-model">
    <iframe ref=${ref} title=${`3D model ${file.name}`} srcdoc=${modelDoc(location.origin + fileUrl(piece.id, file.name), bg)}></iframe>
    ${state === "loading" && html`<div class="sc-model-wait muted">Opening the model</div>`}
  </div>`;
}

function Output({ piece, f, still, big }) {
  const url = px(f.url) || fileUrl(piece.id, f.name);
  const [broken, setBroken] = useState(false);
  const k = kindOf(f);
  const style = ratio(f) ? { aspectRatio: ratio(f) } : null;
  if (broken) return html`<div class="sc-out-missing" style=${style}><i class="ph ph-image-broken" aria-hidden="true"></i><span>${f.name} is missing from the library.</span></div>`;
  if (k === "image" || k === "svg") return html`<a class="sc-out-img" href=${url} target="_blank" rel="noopener" style=${style}>
    <img src=${url} alt=${`${piece.title}, ${f.role}`} onError=${() => setBroken(true)} /></a>`;
  if (k === "video") return html`<video class="sc-out-video" controls preload="metadata" playsinline poster=${still || undefined} style=${style} src=${url} onError=${() => setBroken(true)}></video>`;
  if (k === "html") return html`<iframe class="sc-out-html" sandbox="allow-scripts" title=${`${piece.title}, ${f.name}`} src=${url} style=${style || { aspectRatio: "16 / 9" }} loading="lazy"></iframe>`;
  if (k === "model") return html`<${ModelView} piece=${piece} file=${f} still=${still} />`;
  return html`<a class="sc-out-file" href=${url} target="_blank" rel="noopener"><i class="ph ph-file" aria-hidden="true"></i>${f.name}<span class="muted">${f.type}</span></a>`;
}

const ROLE_ORDER = ["hero", "model", "html", "video", "still", "poster", "map", "source"];
const ROLE_LABEL = { hero: "Hero", model: "Model", html: "Page", video: "Video", still: "Still", poster: "Poster", map: "Map", source: "Source" };

function Rating({ piece, onSaved }) {
  const [score, setScore] = useState(piece.owner && piece.owner.score);
  const [note, setNote] = useState((piece.owner && piece.owner.note) || "");
  const saved = useRef(note);
  const save = async (s, n, what) => {
    try {
      await call(`${API}/pieces/${piece.id}/rating`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ score: s, note: n }) });
      saved.current = n;
      toastOk(what);
      onSaved(s, n);
    } catch (e) {
      toast({ title: "The rating did not save", desc: e.message || String(e), kind: "error" });
    }
  };
  return html`<section class="sc-section">
    <h2>Your rating</h2>
    <div class="g-segmented sc-rate" data-block role="radiogroup" aria-label="Your score from 1 to 10">
      ${Array.from({ length: 10 }, (_, i) => i + 1).map((n) => html`<label key=${n} class="num">
        <input type="radio" name="sc-score" value=${n} checked=${score === n}
          onChange=${() => { setScore(n); save(n, note, `Rated ${n}`); }} />${n}</label>`)}
    </div>
    <div class="field sc-note-field">
      <label class="label" for="sc-note">Note <span class="optional">optional</span></label>
      <textarea id="sc-note" class="textarea" maxlength="500" rows="2" value=${note}
        placeholder=${score ? "What would make it better" : "Pick a score first"} disabled=${!score}
        onInput=${(e) => setNote(e.currentTarget.value)}
        onBlur=${() => { if (score && note !== saved.current) save(score, note, "Note saved"); }}></textarea>
    </div>
  </section>`;
}

const rowsOf = (pairs) => pairs.filter(([, v]) => v != null && v !== "" && !(Array.isArray(v) && !v.length));

function Provenance({ p }) {
  const v = p.provenance || {};
  const agents = (v.agents || []).map((a) => [a.role, a.model, a.effort].filter(Boolean).join(" ")).join(", ");
  const rows = rowsOf([
    ["Runner", v.runner],
    ["Device", v.device && [v.device.name, v.device.gpu].filter(Boolean).join(", ")],
    ["Agents", v.agents && (v.agents.length ? agents : "None, pure code")],
    ["Tools", (v.tools || []).join(", ")],
    ["Generated pixels", v.generated_pixels == null ? null : v.generated_pixels ? "Yes" : "No"],
    ["Cost", v.cost_usd == null ? null : `$${Number(v.cost_usd).toFixed(2)}`],
    ["Wall time", v.wall_s == null ? null : `${Math.round(v.wall_s)} s`],
    ["Attempts", v.attempts],
    ["Commit", v.commit && html`<span class="mono">${String(v.commit).slice(0, 12)}</span>`],
    ["Host", v.host],
  ]);
  return html`<section class="sc-section">
    <h2>How it was made</h2>
    <div class="card"><dl class="sc-kv">${rows.map(([k, val]) => html`<dt key=${k}>${k}</dt><dd>${val}</dd>`)}</dl>
    ${(v.sources || []).length > 0 && html`<h3 class="sc-sub">Sources</h3><ul class="sc-list">${v.sources.map((s, i) => html`<li key=${i}>
      ${s.url ? html`<a href=${s.url} target="_blank" rel="noopener">${s.what || s.url}</a>` : s.what}
      <${Badge} kind="plain">${s.licence || "No licence given"}<//></li>`)}</ul>`}
    ${(v.data || []).length > 0 && html`<h3 class="sc-sub">Figures</h3><ul class="sc-list">${v.data.map((d, i) => html`<li key=${i}>
      <span>${d.figure}</span> <span class="num">${d.value}</span><div class="mono faint wrap-any">${d.query}</div></li>`)}</ul>`}
    </div>
  </section>`;
}

function Detail({ id, cols, back, go, onRated }) {
  const st = useLoad(`${API}/pieces/${id}`);
  if (st.error) {
    if (sameError(st.error)) return html`<${DetailBar} back=${back} /><${Trouble} error=${st.error} retry=${st.reload} />`;
    return html`<${DetailBar} back=${back} /><div class="card"><${Empty} icon="info" title="No such piece"
      desc=${`g-content has no piece called ${id}. It may have been removed.`} /></div>`;
  }
  if (!st.data) return html`<${DetailBar} back=${back} /><div class="sc-hero-slot skeleton"></div><${SkeletonRows} rows=${3} />`;
  const p = st.data;
  const files = [...(p.files || [])].sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));
  const stillFile = files.find((f) => f.role === "poster" || f.role === "still") || files.find((f) => f.role === "hero" && kindOf(f) === "image");
  const still = stillFile && (px(stillFile.url) || fileUrl(p.id, stillFile.name));
  const hero = files.find((f) => f.role === "hero") || files[0];
  const rest = files.filter((f) => f !== hero && !(f === stillFile && kindOf(hero || {}) === "video"));
  const gates = Object.entries(p.gates || {});
  return html`
    <${DetailBar} back=${back}>
      <${Status} status=${p.status} />
    <//>
    <div class="sc-detail-head">
      <h2 class="sc-detail-title">${p.title || p.id}</h2>
      ${p.summary && html`<p class="muted">${p.summary}</p>`}
      <div class="sc-recipe-meta">${p.collection && html`<a class="sc-coll-link" href=${`?collection=${p.collection}`}
          onClick=${(e) => { if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); go({ piece: "", collection: p.collection, view: "" }); } }}>
          <i class="ph ph-folder-simple" aria-hidden="true"></i>${(cols.find((c) => c.id === p.collection) || {}).title || p.collection}</a>`}<span>${p.recipe}</span><span>${p.format}</span><span class="mono">${p.id}</span></div>
    </div>
    ${hero ? html`<div class="sc-hero"><${Output} piece=${p} f=${hero} still=${still} big /></div>`
      : html`<div class="card"><${Empty} icon="info" title="This piece lists no files" /></div>`}
    ${rest.length > 0 && html`<section class="sc-section"><h2>Every output</h2><div class="sc-outs">${rest.map((f) => html`<figure class="sc-out" key=${f.name}>
      <${Output} piece=${p} f=${f} still=${still} />
      <figcaption><span>${ROLE_LABEL[f.role] || f.role}</span><span class="muted mono">${f.name}${f.width ? ` ${f.width}x${f.height}` : ""}</span></figcaption>
    </figure>`)}</div></section>`}
    <${Rating} piece=${p} onSaved=${(s, n) => { st.setData({ ...p, owner: { score: s, note: n } }); onRated(p.id, s); }} />
    <section class="sc-section">
      <h2>The judge</h2>
      ${p.judge ? html`<div class="card sc-judge">
          <div class="sc-judge-score"><span class="num sc-big">${p.judge.score}</span><span class="muted">out of 10</span></div>
          <p>${p.judge.notes}</p>
          <div class="muted sc-recipe-meta"><span>${p.judge.model}</span><span>${p.judge.effort} effort</span></div>
        </div>`
        : html`<div class="card"><${Empty} icon="info" title="Not judged yet" desc=${`Run g-content judge ${p.id} to score it.`} /></div>`}
    </section>
    ${gates.length > 0 && html`<section class="sc-section"><h2>Gates</h2><div class="card sc-gates">${gates.map(([gid, g]) => html`
      <details class="sc-gate" key=${gid}>
        <summary><span class="mono">${gid}</span><${Badge} kind=${GATE_BADGE[g.result] || "plain"}>${g.result}<//></summary>
        <p class="muted">${g.note || "No note."}${g.by ? ` Checked by ${g.by}.` : ""}</p>
      </details>`)}</div></section>`}
    <${Provenance} p=${p} />`;
}

function DetailBar({ back, children }) {
  return html`<div class="sc-detail-bar">
    <${Button} size="sm" kind="tertiary" onClick=${back}><i class="ph ph-arrow-left" aria-hidden="true"></i>All pieces<//>
    ${children}
  </div>`;
}

/* --------------------------------------------------------------- page */

function Showcase() {
  const [q, go] = useQuery();
  const view = q.view || "pieces";
  const recipes = useLoad(`${API}/recipes`);
  const pieces = useLoad(`${API}/pieces`);
  const colls = useLoad(`${API}/collections`);
  const cal = useLoad(view === "disagree" ? `${API}/calibration` : null);
  const open = (id) => go({ piece: id });
  const back = () => (history.state === null && document.referrer.indexOf(location.pathname) < 0 ? go({ piece: "" }) : history.back());
  const onRated = (id, s) => pieces.data && Array.isArray(pieces.data) && pieces.setData(pieces.data.map((p) => (p.id === id ? { ...p, owner_score: s } : p)));

  const clist = Array.isArray(colls.data) ? colls.data : (colls.data && colls.data.collections) || [];
  if (q.piece) return html`<div class="sc-page"><${Detail} id=${q.piece} cols=${clist} go=${go} back=${() => go({ piece: "" })} onRated=${onRated} /></div>`;

  // A g-content without collections yet still shows its pieces, ungrouped.
  const err = pieces.error || recipes.error || (colls.error && sameError(colls.error) ? colls.error : null);
  const cwait = colls.data === undefined && !colls.error;
  const plist = Array.isArray(pieces.data) ? pieces.data : (pieces.data && pieces.data.pieces) || [];
  const rlist = Array.isArray(recipes.data) ? recipes.data : (recipes.data && recipes.data.recipes) || [];
  return html`<div class="sc-page">
    <${PageHead} title="Showcase" sub="What the recipes have made. Open a piece to see it full size and how it was made, then rate it.">
      <div class="g-segmented g-segmented-sm" role="radiogroup" aria-label="View">
        ${MODES.map(([k, label]) => html`<label key=${k}><input type="radio" name="sc-view" checked=${view === k}
          onChange=${() => go({ view: k === "pieces" ? "" : k }, true)} />${label}</label>`)}
      </div>
      ${view === "pieces" && rlist.length > 0 && html`<span class="select-wrap sc-recipe-pick"><select class="select" aria-label="Recipe"
          value=${q.recipe || ""} onChange=${(e) => go({ recipe: e.currentTarget.value }, true)}>
        <option value="">Every recipe</option>
        ${rlist.map((r) => html`<option key=${r.id} value=${r.id}>${r.title || r.id} (${plist.filter((p) => p.recipe === r.id).length})</option>`)}
      </select></span>`}
    <//>
    ${err ? html`<${Trouble} error=${err} retry=${() => { pieces.reload(); recipes.reload(); colls.reload(); }} />`
      : view === "recipes" ? (recipes.data === undefined || cwait ? html`<${SkeletonRows} rows=${4} height=${72} />` : html`<${Recipes} recipes=${rlist} cols=${clist} go=${go} />`)
      : view === "disagree" ? (cal.error ? html`<${Trouble} error=${cal.error} retry=${cal.reload} />`
          : cal.data === undefined ? html`<${SkeletonRows} rows=${4} height=${56} />` : html`<${Disagreements} cal=${cal.data} open=${open} />`)
      : pieces.data === undefined || cwait ? html`<div class="sc-grid">${[0, 1, 2, 3, 4, 5].map((i) => html`<div class="card sc-card" key=${i}><div class="sc-preview skeleton"></div><div class="sc-card-body"><div class="skeleton" style="height:16px;width:70%"></div><div class="skeleton" style="height:12px;width:40%"></div></div></div>`)}</div>`
      : html`<${Pieces} pieces=${plist} cols=${clist} q=${q} go=${go} open=${open} />`}
  </div>`;
}

mount(Showcase);
