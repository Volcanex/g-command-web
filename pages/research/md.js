// Research Markdown: the subset the research repos write (headings, paragraphs,
// lists, pipe tables, block quotes, fenced code, rules, **bold**, *italic*,
// `code`, links), drawn as Preact nodes inside `.prose`. No HTML is parsed, so
// a file on disk cannot inject any. Headings carry ids for the contents list.
import { html } from "../../core/app/boot.js";

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|!?\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|_[^_\s][^_]*_(?![A-Za-z0-9])|\[\[[^\]]+\]\]|https:\/\/[^\s)<>]+)/g;
const safeHref = (u) => (/^\/(?!\/)/.test(u) || /^https?:\/\//.test(u) || /^#[\w-]+$/.test(u) ? u : "");

export function inline(text) {
  const out = [];
  let last = 0;
  for (const m of String(text).matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const s = m[0];
    if (s.startsWith("**")) out.push(html`<strong>${inline(s.slice(2, -2))}</strong>`);
    else if (s.startsWith("`")) out.push(html`<code>${s.slice(1, -1)}</code>`);
    else if (s.startsWith("[[")) out.push(s.slice(2, -2).split("|").pop());
    else if (s.startsWith("!")) out.push(s.match(/^!\[([^\]]*)\]/)[1]);
    else if (s.startsWith("[")) {
      const [, label, url] = s.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      const href = safeHref(url);
      out.push(href ? html`<a href=${href} target=${href.startsWith("http") ? "_blank" : null} rel="noopener">${inline(label)}</a>` : label);
    } else if (s.startsWith("https://")) {
      const url = s.replace(/[.,;:]+$/, "");
      out.push(html`<a href=${url} target="_blank" rel="noopener" class="rs-url">${url}</a>`);
      if (url.length < s.length) out.push(s.slice(url.length));
    } else out.push(html`<em>${inline(s.slice(1, -1))}</em>`);
    last = m.index + s.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/* Flatten Markdown to plain text for slots that are not prose (contents, titles). */
export const plainText = (s) => String(s || "").replace(/\*\*|__|`/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
  .replace(/(^|\s)[*_]([^*_]+)[*_]/g, "$1$2").trim();

function slugger() {
  const used = new Map();
  return (text) => {
    const base = plainText(text).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "section";
    const n = used.get(base) || 0;
    used.set(base, n + 1);
    return n ? `${base}-${n}` : base;
  };
}

const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

/* Parse once into {nodes, headings}; headings are [{level, text, id}] for levels 2 and 3. */
export function parse(text) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const slug = slugger();
  const nodes = [];
  const headings = [];
  let para = [];
  let list = null;
  const flushPara = () => { if (para.length) nodes.push(html`<p>${inline(para.join(" "))}</p>`); para = []; };
  const flushList = () => {
    if (!list) return;
    const items = list.items.map((it) => html`<li>${inline(it)}</li>`);
    nodes.push(list.ordered ? html`<ol start=${list.start}>${items}</ol>` : html`<ul>${items}</ul>`);
    list = null;
  };
  const flush = () => { flushPara(); flushList(); };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    const fence = line.match(/^\s*(```|~~~)/);
    if (fence) {
      flush();
      const body = [];
      while (++i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i]);
      nodes.push(html`<pre><code>${body.join("\n")}</code></pre>`);
      continue;
    }
    const head = line.match(/^(#{1,6})\s+(.*?)\s*#*$/);
    if (head) {
      flush();
      const level = Math.min(head[1].length, 4);
      const id = slug(head[2]);
      if (level === 2 || level === 3) headings.push({ level, text: plainText(head[2]), id });
      const H = `h${level}`;
      nodes.push(html`<${H} id=${id}>${inline(head[2])}<//>`);
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      flush();
      const cols = cells(line);
      const rows = [];
      i += 1;
      while (i + 1 < lines.length && /^\s*\|.*\|\s*$/.test(lines[i + 1])) rows.push(cells(lines[++i]));
      nodes.push(html`<div class="rs-table-wrap"><table>
        <thead><tr>${cols.map((c) => html`<th>${inline(c)}</th>`)}</tr></thead>
        <tbody>${rows.map((r) => html`<tr>${cols.map((_, n) => html`<td>${inline(r[n] || "")}</td>`)}</tr>`)}</tbody>
      </table></div>`);
      continue;
    }
    if (/^\s*>/.test(line)) {
      flush();
      const quote = [line.replace(/^\s*>\s?/, "")];
      while (i + 1 < lines.length && /^\s*>/.test(lines[i + 1])) quote.push(lines[++i].replace(/^\s*>\s?/, ""));
      nodes.push(html`<blockquote><p>${inline(quote.join(" "))}</p></blockquote>`);
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); nodes.push(html`<hr />`); continue; }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    const num = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (bullet || num) {
      flushPara();
      const ordered = !!num;
      if (list && list.ordered !== ordered) flushList();
      if (!list) list = { ordered, items: [], start: num ? Number(num[1]) : 1 };
      list.items.push(num ? num[2] : bullet[1]);
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    if (list && /^\s{2,}\S/.test(line)) { list.items[list.items.length - 1] += " " + line.trim(); continue; }
    flushList();
    para.push(line.trim());
  }
  flush();
  return { nodes, headings };
}
