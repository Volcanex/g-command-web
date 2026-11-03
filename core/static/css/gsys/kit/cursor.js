/* g-design@1.6.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// Your own cursor: the tinted arrow, hand, text bar and fist Studio draws for coworking presence,
// as the default pointer of every g app, so moving between Command and an embedded Studio never
// changes it. Plain DOM with no imports, like rail.js, so a server-rendered page loads it as a
// module. The rules that apply it (html[data-own-cursor]) and the palette it is tinted from
// (--cowork-<name>) are in kit.css. No presence, no sockets: only the pointer.

/* Where Studio keeps your coworking colour. A page on the same origin as an embedded Studio
   reads the same key, so its cursor is the one Studio paints. */
export const CURSOR_KEY = "gs.cowork-color";
/* The colour before anyone has picked one. */
export const DEFAULT_CURSOR = "red";
export const CURSOR_COLORS = ["red", "orange", "amber", "lime", "green", "teal", "sky", "blue", "violet", "pink"];

/* The cursors as SVG, tinted, with a white keyline so they read on any surface. The hotspots
   are the arrow's tip, the fingertip and the middle of the text bar. The fist is the hand with
   its finger folded, in the same box and with the same hotspot, so grabbing never moves or
   resizes the cursor. */
export function cursorSvgs(fill) {
  const svg = (w, h, body) => `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${body}</svg>`;
  return {
    arrow: [svg(20, 22, `<path d="M2.2 1.6 15.6 11.1a.6.6 0 0 1-.27 1.08l-5.62.7a1.2 1.2 0 0 0-.85.55l-3.07 4.86a.6.6 0 0 1-1.1-.22L1.3 2.18a.6.6 0 0 1 .9-.58Z" fill="${fill}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>`), 2, 2],
    hand: [svg(22, 20, `<path d="M7.5 3.55A1.55 1.55 0 0 1 10.6 3.55V7.89L11.1 7.8C12 7.7 12.7 8.15 13 8.77C13.8 8.5 14.7 8.77 15.1 9.47C15.9 9.3 16.7 9.74 16.9 10.44L17.3 12.38C17.7 14.22 17.1 16.07 15.8 17.48L15.2 18.18H8.3L4.5 13.78C3.9 13.08 4 12.2 4.8 11.67C5.5 11.14 6.5 11.23 7.1 11.85L7.5 12.29Z" fill="${fill}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>`), 9, 2],
    grab: [svg(22, 20, `<path d="M7.5 9.2C7.5 8.2 8.2 7.55 9.05 7.55C9.85 7.55 10.5 8.1 10.75 8.7L11.1 7.8C12 7.7 12.7 8.15 13 8.77C13.8 8.5 14.7 8.77 15.1 9.47C15.9 9.3 16.7 9.74 16.9 10.44L17.3 12.38C17.7 14.22 17.1 16.07 15.8 17.48L15.2 18.18H8.3L4.5 13.78C3.9 13.08 4 12.2 4.8 11.67C5.5 11.14 6.5 11.23 7.1 11.85L7.5 12.29Z" fill="${fill}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/>`), 9, 2],
    text: [svg(16, 24, `<path d="M4 3h2.2A1.8 1.8 0 0 1 8 4.8 1.8 1.8 0 0 1 9.8 3H12M8 4.8v14.4M4 21h2.2A1.8 1.8 0 0 0 8 19.2a1.8 1.8 0 0 0 1.8 1.8H12" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 3h2.2A1.8 1.8 0 0 1 8 4.8 1.8 1.8 0 0 1 9.8 3H12M8 4.8v14.4M4 21h2.2A1.8 1.8 0 0 0 8 19.2a1.8 1.8 0 0 0 1.8 1.8H12" fill="none" stroke="${fill}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`), 8, 12],
  };
}
export const cursorUrl = ([svg, x, y], fallback) => `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${x} ${y}, ${fallback}`;

/* A palette colour (--cowork-<name>) resolved to rgb, through a canvas so any CSS colour syntax
   comes out plain. `el` is where the token is read: the page root, or a scope that sets it. */
export function cursorRgb(name, el = document.documentElement) {
  const v = getComputedStyle(el).getPropertyValue(`--cowork-${name}`).trim();
  if (!v) return null;
  const cv = document.createElement("canvas");
  cv.width = cv.height = 1;
  const g = cv.getContext("2d", { willReadFrequently: true });
  if (!g) return null;
  g.fillStyle = "#000";
  g.fillStyle = v;
  g.fillRect(0, 0, 1, 1);
  const [r, gg, b] = g.getImageData(0, 0, 1, 1).data;
  return `rgb(${r},${gg},${b})`;
}

/* Put the cursor in `name` on the page. False when the token is missing (kit.css not loaded). */
export function paintOwnCursor(name, el) {
  const root = document.documentElement;
  const rgb = cursorRgb(name, el || root);
  if (!rgb) return false;
  const s = cursorSvgs(rgb);
  root.style.setProperty("--cursor-arrow", cursorUrl(s.arrow, "default"));
  root.style.setProperty("--cursor-hand", cursorUrl(s.hand, "pointer"));
  root.style.setProperty("--cursor-text", cursorUrl(s.text, "text"));
  root.style.setProperty("--cursor-grab", cursorUrl(s.grab, "grabbing"));
  root.setAttribute("data-own-cursor", name);
  return true;
}

/* The stored colour, else the default. localStorage can be missing or throw. */
export function ownCursorColor(key = CURSOR_KEY, fallback = DEFAULT_CURSOR) {
  try { const c = localStorage.getItem(key); if (CURSOR_COLORS.includes(c)) return c; } catch (e) { /* default */ }
  return fallback;
}

/* For a page that only wants the cursor: paint it now and again whenever the theme changes,
   since the palette's lightness changes with it. */
let watching = false;
export function wireOwnCursor({ key = CURSOR_KEY, fallback = DEFAULT_CURSOR } = {}) {
  const paint = () => paintOwnCursor(ownCursorColor(key, fallback));
  paint();
  if (watching) return;
  watching = true;
  new MutationObserver(() => requestAnimationFrame(paint))
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}
