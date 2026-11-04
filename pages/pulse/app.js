// Pulse: the live layer. The page and the brief are Markdown from the brain,
// drawn through Chat's renderer (pages/chat/markdown.js), which builds nodes
// and never parses HTML, so nothing in the text can inject markup.
//   GET  ${BRAIN_API}/api/pulse/page    Markdown, an HTML comment header first
//   GET  ${BRAIN_API}/api/pulse/brief   { date, body }
//   GET  ${BRAIN_API}/api/pulse/inlets  [{ id, status, schedule, last_run, summary }]
import { html, useState, useEffect, Badge, Empty, SkeletonRows, PageHead, mount } from "../../core/app/boot.js";
import { Markdown } from "../chat/markdown.js";
import "./app.css";

const API = (window.BRAIN_API || "") + "/api";
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const KIND = { live: "ok", ok: "ok", stub: "plain", error: "danger", stale: "warn" };

function useFetch(path, as) {
  const [state, set] = useState({ data: undefined, error: null });
  useEffect(() => {
    fetch(API + path).then((r) => {
      if (!r.ok) throw new Error(`${path} ${r.status}`);
      return as === "text" ? r.text() : r.json();
    }).then((data) => set({ data, error: null }), (error) => set({ data: null, error }));
  }, []);
  return state;
}

function Text({ state, pick, empty }) {
  if (state.data === undefined) return html`<${SkeletonRows} rows=${3} />`;
  if (state.error) return html`<p class="dim">Not available.</p>`;
  const text = pick(state.data);
  return text ? html`<${Markdown} text=${text} cls="pulse-prose" />` : html`<p class="dim">${empty}</p>`;
}

// The page opens with an HTML comment header for the brain; it is not content.
const pageText = (t) => String(t).replace(/^<!--[\s\S]*?-->\n?/, "").trim();

function Page() {
  const page = useFetch("/pulse/page", "text");
  const brief = useFetch("/pulse/brief");
  const inlets = useFetch("/pulse/inlets");
  const b = brief.data;
  return html`
    <${PageHead} title="Pulse" sub="Ephemeral and auto-ingested, kept out of the brain; its only durable output is L6 todos." />
    <div class="card pulse-block">
      <span class="card-title">Page</span>
      <${Text} state=${page} pick=${pageText} empty="The page is empty." />
    </div>
    <div class="card pulse-block">
      <span class="card-title">Today's brief</span>
      ${b && b.date && html`<p class="brief-date num">Generated ${b.date}</p>`}
      <${Text} state=${brief} pick=${(x) => x.body || ""} empty="No brief generated yet." />
    </div>
    <div class="card pulse-block">
      <span class="card-title">Inlets</span>
      ${inlets.data === undefined ? html`<${SkeletonRows} rows=${3} />`
        : inlets.error ? html`<p class="dim">Not available.</p>`
        : !inlets.data.length ? html`<${Empty} title="No inlets defined" />`
        : html`<div class="table-wrap"><table class="table">
            <thead><tr><th>Inlet</th><th>Status</th><th>Schedule</th><th>Last run</th><th>Summary</th></tr></thead>
            <tbody>${inlets.data.map((i) => html`<tr>
              <td class="mono">${i.id}</td>
              <td><${Badge} kind=${KIND[i.status] || "plain"}>${cap(i.status)}<//></td>
              <td class="mono">${i.schedule || "-"}</td>
              <td class="mono num">${i.last_run || "-"}</td>
              <td>${i.summary}</td>
            </tr>`)}</tbody></table></div>`}
    </div>
    ${(brief.error || page.error) && html`<p class="api-note">The pulse API did not answer. Check that the brain service is running, then reload this page.</p>`}`;
}

mount(Page);
