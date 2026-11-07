import { html, PageHead, Loaded, Empty, ErrorState, SkeletonRows, Badge, Button, CopyButton,
  mount, useJson, useState, useEffect } from "../../core/app/boot.js";
import "./app.css";

const rooms = ["overview", "pool", "decisions", "staging", "creative", "events", "orders"];
const label = (s) => String(s || "").replaceAll("_", " ").replaceAll("-", " ").replace(/^./, (c) => c.toUpperCase());
const plain = (s) => window.g?.plain ? window.g.plain(String(s ?? "")) : String(s ?? "");
const money = (p) => new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(p / 100);
const date = (ts) => ts ? new Date(ts * 1000).toLocaleString("en-GB") : "Not recorded";
const link = (room, extra = {}) => "/haln?" + new URLSearchParams({ room, ...extra });
const itemLink = (id) => link("pool", { item: id });
const shop = "https://haln.gabrielpenman.com";
const admin = "https://admin.haln.gabrielpenman.com/reports";
const safeUrl = (s) => /^https?:\/\//i.test(String(s));

function Status({ value }) {
  const kind = ["live", "pass", "paid", "staging-complete"].includes(value) ? "ok"
    : ["failed", "fail"].includes(value) ? "danger" : "plain";
  return html`<${Badge} kind=${kind}>${label(value || "unreviewed")}<//>`;
}

function Value({ value }) {
  if (value == null || value === "") return html`<span class="haln-muted">Not recorded</span>`;
  if (Array.isArray(value)) return value.length ? html`<ul class="haln-list">${value.map((v, i) => html`<li key=${i}><${Value} value=${v} /></li>`)}</ul>` : html`<span class="haln-muted">None recorded</span>`;
  if (typeof value === "object") return html`<dl class="haln-data">${Object.entries(value).map(([k, v]) => html`<div key=${k}><dt>${label(k)}</dt><dd><${Value} value=${v} /></dd></div>`)}</dl>`;
  if (safeUrl(value)) return html`<a href=${String(value)} target="_blank" rel="noopener noreferrer">${plain(value)}</a>`;
  return html`<span class="haln-value">${plain(value)}</span>`;
}

function Blank({ title, desc }) {
  return html`<${Empty} title=${title} desc=${desc}><a class="btn btn-secondary btn-sm" href=${link("pool")}>Browse the pool</a><//>`;
}

function ItemTitle({ item }) {
  return html`<div class="haln-stack"><h3><a href=${itemLink(item.id)}>${plain(item.title)}</a></h3>
    <div class="haln-meta"><span class="num">#${item.id}</span><${Status} value=${item.status} />
      ${item.data.fulfilment_status && html`<span>${label(item.data.fulfilment_status)}</span>`}</div></div>`;
}

function ItemRows({ items }) {
  return html`<div class="card haln-card haln-rows">${items.map((item) => html`<article class="haln-row" key=${item.id}>
    <${ItemTitle} item=${item} />
    <div class="haln-stack"><span class="haln-muted">Evidence</span><span class="num">${item.evidence_tiers.measured} measured<br />${item.evidence_tiers.review} review</span></div>
    <div class="haln-stack"><span class="haln-muted">${item.status === "candidate" ? "Next step" : "Price"}</span>
      <span class="num">${item.status === "candidate" ? plain(item.data.graduation_requirement || "No requirement recorded") : item.data.price_pence != null ? money(item.data.price_pence) : "Not set"}</span>
      ${item.data.demand_uk_monthly != null && html`<span class="haln-muted num">${item.data.demand_uk_monthly} UK demand / month</span>`}</div>
  </article>`)}</div>`;
}

function Pool({ data, initialStatus }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState(initialStatus || "");
  const statuses = [...new Set(data.items.map((i) => i.status))].sort();
  const items = data.items.filter((i) => (!status || i.status === status) && `${i.title} ${i.id} ${i.source_key}`.toLowerCase().includes(query.toLowerCase()));
  return html`<div class="haln-stack"><div class="haln-tools">
    <input class="input" type="search" aria-label="Search pool" placeholder="Search products or source keys" value=${query} onInput=${(e) => setQuery(e.target.value)} />
    <select class="select" aria-label="Filter pool status" value=${status} onChange=${(e) => setStatus(e.target.value)}><option value="">All statuses</option>${statuses.map((s) => html`<option value=${s}>${label(s)}</option>`)}</select>
    <span class="haln-muted num">${items.length} of ${data.items.length} items</span>
  </div>${items.length ? html`<${ItemRows} items=${items} />` : html`<${Empty} title="No matching items" desc="Clear the search or status filter to see the pool."><${Button} onClick=${() => { setQuery(""); setStatus(""); }}>Clear filters<//><//>`}</div>`;
}

