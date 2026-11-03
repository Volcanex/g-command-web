/* g-design@1.6.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// The rail (kit.css .g-shell[data-rail], .g-rail-toggle, .nav-group), plain DOM with no imports,
// so a server-rendered page loads it as a module and the Preact shell uses it too.
//
// From 721px up the rail is collapsed to icons by default. Resting the pointer on it for a
// moment, or moving keyboard focus into it, opens it as an overlay above the content
// (data-rail-peek), so nothing beside it moves; it closes a moment after the pointer leaves,
// when focus leaves, or on Escape. The toggle beside the brand pins it open (the content then
// makes room) and, pinned, collapses it again: "Keep open" and "Collapse". Pinned is remembered
// per viewer under the toggle's key in localStorage, which can be missing or throw (private
// windows, blocked storage), so every access is guarded and the rail simply stays collapsed.
// Under 721px the rail is the phone sheet and none of this applies.
//
// Each shell wires its own rail, and every selector here keeps to its own aside, so two shells
// on one page (Studio inside Command) open, close and pin on their own.

export const RAIL_KEY = "g-rail";
const PINNED = "pinned";
const OPEN_DELAY = 150;   // intent: a pointer passing over the rail on its way elsewhere does nothing
const CLOSE_DELAY = 300;  // a pointer that slips off the edge for a moment keeps it open
const SETTLE = 500;       // the close transition (kit.css, --spring-smooth-dur, perceived 300ms)
const WIDE = "(min-width: 721px)";

export function railPinned(key = RAIL_KEY) {
  try { return localStorage.getItem(key) === PINNED; } catch (e) { return false; }
}
/* Kept for callers of the open-by-default rail: collapsed now means "not pinned". */
export function railCollapsed(key = RAIL_KEY) { return !railPinned(key); }

function remember(key, pinned) {
  try {
    if (pinned) localStorage.setItem(key, PINNED);
    else localStorage.removeItem(key);
  } catch (e) { /* not remembered; the rail still works for this page */ }
}

const TOGGLE_ICON = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">'
  + '<rect x="1.75" y="2.75" width="12.5" height="10.5" rx="2"/><path d="M6 3v10"/><path d="M10.5 6.5 9 8l1.5 1.5"/></svg>';

const asideOf = (shell) => shell && shell.querySelector(":scope > aside");
const togglesOf = (shell) => shell.querySelectorAll(":scope > aside .g-rail-toggle");

/* Set one shell's rail: pinned open, or collapsed to icons. */
export function applyRail(shell, collapsed) {
  if (!shell) return;
  if (collapsed) shell.setAttribute("data-rail", "collapsed");
  else shell.setAttribute("data-rail", PINNED);
  togglesOf(shell).forEach((b) => {
    const label = collapsed ? "Keep open" : "Collapse";
    b.setAttribute("aria-label", label);
    b.setAttribute("data-tip", label);
    b.setAttribute("aria-pressed", collapsed ? "false" : "true");
  });
}

/* Hover and focus open a collapsed rail over the content. One controller per shell. */
function wirePeek(shell) {
  const aside = asideOf(shell);
  if (!aside || aside.dataset.railPeek !== undefined) return;
  aside.dataset.railPeek = "";
  const wide = matchMedia(WIDE);
  let openTimer = 0, closeTimer = 0, settleTimer = 0;
  let pointerIn = false;
  let held = false;  // closed by hand (Escape, unpin): no reopening until the pointer or focus leaves

  const collapsed = () => shell.getAttribute("data-rail") === "collapsed";
  const peeking = () => shell.hasAttribute("data-rail-peek");
  const busy = () => !!aside.querySelector(":popover-open, [aria-haspopup][aria-expanded='true']");
  const clear = () => { clearTimeout(openTimer); clearTimeout(closeTimer); };

  function open() {
    clear();
    if (!collapsed() || !wide.matches || peeking()) return;
    clearTimeout(settleTimer);
    shell.removeAttribute("data-rail-settling");
    shell.setAttribute("data-rail-peek", "");
    aside.setAttribute("aria-expanded", "true");
  }
  function close() {
    clear();
    if (!peeking()) return;
    shell.removeAttribute("data-rail-peek");
    aside.removeAttribute("aria-expanded");
    // Items keep their open width while the rail narrows, so labels fade rather than squeeze.
    shell.setAttribute("data-rail-settling", "");
    settleTimer = setTimeout(() => shell.removeAttribute("data-rail-settling"), SETTLE);
  }
  shell.railClose = (hold = false) => { if (hold) held = true; close(); };

  aside.addEventListener("pointerenter", (e) => {
    if (e.pointerType === "touch") return;
    pointerIn = true;
    clearTimeout(closeTimer);
    if (!held && collapsed() && !peeking()) openTimer = setTimeout(open, OPEN_DELAY);
  });
  aside.addEventListener("pointerleave", (e) => {
    if (e.pointerType === "touch") return;
    pointerIn = false;
    held = false;
    clearTimeout(openTimer);
    // Keyboard focus in the rail keeps it open; a click's focus does not outlast the pointer.
    if (peeking() && !aside.querySelector(":focus-visible")) {
      closeTimer = setTimeout(() => { if (!busy()) close(); }, CLOSE_DELAY);
    }
  });
  aside.addEventListener("focusin", (e) => { if (!held && collapsed() && e.target.matches(":focus-visible")) open(); });
  aside.addEventListener("focusout", (e) => {
    if (aside.contains(e.relatedTarget)) return;
    held = false;
    // a menu opened from the rail takes focus into its popover, which is still inside the aside
    setTimeout(() => { if (!pointerIn && !aside.contains(document.activeElement) && !busy()) close(); }, 0);
  });
  aside.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !peeking() || busy()) return;
    held = true;
    close();
  });
  wide.addEventListener("change", () => { if (!wide.matches) close(); });
}

