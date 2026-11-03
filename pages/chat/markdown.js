// The small Markdown Voice writes (paragraphs, bullet and numbered lists,
// headings, **bold**, *italic*, `code`, [links](/path)), drawn as Preact
// nodes inside `.prose`. No HTML is ever parsed, so a reply cannot inject any.
import { html } from "../../core/app/boot.js";

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|\[\[[^\]]+\]\])/g;
// Links go to command paths or https only.
const safeHref = (u) => (/^\/(?!\/)/.test(u) || /^https:\/\//.test(u) ? u : "");

function inline(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const s = m[0];
    if (s.startsWith("**")) out.push(html`<strong>${s.slice(2, -2)}</strong>`);
    else if (s.startsWith("`")) out.push(html`<code>${s.slice(1, -1)}</code>`);
    else if (s.startsWith("[[")) out.push(s.slice(2, -2).split("|").pop());
    else if (s.startsWith("[")) {
      const [, label, url] = s.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      const href = safeHref(url);
      out.push(href ? html`<a href=${href} target=${href.startsWith("/") ? null : "_blank"} rel="noopener">${label}</a>` : label);
    } else out.push(html`<em>${s.slice(1, -1)}</em>`);
    last = m.index + s.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function blocks(text) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const out = [];
  let para = [];
  let list = null;
  const flushPara = () => { if (para.length) out.push(html`<p>${para.flatMap((l, i) => (i ? [html`<br />`, ...inline(l)] : inline(l)))}</p>`); para = []; };
  const flushList = () => {
    if (!list) return;
    const items = list.items.map((it) => html`<li>${inline(it)}</li>`);
    out.push(list.ordered ? html`<ol>${items}</ol>` : html`<ul>${items}</ul>`);
    list = null;
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const num = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const head = line.match(/^#{1,4}\s+(.*)$/);
    if (bullet || num) {
      flushPara();
      const ordered = !!num;
      if (list && list.ordered !== ordered) flushList();
      if (!list) list = { ordered, items: [] };
      list.items.push((bullet || num)[1]);
    } else if (head) {
      flushPara(); flushList();
      out.push(html`<h4>${inline(head[1])}</h4>`);
    } else if (!line.trim()) {
      flushPara(); flushList();
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara(); flushList();
  return out;
}

export function Markdown({ text }) {
  if (!text) return null;
  return html`<div class="prose chat-prose">${blocks(text)}</div>`;
}