function Events({ items }) {
  if (!items.length) return html`<${Blank} title="No events recorded" desc="Pool activity will appear here when the shop records it." />`;
  return html`<div class="card haln-card haln-rows">${items.map((e) => html`<article class="haln-row" key=${e.id}>
    <div><h3>${label(e.event_type)}</h3><${Value} value=${e.data} /></div>
    <div>${e.item_id != null ? html`<a href=${itemLink(e.item_id)}>View item #${e.item_id}</a>` : "Shop event"}</div>
    <time class="haln-muted num" datetime=${new Date(e.ts * 1000).toISOString()}>${date(e.ts)}</time>
  </article>`)}</div>`;
}

function Overview({ data }) {
  const stages = [...new Set(["candidate", "evidence_mined", "floor_verified", "listed", "live", ...Object.keys(data.by_status)])];
  return html`<div class="haln-stack">
    <div class="haln-grid">${[["Pool items", data.total_items], ["Locked items", data.locked_items], ["Failed items", data.failed_items], ["Sourcing decisions", data.decisions.length]].map(([name, n]) => html`<div class="card haln-card haln-stack"><span class="haln-muted">${name}</span><strong class="haln-metric num">${n}</strong></div>`)}</div>
    <section class="card haln-card haln-stack"><h2>Live pipeline</h2><div class="haln-pipeline">${stages.map((s) => html`<a href=${link("pool", { status: s })}><span>${label(s)}</span><strong class="num">${data.by_status[s] || 0}</strong></a>`)}</div>
      <p class="haln-muted num">${data.candidates_count} candidates have a graduation requirement. Refreshed ${date(data.now)}.</p></section>
    <section class="card haln-card haln-stack"><h2>Sourcing decisions</h2>${data.decisions.length ? html`<div class="haln-stack">${data.decisions.slice(0, 2).map((i) => html`<${ItemTitle} item=${i} />`)}<a href=${link("decisions")}>Review all ${data.decisions.length} decisions</a></div>` : html`<p class="haln-muted">No sourcing decisions are pending.</p>`}</section>
    <h2 class="label">Latest five events</h2><${Events} items=${data.last_events} />
  </div>`;
}

function Decisions({ data }) {
  if (!data.items.length) return html`<${Blank} title="No sourcing decisions pending" desc="Items awaiting a supplier or sourcing decision will appear here." />`;
  return html`<div class="haln-stack">${data.items.map((item) => html`<section class="card haln-card haln-stack"><${ItemTitle} item=${item} />
    <p>${item.data.fulfilment_status === "rfq_pending" ? "Send a supplier RFQ using the drafts in the fulfilment note." : "Find a UK-warehoused supplier before this item can list."}</p>
    <${Value} value=${Object.fromEntries(["cost_note", "cj_uk_sweep", "compliance"].filter((k) => item.data[k]).map((k) => [k, item.data[k]]))} />
    <a href=${admin + "/note/findings/fulfilment-resolution-2026-07"} target="_blank" rel="noopener noreferrer">Read the fulfilment note</a>
  </section>`)}</div>`;
}

function Staging({ data }) {
  if (!data.items.length) return html`<${Blank} title="No catalogue items in staging" desc="Staging checks products with evidence mined, floor verified, listed or live status." />`;
  return html`<div class="haln-stack"><p class="haln-muted">${["staging-complete", "awaiting-seeds", "not-ready"].map((s) => `${label(s)}: ${data.items.filter((i) => i.overall === s).length}`).join(". ")}</p>
    ${data.items.map((item) => html`<section class="card haln-card haln-stack"><${ItemTitle} item=${item} /><div><${Status} value=${item.overall} /></div>
      <div class="haln-criteria">${item.criteria.map((c) => html`<span class=${c.ok ? "haln-ok" : ""} title=${c.detail}><i class=${`ph ph-${c.ok ? "check-circle" : "circle"}`} aria-hidden="true"></i> ${c.label}: ${c.detail}</span>`)}</div>
      <a href=${shop + "/p/" + item.id} target="_blank" rel="noopener noreferrer">Preview in shop</a></section>`)}
  </div>`;
}

