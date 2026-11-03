// Wages: g-wages' ledger editor, drawn in Command. g-wages keeps the data and
// every sum; this page renders what /api/wages (pages/wages/api.py, a gated
// proxy to g-wages' /api/ledger) returns and posts edits back. Money arrives
// formatted by g-wages, so nothing here re-derives a balance.
import { html, useState, useEffect, useCallback, PageHead, Badge, Button, Dialog, Field, Menu, Empty, ErrorState, SkeletonRows, toast, toastOk, toastError, mount } from "../../core/app/boot.js";
import "./app.css";

const API = "/api/wages";
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const INV_MODES = [["last_invoice", "Since last invoice"], ["last_payment", "Since last payment"],
  ["month", "Last 30 days"], ["last_x", "Last N days"], ["all", "All to date"]];

async function api(method, path, body) {
  const o = { method, credentials: "same-origin", headers: { "Content-Type": "application/json" } };
  if (body) o.body = JSON.stringify(body);
  const r = await fetch(API + path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("Signed out"); }
  let j = {};
  try { j = await r.json(); } catch { /* empty body */ }
  if (!r.ok) throw new Error(j.detail || `g-wages answered ${r.status}`);
  return j;
}

const dateOf = (ws, dow) => { const d = new Date(ws + "T00:00:00"); d.setDate(d.getDate() + dow); return d; };
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fmtRange = (ws) => { const a = dateOf(ws, 0), b = dateOf(ws, 6); return `${a.getDate()} ${MON[a.getMonth()]} to ${b.getDate()} ${MON[b.getMonth()]} ${b.getFullYear()}`; };
const pounds = (p) => (p < 0 ? "-" : "") + "£" + (Math.abs(p) / 100).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dsum = (day, kind) => day.entries.filter((e) => e.kind === kind).reduce((a, e) => a + e.amount_pence, 0);
const icon = (n) => html`<i class=${`ph ph-${n}`} aria-hidden="true"></i>`;

function Stat({ label, value, tone }) {
  return html`<div class="wg-stat"><span class="wg-stat-l">${label}</span><span class=${`wg-stat-v num ${tone || ""}`}>${value}</span></div>`;
}

/* The week as a grid: hours editable in place, everything else opens the day. */
function Grid({ week, onHours, onDay }) {
  const today = ymd(new Date());
  const t = week.totals;
  const cell = (d, v) => html`<td class=${`num wg-click ${v ? "" : "wg-nil"}`} onClick=${() => onDay(d.dow)}>${v ? pounds(v) : "None"}</td>`;
  return html`<div class="card wg-gridwrap"><table class="table wg-grid">
    <thead><tr><th></th>
      ${week.days.map((d) => { const dt = dateOf(week.week_start, d.dow); return html`
        <th class=${`wg-click ${ymd(dt) === today ? "wg-today" : ""}`} onClick=${() => onDay(d.dow)}>
          <span class="wg-dow">${DOW[d.dow]}</span><span class="wg-dnum">${dt.getDate()} ${MON[dt.getMonth()]}</span></th>`; })}
      <th class="wg-tot">Total</th></tr></thead>
    <tbody>
      <tr><td class="wg-lab">Hours</td>
        ${week.days.map((d) => html`<td class="wg-in"><input class="input input-sm num" type="number" step="0.25" min="0"
            aria-label=${`Hours on ${FULL[d.dow]}`} value=${d.centihours ? d.hours : ""} placeholder="0"
            onChange=${(e) => onHours(d.dow, e.target.value)} /></td>`)}
        <td class="num wg-tot">${t.hours}</td></tr>
      <tr><td class="wg-lab">Earned</td>
        ${week.days.map((d) => html`<td class=${`num ${d.centihours ? "" : "wg-nil"}`}>${d.centihours ? d.working_total : "None"}</td>`)}
        <td class="num wg-tot">${t.wages}</td></tr>
      <tr><td class="wg-lab">Paid in</td>${week.days.map((d) => cell(d, dsum(d, "paid_in")))}<td class="num wg-tot">${t.paid_in}</td></tr>
      <tr><td class="wg-lab">Expenses</td>${week.days.map((d) => cell(d, dsum(d, "expense")))}<td class="num wg-tot">${t.expenses}</td></tr>
      <tr><td class="wg-lab">Work</td>
        ${week.days.map((d) => { const n = (d.worklog || []).length, note = d.notes && d.notes.trim();
          return html`<td class=${`wg-click ${n || note ? "" : "wg-nil"}`} onClick=${() => onDay(d.dow)}>
            ${n ? html`<${Badge} kind="info" class="num">${n}<//>` : note ? html`<${Badge} kind="plain">Note<//>` : "None"}</td>`; })}
        <td class="wg-tot"></td></tr>
    </tbody></table></div>`;
}