/* Disclosure groups (kit.css .nav-group): a parent row that opens and closes its children in
   place. Open by default; a group closed by hand is remembered per viewer under the rail's key. */
const groupKey = (key) => `${key}:closed`;
function closedGroups(key) {
  try { return JSON.parse(localStorage.getItem(groupKey(key)) || "[]"); } catch (e) { return []; }
}
export function setGroupOpen(group, open, key) {
  group.toggleAttribute("data-open", open);
  group.querySelectorAll(":scope > .nav-group-row [aria-expanded], :scope > .nav-group-toggle").forEach((b) => b.setAttribute("aria-expanded", open ? "true" : "false"));
  if (!key || !group.dataset.group) return;
  try {
    const shut = new Set(closedGroups(key));
    if (open) shut.delete(group.dataset.group); else shut.add(group.dataset.group);
    if (shut.size) localStorage.setItem(groupKey(key), JSON.stringify([...shut]));
    else localStorage.removeItem(groupKey(key));
  } catch (e) { /* not remembered */ }
}
export function groupOpen(name, key = RAIL_KEY) { return !closedGroups(key).includes(name); }

/* A server-rendered rail's groups: each opens from its remembered state, and its toggle flips it.
   A group holding the current page always opens. */
export function wireGroups(aside, key = RAIL_KEY) {
  if (!aside || aside.dataset.railGroups !== undefined) return;
  aside.dataset.railGroups = "";
  const shut = closedGroups(key);
  aside.querySelectorAll(".nav-group").forEach((group) => {
    const here = group.querySelector('[aria-current="page"]');
    setGroupOpen(group, here || !shut.includes(group.dataset.group));
    const button = group.querySelector(":scope > .nav-group-toggle, :scope > .nav-group-row > .nav-twist");
    button && button.addEventListener("click", () => setGroupOpen(group, !group.hasAttribute("data-open"), key));
  });
}

/* Wire one toggle button: its shell takes the remembered state, hover and focus peek, and a
   click pins or unpins. */
export function wireRailToggle(button, key = button.dataset.railKey || RAIL_KEY) {
  const shell = button.closest(".g-shell");
  if (!shell || button.dataset.railWired !== undefined) return;
  button.dataset.railWired = "";
  if (!button.innerHTML.trim()) button.innerHTML = TOGGLE_ICON;
  applyRail(shell, !railPinned(key));
  wirePeek(shell);
  button.addEventListener("click", () => {
    const pin = shell.getAttribute("data-rail") === "collapsed";
    remember(key, pin);
    if (pin) {
      // The peek is already the open rail: it stops floating and the content makes room.
      shell.removeAttribute("data-rail-peek");
      asideOf(shell).removeAttribute("aria-expanded");
      applyRail(shell, false);
    } else {
      applyRail(shell, true);
      // The pointer is still on the rail: hold it closed until it leaves.
      shell.railClose && shell.railClose(true);
    }
  });
  // Transitions start after the first frame, so a remembered state never animates in on load.
  requestAnimationFrame(() => requestAnimationFrame(() => shell.setAttribute("data-rail-ready", "")));
}

/* A server-rendered page: wire every toggle in it, and its groups. */
export function wireRails(root = document) {
  root.querySelectorAll(".g-rail-toggle").forEach((b) => {
    wireRailToggle(b);
    const shell = b.closest(".g-shell");
    wireGroups(asideOf(shell), b.dataset.railKey || RAIL_KEY);
  });
}
