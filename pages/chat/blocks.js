// A reply's blocks (core/panels/CLAUDE.md, "Blocks"), drawn in Preact. The
// server decides every word, order and tone; this only lays them out, as the
// dash's renderer (pages/full-dash/panels/kit.html) and the apps' ReplyBlocks
// do. Rows, lines and meters that follow one another share a card. Unknown
// block types are skipped, so a new type can ship server first.
import { html, useState, useRef, useGInit, toast } from "../../core/app/boot.js";

const TONES = new Set(["ok", "warn", "danger", "accent", "muted", "plain", "chart-1", "chart-2", "chart-3", "chart-4", "chart-5", "chart-6"]);
const BADGE = { ok: "badge-ok", warn: "badge-warn", danger: "badge-danger", accent: "badge-info" };
const tone = (t) => (TONES.has(t) ? t : "plain");
// Only command paths: a link that is not one is dropped, never followed.
const path = (p) => (typeof p === "string" && p[0] === "/" && p[1] !== "/" ? p : "");
const iconName = (n) => String(n).toLowerCase().replace(/[^a-z0-9-]/g, "");
// Agent cards can carry em dashes and middle dots between facts; g.tidy swaps them for display.
const tidy = (s) => (window.g && window.g.tidy ? window.g.tidy(s) : s);
const plain = (s) => tidy(window.g && window.g.plain ? window.g.plain(String(s ?? "")) : String(s ?? ""));

function Chip({ c, cls = "" }) {
  if (!c) return null;
  const t = tone(c.tone);
  const klass = c.badge ? `badge ${BADGE[t] || "badge-plain"}` : `cb-chip cb-tone-${t}`;
  return html`<span class=${`${klass} ${cls}`} data-tip=${c.tip || null} aria-label=${c.icon && !c.text ? c.tip || c.icon : null}>
    ${c.icon && html`<i class=${`ph ph-${iconName(c.icon)}`} aria-hidden="true"></i>`}${c.text ? plain(c.text) : ""}
  </span>`;
}

function Tick({ action, done, onDone }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (busy || !path(action.path)) return;
    setBusy(true);
    try {
      const r = await fetch(action.path, {
        method: action.method || "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(action.body ?? {}),
      });
      if (!r.ok) throw new Error(String(r.status));
      onDone();
    } catch {
      const err = action.error || {};
      toast({ title: err.title || "Not saved", desc: err.desc || "The change did not reach the brain. Try again.", kind: "danger" });
    }
    setBusy(false);
  };
  return html`<button type="button" class="cb-tick" onClick=${run} disabled=${busy || done}
    aria-label=${action.label || "Mark done"} data-tip=${action.label || null}>
    <i class=${`ph ${done ? "ph-check-circle" : "ph-circle"}`} aria-hidden="true"></i>
  </button>`;
}

function Row({ r }) {
  const [done, setDone] = useState(!!r.done);
  const href = path(r.link);
  const title = plain(r.title);
  const cls = ["cb-row", done && "is-done", r.struck && "is-struck", r.accent && "has-accent"].filter(Boolean).join(" ");
  return html`<li class=${cls} data-accent=${r.accent ? tone(r.accent) : null}>
    ${r.action && html`<${Tick} action=${r.action} done=${done} onDone=${() => setDone(true)} />`}
    ${r.lead && html`<${Chip} c=${r.lead} cls="cb-lead" />`}
    <div class="cb-row-main">
      <div class="cb-row-head">
        ${href
          ? html`<a class=${`cb-title ellipsis${r.title_tone ? ` cb-tone-${tone(r.title_tone)}` : ""}`} href=${href} title=${title}>${title}</a>`
          : html`<span class=${`cb-title ellipsis${r.title_tone ? ` cb-tone-${tone(r.title_tone)}` : ""}`} title=${title}>${title}</span>`}
        ${(r.marks || []).map((m) => html`<${Chip} c=${m} cls="cb-mark" />`)}
      </div>
      ${r.detail && html`<span class="cb-detail ellipsis" title=${plain(r.detail)}>${plain(r.detail)}</span>`}
    </div>
    ${r.trail && html`<${Chip} c=${r.trail} cls="cb-trail num" />`}
  </li>`;
}

function Rows({ b }) {
  const rows = b.rows || [];
  return html`<div class="cb-group">
    ${b.title && html`<div class="cb-group-label">${plain(b.title)}${b.count != null && html` <span class="num muted">${b.count}</span>`}</div>`}
    ${rows.length ? html`<ul class="cb-rows">${rows.map((r) => html`<${Row} key=${r.id} r=${r} />`)}</ul>` : b.empty && html`<span class="muted">${plain(b.empty)}</span>`}
  </div>`;
}

