/* g-design@1.6.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// The collapsible rail (kit.css .g-rail-toggle, .g-shell[data-rail]), plain DOM with no
// imports, so a server-rendered page can load it as a module and the Preact shell uses it too.
// Open by default. Collapsed is remembered per viewer under the toggle's key in localStorage,
// which can be missing or throw (private windows, blocked storage), so every access is guarded
// and the rail simply stays open. Collapsed, a rail item shows its label as a g-ui tooltip.

export const RAIL_KEY = "g-rail";

export function railCollapsed(key = RAIL_KEY) {
  try { return localStorage.getItem(key) === "collapsed"; } catch (e) { return false; }
}

function remember(key, collapsed) {
  try {
    if (collapsed) localStorage.setItem(key, "collapsed");
    else localStorage.removeItem(key);
  } catch (e) { /* not remembered; the rail still works for this page */ }
}

const TOGGLE_ICON = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">'
  + '<rect x="1.75" y="2.75" width="12.5" height="10.5" rx="2"/><path d="M6 3v10"/><path d="M10.5 6.5 9 8l1.5 1.5"/></svg>';

/* Set one shell's rail. Labels for tooltips are added on hover (railTips), and taken off again
   when the rail opens. */
export function applyRail(shell, collapsed) {
  if (!shell) return;
  if (collapsed) shell.setAttribute("data-rail", "collapsed");
  else shell.removeAttribute("data-rail");
  const aside = shell.querySelector(":scope > aside");
  if (!collapsed && aside) aside.querySelectorAll("[data-rail-tip]").forEach((el) => { el.removeAttribute("data-tip"); el.removeAttribute("data-rail-tip"); });
  shell.querySelectorAll(":scope > aside .g-rail-toggle").forEach((b) => {
    const label = collapsed ? "Expand the menu" : "Collapse the menu";
    b.setAttribute("aria-label", label);
    b.setAttribute("data-tip", label);
    b.setAttribute("aria-expanded", collapsed ? "false" : "true");
  });
}

/* Collapsed, an item without a tip of its own gets its label as one, just before g-ui's
   tooltip reads it (this listener is on the rail, g-ui's on the document). */
function railTips(shell) {
  const aside = shell.querySelector(":scope > aside");
  if (!aside || aside.dataset.railTips) return;
  aside.dataset.railTips = "";
  aside.addEventListener("pointerover", (e) => {
    if (shell.getAttribute("data-rail") !== "collapsed") return;
    const item = e.target.closest && e.target.closest(".nav-item");
    if (!item || item.hasAttribute("data-tip")) return;
    const label = item.querySelector(".ellipsis");
    if (!label) return;
    item.setAttribute("data-tip", label.textContent.trim());
    item.setAttribute("data-rail-tip", "");
  });
}

/* Wire one toggle button: its shell takes the remembered state, and a click flips it. */
export function wireRailToggle(button, key = button.dataset.railKey || RAIL_KEY) {
  const shell = button.closest(".g-shell");
  if (!shell || button.dataset.railWired) return;
  button.dataset.railWired = "";
  if (!button.innerHTML.trim()) button.innerHTML = TOGGLE_ICON;
  railTips(shell);
  applyRail(shell, railCollapsed(key));
  button.addEventListener("click", () => {
    const collapsed = shell.getAttribute("data-rail") !== "collapsed";
    remember(key, collapsed);
    applyRail(shell, collapsed);
  });
}

/* A server-rendered page: wire every toggle in it. */
export function wireRails(root = document) {
  root.querySelectorAll(".g-rail-toggle").forEach((b) => wireRailToggle(b));
}