/* One day: hours, the pulled work-log, free notes and the money entries. */
function DayDialog({ week, dow, onClose, onHours, onChanged }) {
  const d = week && dow != null ? week.days.find((x) => x.dow === dow) : null;
  const [kind, setKind] = useState("expense");
  const [amt, setAmt] = useState("");
  const [lbl, setLbl] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setAmt(""); setLbl(""); }, [dow]);
  if (!d) return html`<${Dialog} open=${false} onClose=${onClose} />`;
  const dt = dateOf(week.week_start, dow);
  const locked = week.locked;
  const add = async () => {
    const amount = parseFloat(amt || "0");
    if (!amount) { toast({ title: "Enter an amount first", kind: "warn" }); return; }
    setBusy(true);
    try { await api("POST", `/c/${encodeURIComponent(week.slug)}/entry`, { week_start: week.week_start, dow, kind, amount, label: lbl }); toastOk("Entry added"); setAmt(""); setLbl(""); await onChanged(); }
    catch (e) { toastError(e, "Entry not added"); } finally { setBusy(false); }
  };
  const del = async (id) => {
    try { await api("DELETE", `/c/${encodeURIComponent(week.slug)}/entry/${id}`); toastOk("Entry removed"); await onChanged(); }
    catch (e) { toastError(e, "Entry not removed"); }
  };
  const saveNotes = async (notes) => {
    try { await api("POST", `/c/${encodeURIComponent(week.slug)}/notes`, { week_start: week.week_start, dow, notes }); toastOk("Note saved"); await onChanged(); }
    catch (e) { toastError(e, "Note not saved"); }
  };
  return html`<${Dialog} open=${true} onClose=${onClose} size="md" title=${FULL[dow]}
      desc=${`${dt.getDate()} ${MON[dt.getMonth()]} ${dt.getFullYear()}, ${locked ? "locked" : "active"} week`}>
    <div class="wg-day">
      <${Field} label="Hours worked" hint=${`Earned ${d.working_total}`} id="wg-dh">
        <input id="wg-dh" class="input num" type="number" step="0.25" min="0" value=${d.centihours ? d.hours : ""} placeholder="0"
          onChange=${(e) => onHours(dow, e.target.value)} />
      <//>
      <section><div class="label">Work completed</div>
        ${(d.worklog || []).length ? html`<ul class="wg-work">${d.worklog.map((x) => html`
          <li><${Badge} kind=${x.major ? "info" : "plain"}>${x.label}<//><span>${x.summary}</span></li>`)}</ul>`
          : html`<p class="wg-muted">No commits logged for this day.</p>`}
      </section>
      <${Field} label="Notes" hint="Calls, research and other work without commits. Folds into the report under this day." id="wg-dn">
        <textarea id="wg-dn" class="input wg-notes" value=${d.notes || ""} onChange=${(e) => saveNotes(e.target.value)}></textarea>
      <//>
      <section><div class="label">Money</div>
        ${d.entries.length ? html`<table class="table wg-money"><tbody>${d.entries.map((e) => html`<tr>
            <td>${e.label || (e.kind === "paid_in" ? "Payment" : "Expense")}</td>
            <td class=${`num ${e.kind === "paid_in" ? "wg-pos" : "wg-neg"}`}>${e.kind === "paid_in" ? "+" : "-"}${e.amount}</td>
            <td class="wg-x">${!locked && html`<button class="btn btn-tertiary btn-sm btn-icon" type="button" aria-label="Remove entry" data-tip="Remove entry" onClick=${() => del(e.id)}>${icon("x")}</button>`}</td>
          </tr>`)}</tbody></table>` : html`<p class="wg-muted">No payments or expenses.</p>`}
        ${!locked && html`<div class="wg-add">
          <select class="select input" value=${kind} onChange=${(e) => setKind(e.target.value)} aria-label="Entry kind">
            <option value="expense">Expense, you paid</option><option value="paid_in">Paid in</option></select>
          <input class="input num" type="number" step="0.01" min="0" placeholder="£" value=${amt} onInput=${(e) => setAmt(e.target.value)} aria-label="Amount" />
          <input class="input wg-span" placeholder="Label, for example Cloudflare" value=${lbl} onInput=${(e) => setLbl(e.target.value)} aria-label="Label" />
          <${Button} kind="secondary" class="wg-span" busy=${busy} onClick=${add}>Add entry<//>
        </div>`}
      </section>
    </div>
  <//>`;
}