function Media({ item }) {
  const assets = item.data.creative_assets || [];
  if (!assets.length) return html`<p class="haln-muted">No creative assets recorded. <a href=${link("staging")}>Check staging</a></p>`;
  return html`<div class="haln-media-grid">${assets.map((a, i) => html`<section class="card haln-card haln-stack" key=${i}>
    <div class="haln-meta"><span>${label(a.kind || "asset")} ${a.role ? "(" + label(a.role) + ")" : ""}</span><${Status} value=${a.review?.verdict} /></div>
    ${a.url ? a.is_video ? html`<video class="haln-media" controls preload="none" src=${a.url}></video>` : html`<img class="haln-media" loading="lazy" src=${a.url} alt=${`${plain(item.title)}, ${a.slug || a.kind || "creative asset"}`} />` : html`<p class="haln-muted">${a.dry_run ? "Dry run, no rendered file." : "The recorded file is unavailable."}</p>`}
    ${a.review?.issues?.length ? html`<${Value} value=${a.review.issues} />` : null}
    ${a.seed_source && html`<${Value} value=${a.seed_source} />`}
    ${a.supplier && html`<p class="haln-muted">${plain(a.supplier)}</p>`}
    ${a.n_frames && html`<span class="haln-muted num">${a.n_frames} turntable frames</span>`}
  </section>`)}</div>`;
}

function Creative({ data }) {
  if (!data.items.length) return html`<${Blank} title="No creative briefs recorded" desc="Drafted briefs and their rendered assets will appear here." />`;
  return html`<div class="haln-stack"><div class="haln-tools"><p class="haln-muted">Recorded briefs and assets for review. Nothing here posts automatically.</p><a class="btn btn-secondary btn-sm" href=${link("creative", { pack: "1" })}>Open prompt pack</a></div>
    ${data.items.map((item) => html`<section class="card haln-card haln-stack"><${ItemTitle} item=${item} />
      ${(item.data.creative_briefs || []).map((b, i) => html`<details><summary>Brief ${i + 1}: ${plain(b.hook || b.angle || b.status || "Recorded brief")}</summary><${Value} value=${b} /></details>`)}
      <${Media} item=${item} /></section>`)}
  </div>`;
}

function Item({ data }) {
  const item = data.item;
  const facts = ["floor_claim", "price_pence", "price_note", "demand_uk_monthly", "demand_note", "cost_note", "compliance", "graduation_requirement"];
  const other = Object.entries(item.data).filter(([k]) => ![...facts, "title", "creative_assets"].includes(k));
  return html`<div class="haln-stack"><section class="card haln-card haln-stack"><${ItemTitle} item=${item} />
    <dl class="haln-data">${facts.filter((k) => item.data[k] != null).map((k) => html`<div><dt>${label(k)}</dt><dd><${Value} value=${k === "price_pence" ? money(item.data[k]) : item.data[k]} /></dd></div>`)}</dl>
    ${item.shop_visible && html`<a href=${shop + "/p/" + item.id} target="_blank" rel="noopener noreferrer">Preview in shop</a>`}
    <${Value} value=${Object.fromEntries(["locked_by", "locked_until", "retry_count", "last_error", "failed_at"].filter((k) => item[k]).map((k) => [k, k.endsWith("_at") || k === "locked_until" ? date(item[k]) : item[k]]))} /></section>
    <section class="card haln-card haln-stack"><h2>Evidence and product data</h2>${other.map(([k, v]) => html`<details><summary>${label(k)}</summary><${Value} value=${v} /></details>`)}</section>
    <h2 class="label">Creative assets</h2><${Media} item=${item} />
    <h2 class="label">Item events, latest 200</h2><${Events} items=${data.events} />
  </div>`;
}

function Orders({ data }) {
  if (!data.items.length) return html`<${Blank} title="No orders recorded" desc="Orders will appear here after checkout, including orders made with the test gateway." />`;
  return html`<div class="card haln-card haln-rows">${data.items.map((o) => html`<article class="haln-row"><div><h3><a href=${link("orders", { order: o.token })}>${plain(o.name || o.email)}</a></h3><span class="haln-muted num">${date(o.created_ts)}</span></div><div><${Status} value=${o.status} /><p class="haln-muted">${label(o.gateway)} gateway</p></div><strong class="num">${money(o.total_pence)}</strong></article>`)}</div>`;
}

