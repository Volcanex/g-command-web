/* g-design@1.7.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
import { html } from "./html.js";

/* Phosphor Regular glyphs as inline SVG. The kit ships no glyph data: the app registers the
   names it uses once, at startup, with setIcons({name: [path d, ...]}), so it only bundles
   what it draws. An unknown name draws "question" when that is registered. */
let paths = {};
export function setIcons(map) { paths = { ...paths, ...map }; }

/* Decorative unless given a label. Defaults to 16px so an icon never grows to fill its box;
   CSS width/height rules still win. */
export function Icon({ name, label, size = 16, class: cls }) {
  const d = paths[name] || paths["question"] || [];
  return html`<svg class=${cls || ""} viewBox="0 0 256 256" fill="currentColor" width=${size} height=${size}
    aria-hidden=${label ? undefined : "true"} role=${label ? "img" : undefined} aria-label=${label}>
    ${d.map((p) => html`<path d=${p} />`)}</svg>`;
}