/* A locked week takes hour changes only as amendments with a reason. */
function ReasonDialog({ pending, onClose, onSave }) {
  const [reason, setReason] = useState("");
  useEffect(() => setReason(""), [pending]);
  return html`<${Dialog} open=${!!pending} onClose=${onClose} size="sm" title="Amend a locked week"
      desc="Money in a locked week is frozen. The hours change is recorded as an amendment with this reason."
      foot=${html`<button class="btn btn-secondary" type="button" onClick=${onClose}>Cancel</button>
        <button class="btn btn-primary" type="button" disabled=${!reason.trim()} onClick=${() => onSave(reason.trim())}>Record amendment</button>`}>
    <${Field} label="Reason" id="wg-reason"><input id="wg-reason" class="input" value=${reason} onInput=${(e) => setReason(e.target.value)} /><//>
  <//>`;
}

const BLANK = { name: "", repo: "", rate: "", open: "0", recv: "" };
function ClientDialog({ open, onClose, onCreated }) {
  const [f, setF] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setF(BLANK); }, [open]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    const body = { name: f.name.trim(), repo: f.repo.trim(), opening_balance: parseFloat(f.open || "0") };
    if (f.rate !== "") body.rate = parseFloat(f.rate);
    if (f.recv.trim()) body.receiver_rsync = f.recv.trim();
    setBusy(true);
    try { const c = await api("POST", "/clients", body); toastOk("Client added", c.name); onCreated(c.slug); }
    catch (e) { toastError(e, "Client not added"); } finally { setBusy(false); }
  };
  return html`<${Dialog} open=${open} onClose=${onClose} size="sm" title="Add a client" busy=${busy}
      foot=${html`<button class="btn btn-secondary" type="button" onClick=${onClose}>Cancel</button>
        <${Button} kind="primary" busy=${busy} disabled=${!f.name.trim()} onClick=${save}>Add client<//>`}>
    <${Field} label="Name" id="wc-n"><input id="wc-n" class="input" placeholder="Acme Co" value=${f.name} onInput=${set("name")} /><//>
    <${Field} label="GitHub repo" optional hint="owner/name. Leave blank to log work by hand." id="wc-r"><input id="wc-r" class="input" placeholder="Volcanex/acme" value=${f.repo} onInput=${set("repo")} /><//>
    <${Field} label="Rate per hour, £" optional id="wc-p"><input id="wc-p" class="input num" type="number" step="0.5" value=${f.rate} onInput=${set("rate")} /><//>
    <${Field} label="Opening balance, £" hint="Owed before week one." id="wc-o"><input id="wc-o" class="input num" type="number" step="0.01" value=${f.open} onInput=${set("open")} /><//>
    <${Field} label="Receiver rsync" optional hint="Where the daily report is pushed." id="wc-x"><input id="wc-x" class="input" value=${f.recv} onInput=${set("recv")} /><//>
  <//>`;
}

/* Invoice period, the open link, the issued mark, and the doubts behind it.
   The checks are ours, never the client's, so they live here and not on the invoice. */