function Line({ b }) {
  const items = b.items || [];
  const lead = items.filter((c) => !c.end);
  const end = items.filter((c) => c.end);
  return html`<div class="cb-line">
    ${lead.map((c) => html`<${Chip} c=${c} />`)}
    ${end.length > 0 && html`<span class="cb-line-end">${end.map((c) => html`<${Chip} c=${c} />`)}</span>`}
  </div>`;
}

function Meter({ b }) {
  const ref = useRef(null);
  useGInit(ref, [b.value, b.max]);
  const sub = b.sub || [];
  return html`<div class="cb-meter" ref=${ref} data-tone=${b.tone ? tone(b.tone) : null}>
    <div class="cb-meter-head">
      <span class="cb-meter-label">${plain(b.label)}</span>
      ${b.badge && html`<${Chip} c=${b.badge} />`}
      <div class="g-meter" data-value=${Number(b.value) || 0} data-max=${b.max == null ? 100 : Number(b.max)}
        data-warn-at=${b.warn_at ?? null} data-danger-at=${b.danger_at ?? null}
        aria-label=${plain(b.label)} data-valuetext=${b.text || null}></div>
      <span class="cb-meter-text num">${plain(b.text)}</span>
    </div>
    ${sub.length > 0 && html`<div class="cb-meter-sub"><${Chip} c=${sub[0]} /><span class="cb-spacer"></span>${sub.slice(1).map((c) => html`<${Chip} c=${c} />`)}</div>`}
  </div>`;
}

function Bullets({ b }) {
  return html`<ul class="cb-bullets">${(b.items || []).map((it) => {
    const href = path(it.link);
    const body = html`${it.label && html`<b>${plain(it.label)} </b>`}${plain(it.text)}`;
    return html`<li>${href ? html`<a href=${href}>${body}</a>` : body}</li>`;
  })}</ul>`;
}

function Image({ b }) {
  const url = path(b.url);
  if (!url) return null;
  const ratio = b.width && b.height ? `${b.width} / ${b.height}` : null;
  return html`<a class="cb-image" href=${url} target="_blank" rel="noopener">
    <img src=${url} alt=${plain(b.alt || "")} loading="lazy" style=${ratio ? `aspect-ratio: ${ratio}` : null} />
  </a>`;
}

function Fold({ b }) {
  return html`<details class="cb-fold" open=${!!b.open}>
    <summary>${plain(b.title || "Details")}</summary>
    <${Blocks} blocks=${(b.blocks || []).filter((x) => x && x.type !== "fold")} />
  </details>`;
}

function Panel({ b }) {
  const link = path(b.link);
  return html`<section class="card cb-panel">
    <header class="cb-panel-head">
      ${b.icon && html`<i class=${`ph ph-${iconName(b.icon)} muted`} aria-hidden="true"></i>`}
      <span class="cb-panel-title">${plain(b.title || b.name)}</span>
      ${b.meta && html`<span class="muted cb-panel-meta">${plain(b.meta)}</span>`}
      ${link && html`<a class="btn btn-sm btn-tertiary cb-panel-link" href=${link}>${plain(b.link_label || "Open")}</a>`}
    </header>
    ${b.state && b.state !== "ok" ? html`<p class="muted">${plain(b.message)}</p>` : html`<${Blocks} blocks=${b.blocks || []} />`}
  </section>`;
}

const CARD = { rows: Rows, line: Line, meter: Meter };
const SINGLE = { bullets: Bullets, detail: ({ b }) => html`<p class="cb-small muted">${plain(b.text)}</p>`, image: Image, fold: Fold, panel: Panel };

/* Rows, lines and meters in a run share one card; the rest stand alone. */
function pieces(blocks) {
  const out = [];
  for (const b of blocks || []) {
    if (!b || typeof b !== "object") continue;
    if (CARD[b.type]) {
      const last = out[out.length - 1];
      if (last && last.card) last.card.push(b); else out.push({ card: [b] });
    } else if (SINGLE[b.type]) out.push({ one: b });
  }
  return out;
}

export function Blocks({ blocks }) {
  return html`<div class="cb-blocks">${pieces(blocks).map((p) => p.card
    ? html`<div class="card cb-card">${p.card.map((b) => { const C = CARD[b.type]; return html`<${C} b=${b} />`; })}</div>`
    : (() => { const C = SINGLE[p.one.type]; return html`<${C} b=${p.one} />`; })())}</div>`;
}
