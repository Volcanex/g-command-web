// One research area (pages/research/CLAUDE.md). Every area page's app.js is
// `mountArea("<id>")`; what the area holds and its sub-views come from the
// registry (areas.json) through /api/research, and each sub-view's kind picks
// its renderer below. Sub-views are links (`?view=`), so each is bookmarkable.
import { html, PageHead, Loaded, Empty, SkeletonRows, Badge, mount, useJson } from "../../core/app/boot.js";
import { parse, inline, plainText } from "./md.js";
import "./area.css";

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const when = (iso) => (iso ? DATE.format(new Date(iso)) : "");
const num = (v, d = 0) => (v == null || !Number.isFinite(Number(v)) ? "" : Number(v).toFixed(d));
const pct = (v) => (v == null ? "" : `${Math.round(Number(v) * 100)}%`);
const flat = (s) => (window.g && window.g.plain ? window.g.plain(s) : plainText(s));

const params = () => new URLSearchParams(location.search);
const viewHref = (view, extra = {}) => {
  const p = new URLSearchParams({ view, ...extra });
  return `${location.pathname}?${p}`;
};

/* ---------------------------------------------------------------- documents */

function Contents({ headings, label = "Contents" }) {
  if (!headings.length) return null;
  return html`<nav class="rs-contents" aria-label=${label}>
    ${headings.map((h) => html`<a key=${h.id} class=${`rs-toc rs-toc-${h.level}`} href=${`#${h.id}`}>${h.text}</a>`)}
  </nav>`;
}

/* The side column: on a wide screen it sits left of the text and stays put, on a
   narrow one it folds into a disclosure above it. */
function DocLayout({ side, sideLabel, children }) {
  return html`<div class="rs-doc">
    ${side && html`<details class="card rs-side-fold"><summary>${sideLabel}</summary>${side}</details>`}
    ${side && html`<aside class="rs-side" aria-label=${sideLabel}>${side}</aside>`}
    <article class="card rs-article">${children}</article>
  </div>`;
}

function Meta({ items }) {
  const shown = items.filter(Boolean);
  if (!shown.length) return null;
  return html`<div class="rs-meta">${shown.map((t) => html`<span>${t}</span>`)}</div>`;
}

function Paper({ data }) {
  const { nodes, headings } = parse(data.markdown);
  return html`<${DocLayout} side=${headings.length ? html`<${Contents} headings=${headings} />` : null} sideLabel="Contents">
    <${Meta} items=${[data.file, data.mtime && `Changed ${when(data.mtime)}`]} />
    <div class="prose rs-prose">${nodes}</div>
  <//>`;
}

