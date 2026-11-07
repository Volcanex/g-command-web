import {
  html, mount, useState, useEffect, useJson, PageHead, Loaded, Empty,
  SkeletonRows, ErrorState, Button, Badge, Field, Dialog, Confirm, toastOk,
} from "../../core/app/boot.js";
import "./app.css";

const ROOT = "/api/resell";
const SECTIONS = { dashboard: "Dashboard", pool: "Pool", profit: "Profit", bots: "Bots" };
const STATUSES = ["scraped", "soft-enhanced", "rejected", "enhanced", "verified", "purchased", "listed", "failed", "real_captured", "real_verifying", "real_verified", "real_listing", "real_listed", "real_sold", "real_removed"];
const label = (text) => {
  const s = String(text ?? "").replace(/[_-]/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const plain = (value) => window.g?.plain ? window.g.plain(String(value ?? "")) : String(value ?? "").replace(/\*\*|`|\[\[|\]\]/g, "");
const title = (item) => plain(item.data?.title || item.data?.url || item.source_url || "Untitled item");
const date = (value) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("en-GB") : "Not recorded";
const numeric = (value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
const money = (value) => numeric(value) ? new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(value)) : "Not recorded";
const safeUrl = (value) => {
  try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) ? u.href : null; }
  catch { return null; }
};
const serviceLabel = (name) => label(name.replace(/^arbitrage_/, ""));

function route() {
  const p = new URLSearchParams(location.search);
  return { section: p.get("view") in SECTIONS ? p.get("view") : "dashboard", item: p.get("item") };
}
function navigate(section, item) {
  const params = new URLSearchParams({ view: section });
  if (item) params.set("item", item);
  history.pushState({}, "", `/resell?${params}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
async function write(path, method = "POST", body) {
  const response = await fetch(`${ROOT}/${path}`, {
    method, credentials: "same-origin", headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(typeof result.detail === "string" ? result.detail : "Resell could not save this change. Check the values and try again.");
  }
  return response.json();
}

// Keep failed refreshes visible: useJson retains the last successful response.
function Data({ state, children }) {
  const loaded = state.error ? { ...state, error: new Error("Resell could not load this view. Its service may be offline. Try again.") } : state;
  return html`<${Loaded} state=${loaded} skeleton=${html`<${SkeletonRows} rows=${4} />`}>
    ${(data) => html`<div class="resell-stack">
      ${state.error && html`<${ErrorState} error=${new Error("Resell could not refresh this view. The previous results are shown. Try again.")} retry=${state.reload} />`}
      ${children(data)}
    </div>`}
  <//>`;
}
function Metric({ name, value }) {
  return html`<div class="card resell-metric"><span class="resell-muted">${name}</span><strong class="num">${value}</strong></div>`;
}
function Table({ label: name, headers, children }) {
  return html`<div class="card resell-table"><table class="table" aria-label=${name}>
    <thead><tr>${headers.map((h) => html`<th key=${h}>${h}</th>`)}</tr></thead><tbody>${children}</tbody>
  </table></div>`;
}
function Refresh({ state }) {
  return html`<${Button} size="sm" onClick=${state.reload}>Refresh<//>`;
}
function Status({ value }) {
  return html`<${Badge} kind="plain">${label(value || "unknown")}<//>`;
}

function Dashboard() {
  const state = useJson(ROOT);
  return html`<${Data} state=${state}>${({ services }) => {
    const pool = services.find((s) => s.name === "pool");
    const registry = services.find((s) => s.name === "registry");
    const network = services.find((s) => s.name === "network");
    return html`
      <div class="resell-row resell-between"><span class="resell-muted">Current service status</span><${Refresh} state=${state} /></div>
      ${services.every((s) => !s.available) && html`<div class="card resell-notice">Resell's services are offline. Saved items and profit will be available when its data services are running. Use Refresh to check again.</div>`}
      <div class="resell-grid">
        <${Metric} name="Pool items" value=${pool.available ? pool.data.total_items : "Unavailable"} />
        <${Metric} name="Bot services" value=${registry.available ? registry.data.count : "Unavailable"} />
        <${Metric} name="Network" value=${network.available ? label(network.data.status || "unknown") : "Unavailable"} />
      </div>
      ${pool.available && html`<section class="resell-stack"><h2 class="card-title">Pool by status</h2>
        ${Object.keys(pool.data.by_status || {}).length ? html`<div class="card resell-row">
          ${Object.entries(pool.data.by_status).map(([status, count]) => html`<${Badge} key=${status} kind="plain">${label(status)}: ${count}<//>`)}
        </div>` : html`<${Empty} title="No pool items yet" desc="Open the pool to review its filters."><${Button} onClick=${() => navigate("pool")}>Open pool<//><//>`}
      </section>`}
      <${Table} label="Resell services" headers=${["Service", "Status"]}>
        ${services.map((service) => html`<tr key=${service.name}><td>${label(service.name)}</td><td><${Badge} kind=${service.available ? "ok" : "warn"}>${service.available ? "Available" : "Offline"}<//></td></tr>`)}
      <//>`;
  }}<//>`;
}

function Events() {
  const state = useJson(`${ROOT}/pool/events?limit=20`);
  return html`<section class="resell-stack"><div class="resell-row resell-between"><h2 class="card-title">Recent events</h2><${Refresh} state=${state} /></div>
    <${Data} state=${state}>${({ events = [] }) => events.length ? html`<${Table} label="Recent pool events" headers=${["Event", "Time", "Details"]}>
      ${events.map((event) => html`<tr key=${event._id}><td>${label(event.event_type)}</td><td>${date(event.timestamp)}</td><td><pre class="resell-code">${JSON.stringify(event.data || {}, null, 2)}</pre></td></tr>`)}
    <//>` : html`<${Empty} title="No recent events" desc="Refresh to check for new pool activity."><${Refresh} state=${state} /><//>`}<//>
  </section>`;
}
function Pool() {
  const [filter, setFilter] = useState("");
  const [size, setSize] = useState(10);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState([]);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const params = new URLSearchParams({ status: filter, page, page_size: size });
  const state = useJson(`${ROOT}/pool/items?${params}`);
  useEffect(() => setSelected([]), [filter, page, size]);
  const remove = async () => {
    const errors = [];
    for (const id of selected) {
      try { await write(`pool/items/${id}`, "DELETE"); }
      catch { errors.push(id); }
    }
    setSelected(errors);
    state.reload();
    if (errors.length) {
      setDeleteError(new Error(`${errors.length} items could not be deleted. They remain selected. Try again.`));
      throw new Error("Some items could not be deleted. Close this dialog to review the remaining selection.");
    }
    setDeleteError(null);
    toastOk("Deleted selected items");
  };
  return html`
    <div class="resell-row resell-between">
      <div class="resell-row">
        <${Field} label="Status" id="resell-status"><select class="select" id="resell-status" value=${filter} onChange=${(e) => { setFilter(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>${STATUSES.map((s) => html`<option key=${s} value=${s}>${label(s)}</option>`)}
        </select><//>
        <${Field} label="Items per page" id="resell-size"><select class="select" id="resell-size" value=${size} onChange=${(e) => { setSize(Number(e.target.value)); setPage(1); }}>
          ${[5, 10, 20, 50, 100].map((n) => html`<option key=${n} value=${n}>${n}</option>`)}
        </select><//>
      </div><${Refresh} state=${state} />
    </div>
    ${selected.length > 0 && html`<div class="resell-row"><span class="num">${selected.length} selected</span><${Button} kind="danger" size="sm" onClick=${() => setDeleting(true)}>Delete selected items<//></div>`}
    ${deleteError && html`<${ErrorState} error=${deleteError} retry=${() => setDeleting(true)} />`}
    <${Data} state=${state}>${({ items = [], total, total_pages }) => html`
      ${items.length ? html`<${Table} label="Pool items" headers=${["Select", "Item", "Status", "Created", "Locked by", "Actions"]}>
        <tr><td><input class="checkbox" type="checkbox" aria-label="Select all items on this page" checked=${items.every((i) => selected.includes(i._id))} onChange=${(e) => setSelected(e.target.checked ? items.map((i) => i._id) : [])} /></td><td colspan="5" class="resell-muted num">${total} items match</td></tr>
        ${items.map((item) => html`<tr key=${item._id}>
          <td><input class="checkbox" type="checkbox" aria-label=${`Select ${title(item)}`} checked=${selected.includes(item._id)} onChange=${(e) => setSelected(e.target.checked ? [...selected, item._id] : selected.filter((id) => id !== item._id))} /></td>
          <td class="resell-title"><a href=${`/resell?view=pool&item=${encodeURIComponent(item._id)}`} onClick=${(e) => { if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; e.preventDefault(); navigate("pool", item._id); }}>${title(item)}</a><div class="resell-muted mono">${item._id}</div></td>
          <td><${Status} value=${item.status} /></td><td>${date(item.created_at)}</td><td>${item.locked_by || "Unlocked"}</td>
          <td><${Button} size="sm" onClick=${() => navigate("pool", item._id)}>View details<//></td>
        </tr>`)}
      <//>` : html`<${Empty} title="No items match" desc="Clear the status filter or refresh to check again."><${Button} onClick=${() => { setFilter(""); setPage(1); state.reload(); }}>Clear filter<//><//>`}
      <div class="resell-row resell-between"><span class="num">Page ${page} of ${Math.max(1, total_pages || 0)}</span><div class="resell-row">
        <${Button} size="sm" disabled=${page <= 1} onClick=${() => setPage(page - 1)}>Previous page<//>
        <${Button} size="sm" disabled=${page >= (total_pages || 1)} onClick=${() => setPage(page + 1)}>Next page<//>
      </div></div>`}<//>
    <${Events} />
    <${Confirm} open=${deleting} onClose=${() => setDeleting(false)} onConfirm=${remove} danger title="Delete selected items?" desc=${`Permanently delete ${selected.length} selected items from Resell's pool. This cannot be undone.`} confirmLabel="Delete selected items" />`;
}

function Photo({ src, alt }) {
  const [failed, setFailed] = useState(false);
  if (failed) return html`<span class="resell-muted">Image unavailable</span>`;
  return html`<a href=${src} target="_blank" rel="noopener noreferrer"><img src=${src} alt=${alt} loading="lazy" onError=${() => setFailed(true)} /></a>`;
}
function Item({ id }) {
  const state = useJson(`${ROOT}/pool/items/${encodeURIComponent(id)}`);
  return html`<div class="resell-row resell-between"><${Button} onClick=${() => navigate("pool")}>Back to pool<//><${Refresh} state=${state} /></div>
    <${Data} state=${state}>${(item) => {
      const d = item.data || {};
      const source = safeUrl(item.source_url);
      const apparel = /^apparel\.item\.(\d+)$/.exec(item.source_url || "");
      const photos = [
        ...(Array.isArray(d.image_urls) ? d.image_urls.map(safeUrl).filter(Boolean) : []),
        ...(item.images || []).filter((im) => /^[a-fA-F0-9]{24}$/.test(im?.gridfs_id)).map((im) => `${ROOT}/pool/images/${im.gridfs_id}`),
      ];
      const fields = {
        Status: label(item.status), Source: item.source_url, Brand: d.brand || d.brand_name,
        Size: d.size, Colour: d.color, Material: d.material, Condition: d.depop_condition || d.condition,
        Category: d.category, Seller: d.seller, "Buy cost": money(d.purchase_cost_gbp),
        "Sold for": money(d.sold_price_gbp), "Profit": numeric(d.purchase_cost_gbp) && numeric(d.sold_price_gbp) ? money(Number(d.sold_price_gbp) - Number(d.purchase_cost_gbp)) : "Not recorded",
        "List readiness": d.verification ? (d.verification.list_ready ? "Ready" : `Needs ${(d.verification.missing_for_listing || []).join(", ")}`) : null,
        "Locked by": item.locked_by || "Unlocked", Created: date(item.created_at), Updated: date(item.updated_at),
      };
      return html`<section class="card resell-stack"><h2 class="card-title">${title(item)}</h2><div class="resell-muted mono">${item._id}</div>
        ${source && html`<a href=${source} target="_blank" rel="noopener noreferrer">Open source listing</a>`}
        ${apparel && html`<a href=${`https://apparel.gabrielpenman.com/item/${apparel[1]}`} target="_blank" rel="noopener noreferrer">Open item in Apparel</a>`}
        <dl class="resell-details">${Object.entries(fields).filter(([, v]) => v != null && v !== "").map(([k, v]) => html`<dt key=${k}>${k}</dt><dd>${plain(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`)}</dl>
        ${d.description && html`<div><h3 class="card-title">Description</h3><p class="resell-code">${d.description}</p></div>`}
        <div class="resell-photos">${photos.map((src) => html`<${Photo} key=${src} src=${src} alt=${title(item)} />`)}</div>
        ${(d.generated_images || []).map((generation, i) => html`<section class="resell-stack" key=${i}><h3 class="card-title">${label(generation.type || `Generation ${i + 1}`)}</h3><div class="resell-photos">
          ${Object.entries({ ...(generation.input_images || {}), result: generation.url }).filter(([, v]) => safeUrl(typeof v === "string" ? v : v?.url)).map(([key, value]) => html`<div key=${key}><p class="resell-muted">${label(key)}</p><${Photo} src=${safeUrl(typeof value === "string" ? value : value.url)} alt=${label(key)} /></div>`)}
        </div></section>`)}
        ${(d.generation_errors || []).length > 0 && html`<section><h3 class="card-title">Failed generations</h3>${d.generation_errors.map((error, i) => html`<details key=${i}><summary>${label(error.type || "Generation failed")}</summary><pre class="resell-code">${JSON.stringify(error, null, 2)}</pre></details>`)}</section>`}
        <details><summary>Raw item data</summary><pre class="resell-code">${JSON.stringify(item, null, 2)}</pre></details>
      </section>`;
    }}<//>`;
}

function Profit() {
  const state = useJson(`${ROOT}/profit`);
  return html`<div class="resell-row resell-between"><span class="resell-muted">All sold real stock, with frozen purchase cost</span><${Refresh} state=${state} /></div>
    <${Data} state=${state}>${({ items = [] }) => {
      if (!items.length) return html`<${Empty} title="No sold items yet" desc="Open the pool to review your stock."><${Button} onClick=${() => navigate("pool")}>Open pool<//><//>`;
      const basis = items.filter((i) => numeric(i.data?.sold_price_gbp) && numeric(i.data?.purchase_cost_gbp));
      const revenue = basis.reduce((sum, i) => sum + Number(i.data.sold_price_gbp), 0);
      const cost = basis.reduce((sum, i) => sum + Number(i.data.purchase_cost_gbp), 0);
      return html`<div class="resell-grid">
        <${Metric} name="Revenue" value=${money(revenue)} /><${Metric} name="Cost of goods" value=${money(cost)} />
        <${Metric} name="Profit" value=${money(revenue - cost)} /><${Metric} name="Margin" value=${revenue > 0 ? `${((revenue - cost) / revenue * 100).toFixed(1)}%` : "No revenue"} />
      </div><p class="resell-muted num">${basis.length} sold items with a frozen cost basis. ${items.length - basis.length} excluded from totals because sale price or cost is missing. Before fees and other expenses.</p>
      <${Table} label="Sold stock" headers=${["Item", "Cost", "Sold", "Profit", "Sold at"]}>
        ${items.map((item) => { const d = item.data || {}; return html`<tr key=${item._id}><td class="resell-title"><${Button} size="sm" onClick=${() => navigate("pool", item._id)}>${title(item)}<//></td>
          <td class="num">${money(d.purchase_cost_gbp)}</td><td class="num">${money(d.sold_price_gbp)}</td>
          <td class="num">${numeric(d.sold_price_gbp) && numeric(d.purchase_cost_gbp) ? money(Number(d.sold_price_gbp) - Number(d.purchase_cost_gbp)) : "No cost basis"}</td><td>${date(d.sold_at)}</td></tr>`; })}
      <//>`;
    }}<//>`;
}

function ConfigEditor({ service, onClose }) {
  const running = service.running_replicas > 0;
  const path = running ? `registry/bots/${encodeURIComponent(service.name)}/config` : `config/config/${encodeURIComponent(service.name)}`;
  const state = useJson(`${ROOT}/${path}`);
  const [text, setText] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const config = JSON.parse(text ?? JSON.stringify(state.data.config));
      if (!config || Array.isArray(config) || typeof config !== "object") throw new Error("Enter a JSON object for the configuration, then save again.");
      await write(path, "POST", config);
      toastOk("Saved configuration"); onClose();
    } catch (err) { setError(new Error(err instanceof SyntaxError ? "The configuration is not valid JSON. Correct it and save again." : err.message)); }
    finally { setBusy(false); }
  };
  return html`<${Dialog} open onClose=${onClose} busy=${busy} title=${`Edit ${serviceLabel(service.name)}`} size="lg"
    desc=${running ? "Save through the running bot to validate and reload its configuration." : "Save persistent configuration for this stopped service."}
    foot=${html`<${Button} onClick=${onClose} disabled=${busy}>Cancel<//><${Button} kind="primary" busy=${busy} disabled=${!state.data || !!state.error || busy} onClick=${save}>Save configuration<//>`}>
    <${Data} state=${state}>${(data) => html`<${Field} label="Configuration (JSON)" id="resell-config"><textarea id="resell-config" class="textarea resell-editor" spellcheck="false" value=${text ?? JSON.stringify(data.config, null, 2)} onInput=${(e) => setText(e.target.value)} /><//>`}<//>
    ${error && html`<${ErrorState} error=${error} />`}
  <//>`;
}
function Logs({ service, onClose }) {
  const [tail, setTail] = useState(100);
  const [auto, setAuto] = useState(false);
  const state = useJson(`${ROOT}/registry/bots/${encodeURIComponent(service.name)}/logs?tail=${tail}`);
  useEffect(() => { if (!auto) return; const timer = setInterval(() => { if (!document.hidden) state.reload(); }, 5000); return () => clearInterval(timer); }, [auto, state.reload]);
  return html`<${Dialog} open onClose=${onClose} title=${`Logs for ${serviceLabel(service.name)}`} size="lg">
    <div class="resell-stack"><div class="resell-row"><${Refresh} state=${state} />
      <select class="select" aria-label="Log lines" value=${tail} onChange=${(e) => setTail(Number(e.target.value))}>${[50, 100, 200, 500].map((n) => html`<option key=${n} value=${n}>Last ${n} lines</option>`)}</select>
      <label class="resell-choice"><input class="checkbox" type="checkbox" checked=${auto} onChange=${(e) => setAuto(e.target.checked)} />Refresh every 5 seconds</label>
    </div><${Data} state=${state}>${(data) => { const logs = data.lines || []; return logs.length ? html`<pre class="resell-code">${Array.isArray(logs) ? logs.map((l) => typeof l === "string" ? l : JSON.stringify(l)).join("\n") : logs}</pre>` : html`<${Empty} title="No logs yet" desc="Refresh to check for bot activity."><${Refresh} state=${state} /><//>`; }}<//></div>
  <//>`;
}
function Variant({ service, onClose, reload }) {
  const [name, setName] = useState("");
  const [replicas, setReplicas] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const create = async (e) => {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const params = new URLSearchParams({ base_service: service.name, variant_name: name, replicas });
      await write(`registry/services/create-variant?${params}`);
      toastOk("Created variant"); reload(); onClose();
    } catch (err) { setError(err); }
    finally { setBusy(false); }
  };
  return html`<${Dialog} open onClose=${onClose} busy=${busy} title="Create bot variant" desc=${`Use ${serviceLabel(service.name)} with a separate configuration. Zero replicas keeps the new service stopped.`}>
    <form class="resell-stack" onSubmit=${create}>
      <${Field} label="Variant name" id="resell-variant-name"><input id="resell-variant-name" class="input" required pattern="[a-zA-Z0-9_-]+" value=${name} onInput=${(e) => setName(e.target.value)} /><//>
      <${Field} label="Replicas" id="resell-variant-count"><input id="resell-variant-count" class="input" type="number" min="0" step="1" required value=${replicas} onInput=${(e) => setReplicas(e.target.value)} /><//>
      ${error && html`<${ErrorState} error=${error} />`}
      <div class="resell-row"><${Button} onClick=${onClose} disabled=${busy}>Cancel<//><${Button} type="submit" kind="primary" busy=${busy} disabled=${busy}>Create variant<//></div>
    </form>
  <//>`;
}
function Bots() {
  const state = useJson(`${ROOT}/bots`);
  const [dialog, setDialog] = useState(null);
  const [action, setAction] = useState(null);
  const run = async () => {
    await write(action.path, action.method);
    toastOk(action.success); state.reload();
  };
  return html`<div class="resell-row resell-between"><span class="resell-muted">Bot services and current tasks</span><${Refresh} state=${state} /></div>
    <${Data} state=${state}>${({ services = [], bots = [] }) => html`
      ${services.length ? html`<div class="resell-grid">${services.map((service) => html`<section class="card resell-stack" key=${service.name}>
        <div><h2 class="card-title">${serviceLabel(service.name)}</h2><p class="resell-muted num">${service.running_replicas} tasks, ${service.desired_replicas} desired replicas</p></div>
        <div class="resell-row">
          <${Button} size="sm" disabled=${service.desired_replicas === 0} onClick=${() => setAction({ title: "Stop one replica?", desc: `Set ${serviceLabel(service.name)} to ${service.desired_replicas - 1} replicas.`, path: `registry/bots/${encodeURIComponent(service.name)}/scale?count=${service.desired_replicas - 1}`, success: "Stopped one replica", label: "Stop one replica" })}>Stop one replica<//>
          <${Button} size="sm" onClick=${() => setAction({ title: "Start one replica?", desc: `Set ${serviceLabel(service.name)} to ${service.desired_replicas + 1} replicas. This starts the bot's automation.`, path: `registry/bots/${encodeURIComponent(service.name)}/scale?count=${service.desired_replicas + 1}`, success: "Started one replica", label: "Start one replica" })}>Start one replica<//>
          <${Button} size="sm" onClick=${() => setDialog({ type: "config", service })}>Edit configuration<//>
          ${service.running_replicas > 0 && html`<${Button} size="sm" onClick=${() => setDialog({ type: "logs", service })}>View logs<//>`}
          ${!service.name.includes("@") && html`<${Button} size="sm" onClick=${() => setDialog({ type: "variant", service })}>Create variant<//>`}
          ${service.labels?.["arbitrage-managed"] === "dynamic" && html`<${Button} size="sm" kind="danger" onClick=${() => setAction({ title: "Delete bot variant?", desc: `Delete ${serviceLabel(service.name)} from Resell.`, path: `registry/services/${encodeURIComponent(service.name)}`, method: "DELETE", success: "Deleted variant", label: "Delete variant", danger: true })}>Delete variant<//>`}
        </div>
      </section>`)}</div>` : html`<${Empty} title="No bot services found" desc="Refresh to check Resell's service registry."><${Refresh} state=${state} /><//>`}
      ${bots.length ? html`<${Table} label="Bot tasks" headers=${["Bot", "State", "Desired state", "Node", "Actions"]}>
        ${bots.map((bot) => html`<tr key=${bot.id}><td>${bot.id}</td><td><${Status} value=${bot.state} /></td><td>${label(bot.desired_state)}</td><td>${bot.node_id?.slice(0, 12) || "Unknown"}</td><td><${Button} size="sm" onClick=${() => setDialog({ type: "logs", service: { name: bot.service } })}>View logs<//></td></tr>`)}
      <//>` : html`<${Empty} title="No bots running" desc="Start a replica from its service controls when you want it to run." />`}
    `}<//>
    ${dialog?.type === "config" && html`<${ConfigEditor} service=${dialog.service} onClose=${() => setDialog(null)} />`}
    ${dialog?.type === "logs" && html`<${Logs} service=${dialog.service} onClose=${() => setDialog(null)} />`}
    ${dialog?.type === "variant" && html`<${Variant} service=${dialog.service} onClose=${() => setDialog(null)} reload=${state.reload} />`}
    <${Confirm} open=${!!action} title=${action?.title} desc=${action?.desc} danger=${action?.danger} confirmLabel=${action?.label} onClose=${() => setAction(null)} onConfirm=${run} />`;
}

function Page() {
  const [current, setCurrent] = useState(route);
  useEffect(() => { const update = () => setCurrent(route()); window.addEventListener("popstate", update); return () => window.removeEventListener("popstate", update); }, []);
  return html`<${PageHead} title="Resell" sub="Pool, profit and bot controls for Resell." />
    <nav class="resell-nav" aria-label="Resell screens">${Object.entries(SECTIONS).map(([key, name]) => html`<a key=${key} class=${`btn btn-sm ${current.section === key ? "btn-primary" : "btn-secondary"}`} aria-current=${current.section === key ? "page" : undefined} href=${`/resell?view=${key}`} onClick=${(e) => { if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; e.preventDefault(); navigate(key); }}>${name}</a>`)}</nav>
    ${current.item && current.section === "pool" ? html`<${Item} key=${current.item} id=${current.item} />` : current.section === "pool" ? html`<${Pool} />` : current.section === "profit" ? html`<${Profit} />` : current.section === "bots" ? html`<${Bots} />` : html`<${Dashboard} />`}`;
}
mount(Page);
