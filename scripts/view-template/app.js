// __TITLE__. Scaffolded by scripts/new-view.py; the view contract (pages/CLAUDE.md,
// "New views") holds while you keep to these rules.
//   Header   PageHead only. The top bar names the page (Group > Page), so the title is
//            screen-reader text; never add a visible title or top spacing of your own.
//   Margins  the shell's .content-page owns the gutter and the --sp-4 stack gap.
//   Motion   the shell's cross-document view transition (g-vt-in) brings the page in;
//            add no entry animation here.
//   States   Loaded draws the skeleton, the error (with retry) and then children; Empty for no rows.
//   Style    app.css, alias tokens only.
import { html, PageHead, Loaded, Empty, SkeletonRows, mount, useJson } from "../../core/app/boot.js";
import "./app.css";

function Rows({ items }) {
  if (!items.length) return html`<${Empty} title="Nothing here yet" desc="Items appear here once there are some." />`;
  return html`<div class="card __SLUG__-list">
    ${items.map((it) => html`<div class="__SLUG__-row" key=${it.id}><span>${it.title}</span></div>`)}
  </div>`;
}

function Page() {
  const state = useJson("/api/__SLUG__");
  return html`
    <${PageHead} title="__TITLE__" sub="One line on what this view is for." />
    <${Loaded} state=${state} skeleton=${html`<${SkeletonRows} rows=${4} />`}>
      ${(data) => html`<${Rows} items=${data.items || []} />`}
    <//>`;
}

mount(Page);