function Docs({ data, view }) {
  const doc = data.doc;
  const { nodes, headings } = parse(doc.markdown);
  const side = html`<nav class="rs-contents" aria-label="Documents">
    ${data.docs.map((d) => html`<div key=${d.id} class="rs-doc-entry">
      <a class="rs-toc rs-toc-doc" href=${viewHref(view, { doc: d.id })} aria-current=${d.id === doc.id ? "page" : undefined}>${flat(d.title)}</a>
      ${d.id === doc.id && headings.filter((h) => h.level === 2).map((h) => html`<a key=${h.id} class="rs-toc rs-toc-3" href=${`#${h.id}`}>${h.text}</a>`)}
    </div>`)}
  </nav>`;
  return html`
    ${data.bib && html`<p class="rs-note num">${data.docs.length} notes, ${data.bib.entries} references in ${data.bib.file}</p>`}
    <${DocLayout} side=${side} sideLabel=${`${data.docs.length} documents`}>
      <${Meta} items=${[doc.id, `Changed ${when(doc.mtime)}`]} />
      <div class="prose rs-prose">${nodes}</div>
    <//>`;
}

/* ---------------------------------------------------------------- claims */

const STATUS_KIND = { Established: "ok", Argued: "info", Conjecture: "warn" };

function Stat({ label, now, then }) {
  return html`<div class="rs-stat">
    <div class="rs-stat-value num">${now}</div>
    <div class="rs-stat-label">${label}</div>
    <div class="rs-stat-then num">${then}</div>
  </div>`;
}

function Claims({ data }) {
  const live = data.live;
  const then = data.then || {};
  const groups = [];
  for (const c of data.claims) {
    let g = groups.find((x) => x.status === c.status);
    if (!g) groups.push((g = { status: c.status, items: [] }));
    g.items.push(c);
  }
  const was = (n) => (then.date && n != null ? `${n} on ${when(then.date)}` : "");
  return html`
    ${live ? html`<section class="card rs-live" aria-label="Live registry">
      <div class="card-head"><span class="card-title">Live in g-levels</span>
        <a class="btn btn-tertiary btn-sm" href="/levels">Open Levels</a></div>
      <div class="rs-stats">
        <${Stat} label="Gates" now=${live.gates} then=${was(then.gates)} />
        <${Stat} label="Charters" now=${live.charters} then=${was(then.charters)} />
        <${Stat} label="Design gates" now=${live.design} then=${was(then.design)} />
        <${Stat} label="Silent gates" now=${live.silent} then=${`${live.rows} results logged`} />
      </div>
    </section>` : html`<div class="card"><${Empty} icon="warning-circle" title="The live side is missing" desc=${data.levels_error} /></div>`}
    ${groups.map((g) => html`<section class="stack" key=${g.status}>
      <h2 class="section-head">${g.status}<${Badge} kind="plain" class="num">${g.items.length}<//></h2>
      <div class="card rs-claims">
        ${g.items.map((c, i) => html`<div class="rs-claim" key=${i}>
          <p class="rs-claim-text">${inline(c.text.charAt(0).toUpperCase() + c.text.slice(1))}</p>
          ${c.evidence && c.evidence.length
            ? html`<dl class="rs-evidence">${c.evidence.map((e) => html`<div key=${e.label}>
                <dt>${e.label}</dt><dd><span class="num rs-ev-value">${e.value}</span><span class="rs-ev-detail">${e.detail}</span></dd></div>`)}</dl>`
            : html`<p class="rs-ev-none">${live ? "Nothing in g-levels measures this yet." : ""}</p>`}
        </div>`)}
      </div>
    </section>`)}
    ${data.domain && data.domain.length > 0 && html`<section class="stack">
      <h2 class="section-head">Gates on ${data.domain_name}<${Badge} kind="plain" class="num">${data.domain.length}<//></h2>
      <div class="card rs-claims">
        ${data.domain.map((g) => {
          const c = g.counts || {};
          const total = ["met", "attempted", "waived", "impossible"].reduce((n, k) => n + (c[k] || 0), 0);
          return html`<div class="rs-claim" key=${g.id}>
            <div class="row-tight"><code class="rs-gate">${g.id}</code>
              <${Badge} kind=${g.pinned ? "ok" : "warn"}>${g.pinned ? "Pinned" : "Not pinned"}<//>
              ${g.kind === "design" && html`<${Badge} kind="plain">Design<//>`}</div>
            <p class="rs-claim-text">${g.principle}</p>
            <p class="rs-ev-none num">${total ? `${c.met || 0} met, ${c.attempted || 0} attempted, ${c.impossible || 0} impossible, last ${when(g.last)}`
              : g.pinned ? "Pinned, nothing logged yet." : "No charter pins it, so it never fires."}</p>
          </div>`;
        })}
      </div>
    </section>`}`;
}

/* ---------------------------------------------------------------- ANS */

function Runs({ data }) {
  const done = data.runs.filter((r) => r.status === "completed").length;
  return html`
    <p class="rs-note num">${data.runs.length} runs, ${done} completed, in ${data.sweeps.length} sweeps. Read from ${data.file}, changed ${when(data.mtime)}.</p>
    <section class="stack">
      <h2 class="section-head">Sweeps</h2>
      <div class="card flush"><div class="table-wrap"><table class="table rs-table">
        <thead><tr><th>Sweep</th><th>Status</th><th class="r rs-wide">Runs</th><th class="rs-wide">Started</th></tr></thead>
        <tbody>${data.sweeps.map((s) => html`<tr key=${s.sweep}><td><div class="rs-cell"><span class="mono">${s.sweep}</span>
            <span class="rs-dim rs-narrow num">${s.runs} runs, ${when(s.started)}</span></div></td>
          <td><${Badge} kind=${s.status === "completed" ? "ok" : "warn"}>${s.status === "completed" ? "Completed" : "Interrupted"}<//></td>
          <td class="r num rs-wide">${s.runs}</td><td class="num rs-wide">${when(s.started)}</td></tr>`)}</tbody>
      </table></div></div>
    </section>
    <section class="stack">
      <h2 class="section-head">Runs</h2>
      <div class="card flush"><div class="table-wrap"><table class="table rs-table">
        <thead><tr><th>Model</th><th class="rs-wide">Harness</th><th class="rs-wide">Suite</th><th>Passed</th><th class="r rs-wide">Gen tok/s</th><th class="r rs-wide">Peak MiB</th><th class="rs-wide">Status</th></tr></thead>
        <tbody>${data.runs.map((r) => {
          const rate = r.done ? r.passed / r.done : 0;
          const open = r.status !== "completed";
          return html`<tr key=${r.run}>
            <td><div class="rs-cell"><span>${r.model}</span>
              <span class="rs-dim rs-narrow"><span class="mono">${r.harness}</span> on ${r.suite}</span></div></td>
            <td class="mono rs-wide">${r.harness}</td><td class="rs-wide">${r.suite}</td>
            <td><div class="rs-cell"><div class="rs-pass"><span class="num">${r.passed} of ${r.done}</span>
              <span class="g-meter" aria-hidden="true"><span class="g-meter-fill" style=${`width:${Math.round(rate * 100)}%`}></span></span></div>
              ${open && html`<span class="rs-dim rs-narrow num">${r.done} of ${r.n} done</span>`}</div></td>
            <td class="r num rs-wide">${num(r.gen_tps, 1)}</td><td class="r num rs-wide">${num(r.peak_mb)}</td>
            <td class="rs-wide">${open ? html`<${Badge} kind="warn">${r.done} of ${r.n} done<//>` : html`<${Badge} kind="ok">Completed<//>`}</td>
          </tr>`;
        })}</tbody>
      </table></div></div>
    </section>`;
}

/* A pass rate with its interval: the band is the interval, the tick the estimate. */
function Interval({ rate, low, high }) {
  const at = (v) => `${Math.max(0, Math.min(100, Number(v || 0) * 100))}%`;
  return html`<span class="rs-ci" aria-hidden="true">
    <span class="rs-ci-band" style=${`left:${at(low)};width:calc(${at(high)} - ${at(low)})`}></span>
    <span class="rs-ci-mark" style=${`left:${at(rate)}`}></span>
  </span>`;
}

function Atlas({ data }) {
  return data.datasets.map((d) => html`<section class="stack" key=${d.id}>
    <h2 class="section-head">${d.label}<${Badge} kind="plain" class="num">${d.n_configs} configs<//></h2>
    <p class="section-sub num">${d.n_tasks} tasks, ${d.n_items} items on ${d.host}. Built ${when(d.generated)}.</p>
    <div class="card">
      <div class="rs-rates">
        ${d.rates.map((r, i) => html`<div class="rs-rate" key=${i}>
          <div class="rs-rate-name"><span>${r.model}</span><span class="mono rs-dim">${r.harness}</span></div>
          <${Interval} rate=${r.rate} low=${r.low} high=${r.high} />
          <div class="rs-rate-num num">${pct(r.rate)}<span class="rs-dim"> ${r.successes} of ${r.n}, ${pct(r.low)} to ${pct(r.high)}</span></div>
        </div>`)}
      </div>
      <p class="rs-foot">Pass rate per configuration. The band is its interval, the tick the estimate.</p>
    </div>
    ${d.sensitivity.length > 0 && html`<div class="card flush"><div class="table-wrap"><table class="table rs-table">
      <thead><tr><th>Factor</th><th class="r">First order</th><th class="r">Total</th></tr></thead>
      <tbody>${d.sensitivity.map((s) => html`<tr key=${s.factor}><td>${s.factor}</td>
        <td class="r num">${num(s.S1, 2)} <span class="rs-dim">${num(s.S1_low, 2)} to ${num(s.S1_high, 2)}</span></td>
        <td class="r num">${num(s.ST, 2)} <span class="rs-dim">${num(s.ST_low, 2)} to ${num(s.ST_high, 2)}</span></td></tr>`)}</tbody>
    </table></div>${d.caveat && html`<p class="rs-foot rs-foot-pad">${d.caveat}</p>`}</div>`}
  </section>`);
}

/* ---------------------------------------------------------------- dissertation */

function Tables({ data }) {
  return data.tables.map((t) => html`<section class="stack" key=${t.id}>
    <h2 class="section-head">${t.title}<${Badge} kind="plain" class="num">${t.total} rows<//></h2>
    <p class="section-sub">${t.id}, changed ${when(t.mtime)}${t.total > t.rows.length ? `. The first ${t.rows.length} rows are shown.` : ""}</p>
    <div class="card flush"><div class="table-wrap"><table class="table rs-table">
      <thead><tr>${t.columns.map((c) => html`<th>${c}</th>`)}</tr></thead>
      <tbody>${t.rows.map((r, i) => html`<tr key=${i}>${t.columns.map((_, n) => {
        const v = r[n] ?? "";
        return html`<td class=${/^-?[\d.,]+%?$/.test(v.trim()) ? "r num" : ""}>${v}</td>`;
      })}</tr>`)}</tbody>
    </table></div></div>
  </section>`);
}

function Charts({ data }) {
  return html`<div class="rs-charts">${data.charts.map((c) => html`<figure class="card rs-figure" key=${c.id}>
    <img src=${c.url} alt=${c.title} loading="lazy" />
    <figcaption><span>${c.title}</span><span class="rs-dim num">${when(c.mtime)}</span></figcaption>
  </figure>`)}</div>`;
}

/* ---------------------------------------------------------------- page */

const KINDS = { paper: Paper, docs: Docs, claims: Claims, "ans-runs": Runs, "ans-atlas": Atlas, tables: Tables, charts: Charts };

function Missing({ data, title }) {
  return html`<div class="card"><${Empty} icon="info" title=${data.reason || `No ${title.toLowerCase()} yet`}
    desc=${`This view reads ${data.source} and fills in as files land there.`} /></div>`;
}

function View({ area, view }) {
  const q = params();
  const doc = q.get("doc");
  const state = useJson(`/api/research/${area}/${view.id}${doc ? `?doc=${encodeURIComponent(doc)}` : ""}`);
  const Kind = KINDS[view.kind];
  return html`<${Loaded} state=${state} skeleton=${html`<${SkeletonRows} rows=${6} />`}>
    ${(data) => (data.missing && !(data.docs && data.docs.length) ? html`<${Missing} data=${data} title=${view.title} />` : html`<${Kind} data=${data} view=${view.id} />`)}
  <//>`;
}

function Tabs({ views, current }) {
  return html`<nav class="tabs rs-tabs" aria-label="Views">${views.map((v) => html`
    <a key=${v.id} class="tab" aria-current=${v.id === current ? "page" : undefined} href=${viewHref(v.id)}>${v.title}</a>`)}</nav>`;
}

function AreaPage({ id }) {
  const reg = useJson("/api/research");
  return html`<${Loaded} state=${reg} skeleton=${html`<div class="rs-tabs-slot"></div><${SkeletonRows} rows=${6} />`}>
    ${(data) => {
      const area = data.areas.find((a) => a.id === id);
      if (!area) return html`<div class="card"><${Empty} icon="warning-circle" title="This area is not in the registry" desc="Add it to pages/research/areas.json." /></div>`;
      const want = params().get("view");
      const view = area.views.find((v) => v.id === want) || area.views[0];
      return html`
        <${PageHead} title=${area.title} sub=${area.sub} />
        ${area.views.length > 1 && html`<${Tabs} views=${area.views} current=${view.id} />`}
        <${View} key=${view.id} area=${area.id} view=${view} />`;
    }}
  <//>`;
}

export function mountArea(id) { mount(AreaPage, { id }); }