function Invoices({ slug, refreshKey, onMarked }) {
  const [mode, setMode] = useState("last_invoice");
  const [days, setDays] = useState(30);
  const [current, setCurrent] = useState(false);
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const q = `mode=${encodeURIComponent(mode)}&days=${days || 30}&current=${current ? 1 : 0}`;
  const base = `/c/${encodeURIComponent(slug)}`;
  const load = useCallback(async () => {
    try { setSt(await api("GET", `${base}/invoice/status?${q}`)); } catch { setSt(null); }
  }, [base, q]);
  useEffect(() => { load(); }, [load, refreshKey]);
  const mark = async () => {
    setBusy(true);
    const un = st && st.marked;
    try {
      const r = await api("POST", `${base}/invoice/${un ? "unmark" : "mark"}`, { mode, days: days || 30, current });
      toastOk(un ? "Invoice unmarked" : "Invoice marked", `Through ${r.period_end}`);
      await load(); onMarked();
    } catch (e) { toastError(e, un ? "Invoice not unmarked" : "Invoice not marked"); } finally { setBusy(false); }
  };
  const checks = [];
  if (st && st.empty) checks.push(html`<b>No new work in this period.</b> The amount is a brought-forward balance that was already invoiced, so sending it bills the same work twice. Include this week to see work in progress.`);
  if (st && st.paid_after_pence) checks.push(html`<b>${pounds(st.paid_after_pence)} paid after ${st.period_end}.</b> The invoice shows ${pounds(st.due_pence)}, the balance at period end. Outstanding today is <b>${pounds(st.due_now_pence)}</b>.`);
  if (current) checks.push(html`<b>Unsettled week included.</b> These figures can still move before Sunday, and the invoice does not say so.`);
  return html`<section class="card wg-inv">
    <div class="card-head"><div class="card-title">Invoice</div>
      ${st && html`<${Badge} kind=${st.marked ? "ok" : "plain"}>${st.marked ? `Marked ${st.issued_on}` : "Not marked"}<//>`}</div>
    <div class="wg-inv-row">
      <select class="select input input-sm" value=${mode} onChange=${(e) => setMode(e.target.value)} aria-label="Invoice period">
        ${INV_MODES.map(([v, l]) => html`<option value=${v}>${l}</option>`)}</select>
      ${mode === "last_x" && html`<input class="input input-sm num wg-days" type="number" min="1" value=${days} onInput=${(e) => setDays(parseInt(e.target.value, 10) || 0)} aria-label="Days" />`}
      <label class="wg-check"><input type="checkbox" class="checkbox" checked=${current} onChange=${(e) => setCurrent(e.target.checked)} />Include this week</label>
    </div>
    ${st && html`<div class="wg-inv-sum"><${Stat} label="Period ends" value=${st.period_end} /><${Stat} label="Due" value=${pounds(st.due_pence)} /></div>`}
    ${checks.map((c) => html`<div class="wg-checkmsg">${icon("warning")}<div>${c}</div></div>`)}
    <div class="wg-inv-row">
      <a class="btn btn-primary btn-sm" href=${`${API}${base}/invoice?${q}`} target="_blank" rel="noopener">${icon("file-text")}<span>Open invoice</span></a>
      <${Button} kind="secondary" size="sm" busy=${busy} onClick=${mark}>${st && st.marked ? "Unmark invoice" : "Mark invoiced"}<//>
    </div>
  </section>`;
}

/* Every invoice marked as issued, newest first. */
function Issued({ slug, refreshKey }) {
  const [list, setList] = useState(null);
  useEffect(() => {
    let live = true;
    api("GET", `/c/${encodeURIComponent(slug)}/invoices`).then((j) => live && setList(j.invoices), () => live && setList([]));
    return () => { live = false; };
  }, [slug, refreshKey]);
  return html`<section class="card wg-issued"><div class="card-title">Invoices issued</div>
    ${list == null ? html`<${SkeletonRows} rows=${2} height=${24} />` : list.length ? html`<table class="table"><thead><tr>
        <th>Issued</th><th>Period</th><th class="num">Hours</th><th class="num">Earned</th><th class="num">Expenses</th><th class="num">Due</th></tr></thead><tbody>
        ${list.map((i) => html`<tr><td class="num">${i.issued_on}</td><td class="num">${i.period_start || i.since_date} to ${i.period_end}</td>
          <td class="num">${(i.centihours / 100).toFixed(2)}</td><td class="num">${pounds(i.earned_pence)}</td>
          <td class="num">${pounds(i.expenses_pence)}</td><td class="num">${pounds(i.due_pence)}</td></tr>`)}</tbody></table>`
      : html`<p class="wg-muted">No invoices marked yet.</p>`}
  </section>`;
}

function Wages() {
  const [clients, setClients] = useState(null);
  const [slug, setSlug] = useState("");
  const [weeks, setWeeks] = useState([]);
  const [float, setFloat] = useState("");
  const [idx, setIdx] = useState(0);
  const [week, setWeek] = useState(null);
  const [error, setError] = useState(null);
  const [dayOpen, setDayOpen] = useState(null);
  const [pending, setPending] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [rev, setRev] = useState(0);
  const lapi = (m, p, b) => api(m, `/c/${encodeURIComponent(slug)}${p}`, b);

  const loadClients = useCallback(async (want) => {
    try {
      const cs = (await api("GET", "/clients")).clients || [];
      setClients(cs);
      let saved = want || "";
      try { saved = saved || localStorage.getItem("wages-client") || ""; } catch { /* storage off */ }
      setSlug(cs.find((c) => c.slug === saved) ? saved : cs[0] ? cs[0].slug : "");
    } catch (e) { setError(e); }
  }, []);
  useEffect(() => { loadClients(); }, []);

  const loadWeeks = useCallback(async (keep) => {
    if (!slug) return [];
    const d = await api("GET", `/c/${encodeURIComponent(slug)}/weeks`);
    setFloat(d.float); setWeeks(d.weeks);
    if (!keep) setIdx(0);
    setRev((r) => r + 1);
    return d.weeks;
  }, [slug]);
  useEffect(() => {
    if (!slug) return;
    try { localStorage.setItem("wages-client", slug); } catch { /* storage off */ }
    setWeek(null);
    loadWeeks(false).catch(setError);
  }, [slug]);

  const ws = weeks[idx] && weeks[idx].week_start;
  const loadWeek = useCallback(async () => {
    if (!ws) { setWeek(null); return; }
    try { setWeek({ ...(await lapi("GET", `/week/${ws}`)), slug }); setError(null); } catch (e) { setError(e); }
  }, [slug, ws]);
  useEffect(() => { loadWeek(); }, [loadWeek, rev]);

  const refresh = async () => { await loadWeeks(true); };
  const saveHours = async (dow, val, reason = "") => {
    if (week.locked && !reason) { setPending({ dow, val }); return; }
    try {
      const r = await lapi("POST", "/hours", { week_start: week.week_start, dow, hours: parseFloat(val || "0"), reason });
      setFloat(r.float); toastOk("Hours saved"); await refresh();
    } catch (e) { toastError(e, "Hours not saved"); loadWeek(); }
  };
  const thisWeek = async () => {
    try {
      const w = await lapi("POST", "/current");
      const list = await loadWeeks(false);
      const i = list.findIndex((x) => x.week_start === w.week_start);
      setIdx(i < 0 ? 0 : i);
    } catch (e) { toastError(e, "This week did not open"); }
  };
  const pull = async () => {
    setPulling(true);
    try { const r = await lapi("POST", "/generate", { week_start: week ? week.week_start : "" }); toastOk("Work-log pulled", `${r.items} work items`); await refresh(); }
    catch (e) { toastError(e, "Work-log not pulled"); } finally { setPulling(false); }
  };

  if (error && !clients) return html`<${PageHead} title="Wages" /><${ErrorState} error=${error} retry=${() => { setError(null); loadClients(); }} />`;
  if (!clients) return html`<${PageHead} title="Wages" /><${SkeletonRows} rows=${6} />`;
  const client = clients.find((c) => c.slug === slug);
  const enc = encodeURIComponent(slug);
  const t = week && week.totals;

  return html`
    <${PageHead} title="Wages" sub="The ledger, invoices and reports from g-wages, one client at a time.">
      ${clients.length > 0 && html`<select class="select input input-sm wg-client" value=${slug} onChange=${(e) => setSlug(e.target.value)} aria-label="Client">
        ${clients.map((c) => html`<option value=${c.slug}>${c.name}, ${c.float} owed</option>`)}</select>`}
      <button class="btn btn-secondary btn-sm" type="button" onClick=${() => setAddOpen(true)}>${icon("plus")}<span>Add client</span></button>
      ${client && html`<${Menu} label="Reports" icon="dots-three" items=${[
        { label: "Open report", href: `${API}/c/${enc}/report`, target: "_blank" },
        { label: "Open hours basis", href: `${API}/c/${enc}/sessions/basis`, target: "_blank" },
        { label: "Print this week", onClick: () => window.print() },
      ]} />`}
    <//>
    ${!clients.length ? html`<${Empty} title="No clients yet" desc="Add a client to start a ledger."><button class="btn btn-primary btn-sm" type="button" onClick=${() => setAddOpen(true)}>Add client</button><//>` : html`
    <div class="wg-top">
      <section class="card wg-hero">
        <div class="label">Outstanding for ${client ? client.name : ""}</div>
        <div class="wg-big num">${float || "None"}</div>
        <p class="wg-muted">Owed to you, all time.</p>
        ${t && html`<div class="wg-stats">
          <${Stat} label="Hours" value=${`${t.hours} h`} /><${Stat} label="Earned" value=${t.wages} />
          <${Stat} label="Paid in" value=${t.paid_in} /><${Stat} label="Expenses" value=${t.expenses} tone=${t.expenses !== "£0.00" ? "wg-neg" : ""} />
        </div>`}
      </section>
      ${t && html`<section class="card wg-tape"><div class="card-title">Carried forward</div>
        <table class="table kv-table"><tbody>
          <tr><td>This week</td><td class="num">${t.hours} h</td></tr>
          <tr><td>Earned</td><td class="num">${t.wages}</td></tr>
          <tr><td>Net paid in</td><td class="num">${t.net_paid_in}</td></tr>
          <tr><td>Previous</td><td class="num">${t.prev_overdue}</td></tr>
          <tr class="wg-sum"><td>Carried</td><td class="num">${t.net_overdue}</td></tr>
        </tbody></table></section>`}
      ${slug && html`<${Invoices} slug=${slug} refreshKey=${rev} onMarked=${() => setRev((r) => r + 1)} />`}
    </div>

    <div class="wg-weekbar">
      <button class="btn btn-secondary btn-sm btn-icon" type="button" aria-label="Previous week" data-tip="Previous week" disabled=${idx >= weeks.length - 1} onClick=${() => setIdx(idx + 1)}>${icon("caret-left")}</button>
      <span class="wg-range num">${ws ? fmtRange(ws) : "No weeks yet"}</span>
      <button class="btn btn-secondary btn-sm btn-icon" type="button" aria-label="Next week" data-tip="Next week" disabled=${idx <= 0} onClick=${() => setIdx(idx - 1)}>${icon("caret-right")}</button>
      ${week && html`<${Badge} kind=${week.locked ? "plain" : "info"}>${week.locked ? "Locked" : "Active"}<//>`}
      <span class="wg-flex"></span>
      <button class="btn btn-secondary btn-sm" type="button" onClick=${thisWeek}>Open this week</button>
      <${Button} kind="secondary" size="sm" busy=${pulling} disabled=${!week} onClick=${pull}>Pull work-log<//>
    </div>
    ${error && html`<${ErrorState} error=${error} retry=${() => { setError(null); loadWeek(); }} />`}
    ${!weeks.length ? html`<${Empty} title="No weeks yet" desc="Open this week to start the ledger for this client." />`
      : week ? html`<${Grid} week=${week} onHours=${saveHours} onDay=${setDayOpen} />
        <p class="wg-muted wg-hint">${week.locked ? "Locked week. Editing hours records an amendment, and money is frozen." : `Active week, edit freely. Rate ${week.rate} an hour.`}</p>`
      : html`<${SkeletonRows} rows=${5} />`}
    ${slug && html`<${Issued} slug=${slug} refreshKey=${rev} />`}`}

    <${DayDialog} week=${week} dow=${dayOpen} onClose=${() => setDayOpen(null)} onHours=${saveHours} onChanged=${refresh} />
    <${ReasonDialog} pending=${pending} onClose=${() => { setPending(null); loadWeek(); }}
      onSave=${(reason) => { const p = pending; setPending(null); saveHours(p.dow, p.val, reason); }} />
    <${ClientDialog} open=${addOpen} onClose=${() => setAddOpen(false)}
      onCreated=${(s) => { setAddOpen(false); loadClients(s); }} />`;
}

mount(Wages);