function Order({ data }) {
  const o = data.order;
  return html`<section class="card haln-card haln-stack"><h2>Order ${o.token.slice(0, 12)}</h2><div class="haln-meta"><${Status} value=${o.status} /><strong class="num">${money(o.total_pence)}</strong><span>${label(o.gateway)} gateway</span></div>
    <${Value} value=${{ name: o.name, email: o.email, created: date(o.created_ts), address: o.address, reference: o.reference || "Not recorded" }} />
    <h3>Order items</h3>${o.items.map((i) => html`<div class="haln-meta"><a href=${itemLink(i.item_id)}>${plain(i.title)}</a><span class="num">${i.qty} × ${money(i.price_pence)}</span></div>`)}
  </section>`;
}

function Pack({ data }) {
  if (!data.items.length) return html`<${Blank} title="No prompts available" desc="Create a creative brief in HALN before opening the prompt pack." />`;
  return html`<div class="haln-stack"><p class="haln-muted">Generate stills first, then turntables and video shots. Save each download with its recorded filename for ingestion.</p>
    ${data.items.map((e) => html`<section class="card haln-card haln-stack"><div class="haln-tools"><h2>${e.filename}</h2><${CopyButton} text=${e.prompt} label="Copy prompt" /></div><p class="haln-muted">${e.tool}</p><pre class="haln-prompt">${e.prompt}</pre>${e.note && html`<p>${e.note}</p>`}</section>`)}
  </div>`;
}

function Screen({ room, params, endpoint }) {
  const state = useJson(endpoint);
  useEffect(() => {
    if (room !== "overview") return;
    const timer = setInterval(() => { if (!document.hidden) state.reload(); }, 10000);
    return () => clearInterval(timer);
  }, [room, state.reload]);
  const body = (data) => {
    if (params.get("item")) return html`<${Item} data=${data} />`;
    if (params.get("order")) return html`<${Order} data=${data} />`;
    if (params.get("pack")) return html`<${Pack} data=${data} />`;
    if (room === "overview") return html`<${Overview} data=${data} />`;
    if (room === "pool") return html`<${Pool} data=${data} initialStatus=${params.get("status")} />`;
    if (room === "decisions") return html`<${Decisions} data=${data} />`;
    if (room === "staging") return html`<${Staging} data=${data} />`;
    if (room === "creative") return html`<${Creative} data=${data} />`;
    if (room === "orders") return html`<${Orders} data=${data} />`;
    return html`<div class="haln-stack"><div class="haln-tools"><label class="label" for="haln-event-type">Event type</label><select id="haln-event-type" class="select" value=${data.active_type} onChange=${(e) => { location.href = link("events", e.target.value ? { type: e.target.value } : {}); }}><option value="">All event types</option>${data.types.map((t) => html`<option value=${t}>${label(t)}</option>`)}</select><span class="haln-muted">Latest 100 matching events</span></div><${Events} items=${data.items} /></div>`;
  };
  return html`<${PageHead} title="HALN" sub=${params.get("item") ? "Product detail and evidence" : params.get("order") ? "Order detail" : params.get("pack") ? "Creative prompt pack" : `${label(room)} from the live HALN shop.`}>
    ${(params.get("item") || params.get("order") || params.get("pack")) && html`<a class="btn btn-tertiary btn-sm" href=${link(room)}>Back to ${room}</a>`}
    <${Button} size="sm" onClick=${state.reload}>Refresh<//>
  <//>
  <nav class="haln-nav" aria-label="HALN admin screens">${rooms.map((r) => html`<a class=${`btn btn-sm btn-${room === r ? "secondary" : "tertiary"}`} aria-current=${room === r ? "page" : undefined} href=${link(r)}>${label(r)}</a>`)}</nav>
  ${state.error && state.data !== undefined && html`<${ErrorState} error=${new Error("HALN could not refresh. The previous data is still shown. Try again.")} retry=${state.reload} />`}
  <${Loaded} state=${{ ...state, error: state.error ? new Error("HALN could not load this screen. Try again, or choose another admin screen.") : null }} skeleton=${html`<${SkeletonRows} rows=${4} />`}>${body}<//>`;
}

function Page() {
  const params = new URLSearchParams(location.search);
  const room = rooms.includes(params.get("room")) ? params.get("room") : "overview";
  const suffix = params.get("item") ? `/item/${encodeURIComponent(params.get("item"))}`
    : params.get("order") ? `/orders/${encodeURIComponent(params.get("order"))}`
    : params.get("pack") ? "/creative/pack" : room === "overview" ? "" : `/${room}`;
  const endpoint = "/api/haln" + suffix + (room === "events" && params.get("type") ? "?" + new URLSearchParams({ type: params.get("type") }) : "");
  return html`<${Screen} key=${endpoint} room=${room} params=${params} endpoint=${endpoint} />`;
}

mount(Page);
