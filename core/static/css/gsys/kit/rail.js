/* g-design@1.9.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// The rail (kit.css .g-shell[data-rail], .g-rail-toggle, .nav-group), plain DOM with no imports,
// so a server-rendered page loads it as a module and the Preact shell uses it too.
//
// From 721px up the rail is collapsed to icons by default; a toggle with data-rail-default="open"
// (Brand's railOpen) starts it pinned open instead. Resting the pointer on it for a
// moment, or moving keyboard focus into it, opens it as an overlay above the content
// (data-rail-peek) and the content moves over to make room, so nothing is hidden under it; it closes a moment after the pointer leaves,
// when focus leaves, or on Escape. The toggle beside the brand pins it open (the content then
// makes room) and, pinned, collapses it again: "Keep open" and "Collapse". Pinned is remembered
// per viewer under the toggle's key in localStorage, which can be missing or throw (private
// windows, blocked storage), so every access is guarded and the rail simply stays collapsed.
// Under 721px none of this applies.
//
// Each shell wires its own rail, and every selector here keeps to its own aside, so two shells
// on one page (Studio inside Command) open, close and pin on their own.
//
// Under 721px the rail's pinned items become the dock (wireDock, below): a bar at the foot of the
// screen with up to four places and Go, which opens the palette of every place in the rail. Go is
// Cmd+K or Ctrl+K at every width. The rail stays the one data model.

export const RAIL_KEY = "g-rail";
const PINNED = "pinned";
const COLLAPSED = "collapsed";
const OPEN_DELAY = 150;   // intent: a pointer passing over the rail on its way elsewhere does nothing
const CLOSE_DELAY = 300;  // a pointer that slips off the edge for a moment keeps it open
const SETTLE = 500;       // the close transition (kit.css, --spring-smooth-dur, perceived 300ms)
const WIDE = "(min-width: 721px)";

/* open: the rail's state before the viewer has chosen one. */
export function railPinned(key = RAIL_KEY, open = false) {
  try {
    const v = localStorage.getItem(key);
    return v === PINNED || (v !== COLLAPSED && open);
  } catch (e) { return open; }
}
/* Kept for callers of the open-by-default rail: collapsed now means "not pinned". */
export function railCollapsed(key = RAIL_KEY) { return !railPinned(key); }

function remember(key, pinned) {
  try {
    localStorage.setItem(key, pinned ? PINNED : COLLAPSED);
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
export function wireRailToggle(button, key = button.dataset.railKey || RAIL_KEY, open = button.dataset.railDefault === "open") {
  const shell = button.closest(".g-shell");
  if (!shell || button.dataset.railWired !== undefined) return;
  button.dataset.railWired = "";
  if (!button.innerHTML.trim()) button.innerHTML = TOGGLE_ICON;
  applyRail(shell, !railPinned(key, open));
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

/* A server-rendered page: wire every toggle in it, and its groups, and a dock for every shell
   whose rail pins a place (data-pin). */
export function wireRails(root = document) {
  root.querySelectorAll(".g-rail-toggle").forEach((b) => {
    wireRailToggle(b);
    const shell = b.closest(".g-shell");
    wireGroups(asideOf(shell), b.dataset.railKey || RAIL_KEY);
  });
  const shells = [...root.querySelectorAll(".g-shell")];
  if (root.matches && root.matches(".g-shell")) shells.unshift(root);
  shells.forEach((shell) => {
    if (shell.querySelector(":scope > aside a.nav-item[data-pin]")) wireDock(shell);
  });
}

/* ------------------------------------------------------------------ dock and Go */

/* wireDock(shell, opts): the phone form of the rail, and Go, the palette of every place in it.

   The rail's items with data-pin="1".."4" are the dock's places, in pin order: the label is the
   item's data-dock-label or its text, the icon a copy of the item's first icon, the count its
   .badge. Under 721px the dock is a bar at the foot of the screen (56px plus the safe area) with
   those places and Go; the aside stays in the DOM, hidden, and the menu button goes. From 721px
   there is no dock and Cmd+K or Ctrl+K opens the same palette.

   Each place reopens the last page under it (sessionStorage, per rail key): switching places
   replaces the history entry, so an edge-swipe back never jumps between them, and fires the
   shell's selection haptic. The dock steps aside while a field has focus.

   A shell inside another docked shell (Studio inside Command) is a guest: under 721px the host
   gets data-dock-guest, which hides its dock and top bar, and the guest's first slot is the
   host's G mark, back to the host's last place (the host keeps it on its dock as
   data-dock-return). Two copies of this file may share a page, so they speak only through those
   attributes and sessionStorage.

   Before a slot or a palette entry navigates, the shell gets a cancelable "g-dock:navigate"
   event ({href, replace}); a single-page app may route it itself and cancel. "g-palette:open"
   and "g-palette:close" say when Go opens and closes. Returns unwire(). */

const PHONE = "(max-width: 720px)";
const HISTORY_MAX = 30;
const CLOSE_MS = 600;   // past the palette's exit (kit.css, 330ms), so its rows stay until it has gone
const PATHS = {
  compass: "M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216ZM172.42,72.84l-64,32a8.05,8.05,0,0,0-3.58,3.58l-32,64A8,8,0,0,0,80,184a8.1,8.1,0,0,0,3.58-.84l64-32a8.05,8.05,0,0,0,3.58-3.58l32-64a8,8,0,0,0-10.74-10.74ZM138,138,97.89,158.11,118,118l40.15-20.07Z",
  search: "M229.66,218.34l-50.07-50.06a88.11,88.11,0,1,0-11.31,11.31l50.06,50.07a8,8,0,0,0,11.32-11.32ZM40,112a72,72,0,1,1,72,72A72.08,72.08,0,0,1,40,112Z",
};
const glyph = (name) => `<svg viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="${PATHS[name]}"/></svg>`;
const EDITABLE = 'input:not([type="checkbox"],[type="radio"],[type="button"],[type="submit"],[type="reset"],[type="range"],[type="color"],[type="file"],[type="image"],[type="hidden"]), textarea, select, [contenteditable]:not([contenteditable="false"])';

const session = {
  get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* not remembered */ } },
  json(k, d) { try { return JSON.parse(sessionStorage.getItem(k)) || d; } catch (e) { return d; } },
};

/* A URL as the dock compares it: path without a trailing slash, and the hash route ("#/" and
   "#" are the root) without one. */
function urlParts(href) {
  const u = new URL(href, location.href);
  const path = u.pathname.replace(/\/+$/, "") || "/";
  const hash = u.hash.replace(/^#/, "").replace(/\/+$/, "");
  return { origin: u.origin, path, hash, routed: href.includes("#"), at: u.pathname + u.search + u.hash };
}
/* Is url under place: its path equals or extends the place's ("/" only matches "/"), and when
   the place has a hash route the hash equals or extends that at a "/". */
function under(url, place) {
  if (url.origin !== place.origin) return false;
  const p = place.path;
  if (p === "/" ? url.path !== "/" : url.path !== p && !url.path.startsWith(p + "/")) return false;
  if (!place.routed) return true;
  if (!place.hash) return !url.hash;
  return url.hash === place.hash || url.hash.startsWith(place.hash + "/");
}
/* The most specific of items (links) that url is under, or null. */
function bestUnder(url, items) {
  let best = null, size = -1;
  items.forEach((a) => {
    const href = a.getAttribute("href");
    if (!href) return;
    const p = urlParts(href);
    const n = p.path.length + p.hash.length;
    if (under(url, p) && n > size) { best = a; size = n; }
  });
  return best;
}

const labelOf = (a) => (a.dataset.dockLabel || (a.querySelector(".ellipsis") || a).textContent || "").trim();
const iconOf = (a) => {
  const i = a.querySelector("i.ph, svg");
  return i ? i.cloneNode(true) : null;
};
const pinsOf = (aside) => (aside ? [...aside.querySelectorAll("a.nav-item[data-pin]")] : [])
  .filter((a) => /^[1-4]$/.test(a.dataset.pin))
  .sort((a, b) => a.dataset.pin - b.dataset.pin);
const hostOf = (shell) => {
  const host = shell.parentElement && shell.parentElement.closest(".g-shell");
  return host && host.querySelector(":scope > aside a.nav-item[data-pin]") ? host : null;
};

/* Every place in a rail, in rail order, with where it sits: its group, else its heading. */
function placesOf(aside, where0 = "") {
  if (!aside) return [];
  const out = [];
  let head = where0;
  aside.querySelectorAll(".nav-head, a.nav-item").forEach((el) => {
    if (el.classList.contains("nav-head")) { head = el.textContent.trim(); return; }
    const group = el.closest(".nav-group");
    const gl = group && group.querySelector(":scope > .nav-group-toggle .ellipsis, :scope > .nav-group-row .ellipsis");
    out.push({ el, href: el.getAttribute("href"), label: labelOf(el), group: gl ? gl.textContent.trim() : "", head,
      where: gl ? gl.textContent.trim() : head });
  });
  return out.filter((p) => p.href && p.label);
}

/* Filter: label starts with q, a word in it starts with q, q inside it, then the letters of q in
   order in the label, then in label and where; rail order breaks ties. */
const subseq = (q, s) => { let i = 0; for (const c of s) if (c === q[i]) i++; return i === q.length; };
function score(q, p) {
  const l = p.label.toLowerCase();
  if (l.startsWith(q)) return 0;
  if (l.split(/[\s/,.-]+/).some((w) => w.startsWith(q))) return 1;
  if (l.includes(q)) return 2;
  if (subseq(q, l)) return 3;
  if (subseq(q, (l + " " + p.where.toLowerCase()))) return 4;
  return -1;
}

const editing = (el) => !!(el && el.matches && el.matches(EDITABLE));

export function wireDock(shell, opts = {}) {
  if (!shell) return () => {};
  if (shell.gDock) return shell.gDock;
  const key = opts.key || (shell.querySelector(":scope > aside .g-rail-toggle") || { dataset: {} }).dataset.railKey || RAIL_KEY;
  const phone = matchMedia(PHONE);
  const coarse = matchMedia("(pointer: coarse)");
  const memKey = (href) => `${key}:dock:${href}`;
  const histKey = `${key}:dock:history`;

  const dock = document.createElement("nav");
  dock.className = "g-dock";
  dock.setAttribute("aria-label", "Dock");
  let host = null, sig = "", current = null, recorded = "";

  /* ---- where we are, and where we were */

  function record() {
    const aside = asideOf(shell);
    const here = urlParts(location.href);
    const pins = pinsOf(aside);
    const slot = bestUnder(here, pins) || pins.find((a) => a.getAttribute("aria-current") === "page");
    if (slot) session.set(memKey(slot.getAttribute("href")), here.at);
    if (recorded !== here.at) {
      recorded = here.at;
      const items = aside ? [...aside.querySelectorAll("a.nav-item")] : [];
      const place = bestUnder(here, items) || (aside && aside.querySelector('a.nav-item[aria-current="page"]'));
      const p = place ? place.getAttribute("href") : here.at;
      const hist = session.json(histKey, []).filter((h) => h.u !== here.at);
      hist.unshift({ u: here.at, p });
      session.set(histKey, JSON.stringify(hist.slice(0, HISTORY_MAX)));
    }
    // Where a guest's G mark goes: the newest page under another place than this one.
    const hist = session.json(histKey, []);
    const back = hist.find((h) => h.p !== (hist[0] && hist[0].p));
    const brand = shell.querySelector(":scope > aside .brand");
    dock.dataset.dockReturn = back ? back.u : (brand && brand.getAttribute("href")) || "/";
  }

  /* ---- the dock */

  function slotHtml(label, count, countLabel) {
    const l = document.createElement("span");
    l.className = "g-dock-label";
    l.textContent = label;
    const icon = document.createElement("span");
    icon.className = "g-dock-icon";
    if (count) {
      const c = document.createElement("span");
      c.className = "g-dock-count";
      c.textContent = count;
      if (countLabel) c.setAttribute("aria-label", countLabel);
      icon.append(c);
    }
    return [icon, l];
  }

  function render() {
    host = hostOf(shell);
    const aside = asideOf(shell);
    let pins = pinsOf(aside);
    if (host && pins.length === 4) pins = pins.slice(1);
    if (!pins.length && !host) {
      dock.remove();
      shell.removeAttribute("data-dock");
      sig = "";
      return;
    }
    const hostBrand = host && host.querySelector(":scope > aside .brand");
    const hostName = hostBrand ? (hostBrand.querySelector("b") || hostBrand).textContent.trim() : "";
    const next = (host ? `host:${hostName}|` : "") + pins.map((a) => {
      const b = a.querySelector(".badge");
      const i = a.querySelector("i.ph, svg");
      return [a.getAttribute("href"), labelOf(a), b ? b.textContent.trim() : "", i ? i.outerHTML.length + (i.getAttribute("class") || "") : ""].join("~");
    }).join("|");
    if (next !== sig) {
      sig = next;
      const slots = [];
      if (host) {
        const a = document.createElement("a");
        a.className = "g-dock-slot g-dock-host";
        const hostDock = host.querySelector(":scope > .g-dock");
        a.href = (hostDock && hostDock.dataset.dockReturn) || (hostBrand && hostBrand.getAttribute("href")) || "/";
        const [icon, l] = slotHtml(hostName || "Back");
        const mark = hostBrand && hostBrand.querySelector(".g-mark");
        icon.prepend(mark ? mark.cloneNode(true) : document.createElement("span"));
        a.append(icon, l);
        slots.push(a);
      }
      pins.forEach((item) => {
        const a = document.createElement("a");
        a.className = "g-dock-slot";
        a.href = item.getAttribute("href");
        a.dataset.slot = item.getAttribute("href");
        const b = item.querySelector(".badge");
        const [icon, l] = slotHtml(labelOf(item), b && b.textContent.trim(), b && b.getAttribute("aria-label"));
        const i = iconOf(item);
        if (i) icon.prepend(i);
        a.append(icon, l);
        slots.push(a);
      });
      const go = document.createElement("button");
      go.type = "button";
      go.className = "g-dock-slot g-dock-go";
      go.setAttribute("aria-haspopup", "dialog");
      go.setAttribute("aria-expanded", shell.hasAttribute("data-go-open") ? "true" : "false");
      const [gi, gl] = slotHtml("Go");
      gi.innerHTML = glyph("compass");
      go.append(gi, gl);
      slots.push(go);
      dock.replaceChildren(...slots);
      dock.style.setProperty("--g-dock-n", slots.length);
    }
    if (dock.parentNode !== shell) shell.append(dock);
    shell.setAttribute("data-dock", "");
    light();
    guest();
  }

  /* The current slot: the one the URL is under, else the pin the rail marks current. */
  function light() {
    const here = urlParts(location.href);
    const slots = [...dock.querySelectorAll("a.g-dock-slot[data-slot]")];
    const pins = pinsOf(asideOf(shell));
    const byUrl = bestUnder(here, slots);
    const marked = pins.find((a) => a.getAttribute("aria-current") === "page");
    const now = byUrl || (marked && slots.find((s) => s.dataset.slot === marked.getAttribute("href"))) || null;
    slots.forEach((s) => (s === now ? s.setAttribute("aria-current", "page") : s.removeAttribute("aria-current")));
    current = now ? now.dataset.slot : null;
    const back = host && dock.querySelector(".g-dock-host");
    const hostDock = host && host.querySelector(":scope > .g-dock");
    if (back && hostDock && hostDock.dataset.dockReturn) back.href = hostDock.dataset.dockReturn;
  }

  /* A guest under 721px hides its host's dock and top bar. */
  function guest() {
    if (!host) return;
    host.toggleAttribute("data-dock-guest", phone.matches && shell.isConnected);
  }

  function haptic() {
    try {
      const p = window.gshell && window.gshell.haptic && window.gshell.haptic("selection");
      if (p && p.catch) p.catch(() => {});
    } catch (e) { /* no shell, or it said no */ }
  }

  function navigate(href, replace) {
    const ev = new CustomEvent("g-dock:navigate", { bubbles: true, cancelable: true, detail: { href, replace } });
    if (!shell.dispatchEvent(ev)) return false;
    if (replace) location.replace(href);
    else location.assign(href);
    return true;
  }

  /* A tab bar answers the touch, not its release: a finger on a slot starts the switch at once
     (the click that follows is then spent), as UITabBar does. A mouse or a keyboard still acts
     on click. The dock never scrolls, so a touch on it is never the start of a swipe. */
  let pressed = null;
  dock.addEventListener("pointerdown", (e) => {
    pressed = null;
    if (e.pointerType === "mouse" || !e.isPrimary || e.button) return;
    const slot = e.target.closest(".g-dock-slot");
    if (!slot) return;
    pressed = slot;
    act(slot, e);
  });
  dock.addEventListener("pointercancel", () => { pressed = null; });
  dock.addEventListener("click", (e) => {
    const slot = e.target.closest(".g-dock-slot");
    if (!slot) return;
    if (pressed === slot) { e.preventDefault(); pressed = null; return; }
    pressed = null;
    act(slot, e);
  });
  function act(slot, e) {
    if (slot.classList.contains("g-dock-go")) { e.preventDefault(); toggle(); return; }
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return;
    e.preventDefault();
    if (open) close(true);
    if (slot.classList.contains("g-dock-host")) {
      haptic();
      navigate(slot.getAttribute("href"), true);
      return;
    }
    const href = slot.dataset.slot;
    if (href === current) { navigate(href, true); return; }
    haptic();
    navigate(session.get(memKey(href)) || href, true);
  }

  /* ---- Go: the palette */

  const pal = document.createElement("dialog");
  pal.className = "dlg cmdk g-palette";
  pal.setAttribute("data-palette", "");
  pal.setAttribute("aria-label", "Go");
  const field = document.createElement("div");
  field.className = "g-palette-field";
  field.innerHTML = glyph("search");
  const input = document.createElement("input");
  input.className = "cmdk-input";
  input.type = "text";
  input.placeholder = "Go to a place";
  input.setAttribute("aria-label", "Go to a place");
  input.setAttribute("autocomplete", "off");
  input.setAttribute("autocapitalize", "off");
  input.setAttribute("spellcheck", "false");
  input.setAttribute("enterkeyhint", "go");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "true");
  const list = document.createElement("div");
  list.className = "cmdk-list g-palette-list";
  list.setAttribute("role", "listbox");
  list.id = `g-palette-${Math.random().toString(36).slice(2, 8)}`;
  input.setAttribute("aria-controls", list.id);
  field.append(input);
  pal.append(field, list);
  const scrim = document.createElement("div");
  scrim.className = "g-palette-scrim";
  let open = false, sheet = false, closeTimer = 0, opener = null;

  function places() {
    const own = placesOf(asideOf(shell));
    if (!host) return own;
    const hb = host.querySelector(":scope > aside .brand b");
    const name = hb ? hb.textContent.trim() : "";
    return own.concat(placesOf(asideOf(host)).map((p) => ({ ...p, where: name, head: name, group: "", host: true })));
  }

  function row(p, opts2 = {}) {
    const a = document.createElement("a");
    a.className = "menu-item g-palette-item" + (opts2.child ? " g-palette-child" : "");
    a.href = p.href;
    a.setAttribute("role", "option");
    a.id = `${list.id}-${list.childElementCount}`;
    const i = iconOf(p.el);
    if (i) a.append(i);
    const l = document.createElement("span");
    l.className = "g-palette-label";
    l.textContent = p.label;
    a.append(l);
    if (opts2.where && p.where) {
      const w = document.createElement("span");
      w.className = "g-palette-where";
      w.textContent = p.where;
      a.append(w);
    }
    return a;
  }
  function heading(text) {
    const h = document.createElement("div");
    h.className = "cmdk-group";
    h.setAttribute("role", "presentation");
    h.textContent = text;
    return h;
  }

  function fill() {
    const q = input.value.trim().toLowerCase();
    const ps = places();
    list.replaceChildren();
    if (q) {
      const hits = ps.map((p, n) => ({ p, n, s: score(q, p) })).filter((h) => h.s >= 0)
        .sort((a, b) => a.s - b.s || a.n - b.n);
      hits.forEach((h) => list.append(row(h.p, { where: true })));
      if (!hits.length) {
        const e = document.createElement("div");
        e.className = "cmdk-empty";
        e.textContent = "No place matches";
        list.append(e);
      }
    } else {
      // Every place, as the rail has them, open: headings, and each group named over its
      // places. Typing filters; nothing waits behind another tap.
      let head = null, group = null;
      ps.forEach((p) => {
        if (p.head !== head) { head = p.head; group = null; if (head) list.append(heading(head)); }
        if (p.group !== group) {
          group = p.group;
          if (group) {
            const g = heading(group);
            g.classList.add("g-palette-sub");
            list.append(g);
          }
        }
        list.append(row(p, { child: !!p.group }));
      });
    }
    highlight(sheet ? -1 : 0);
  }

  const options = () => [...list.querySelectorAll(".g-palette-item")];
  function highlight(n) {
    const os = options();
    os.forEach((o, i) => {
      o.toggleAttribute("data-highlighted", i === n);
      o.setAttribute("aria-selected", i === n ? "true" : "false");
    });
    const on = os[n];
    if (on) {
      input.setAttribute("aria-activedescendant", on.id);
      on.scrollIntoView({ block: "nearest" });
    } else input.removeAttribute("aria-activedescendant");
  }
  const highlighted = () => options().findIndex((o) => o.hasAttribute("data-highlighted"));

  function choose(o) {
    if (!o) return;
    const href = o.getAttribute("href");
    close(true);
    const here = urlParts(location.href).at;
    if (urlParts(href).at === here) return;
    navigate(href, false);
  }

  list.addEventListener("click", (e) => {
    const o = e.target.closest(".g-palette-item");
    if (!o || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    choose(o);
  });
  input.addEventListener("input", () => { fill(); if (sheet && input.value) highlight(0); });
  input.addEventListener("keydown", (e) => {
    const n = options().length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!n) return;
      const at = highlighted();
      highlight(e.key === "ArrowDown" ? (at + 1) % n : (at <= 0 ? n - 1 : at - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(options()[Math.max(0, highlighted())]);
    }
  });
  pal.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
  pal.addEventListener("close", () => close(true));  // closed from outside (g-ui.js light dismiss)
  pal.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); } });
  scrim.addEventListener("click", () => close());
  pal.addEventListener("click", (e) => { if (e.target === pal && !sheet) close(); });

  function toggle() { if (open) close(); else show(); }
  function show() {
    if (open) return;
    clearTimeout(closeTimer);
    open = true;
    input.value = "";
    opener = document.activeElement;
    sheet = phone.matches && shell.hasAttribute("data-dock") && !shell.hasAttribute("data-dock-guest");
    pal.toggleAttribute("data-sheet", sheet);
    if (pal.parentNode !== shell) shell.append(pal);
    if (sheet && scrim.parentNode !== shell) shell.insertBefore(scrim, pal);
    fill();
    shell.setAttribute("data-go-open", "");
    const go = dock.querySelector(".g-dock-go");
    go && go.setAttribute("aria-expanded", "true");
    if (sheet) {
      // A sheet above the dock: the dock stays, so the dialog is not modal. A touch never brings
      // the keyboard up on its own (show() would focus the field, so the sheet takes focus
      // itself); a keyboard does.
      const touch = coarse.matches;
      pal.toggleAttribute("autofocus", touch);
      pal.tabIndex = -1;
      pal.show();
      scrim.setAttribute("data-open", "");
      if (!touch) input.focus();
      else if (document.activeElement === input) pal.focus();
    } else {
      pal.removeAttribute("autofocus");
      pal.showModal();
      input.focus();
    }
    shell.dispatchEvent(new CustomEvent("g-palette:open", { bubbles: true }));
  }
  function close(navigating = false) {
    if (!open) return;
    open = false;
    if (document.activeElement === input) input.blur();
    pal.close();
    scrim.removeAttribute("data-open");
    shell.removeAttribute("data-go-open");
    const go = dock.querySelector(".g-dock-go");
    go && go.setAttribute("aria-expanded", "false");
    closeTimer = setTimeout(() => { if (!open) list.replaceChildren(); }, CLOSE_MS);
    if (!navigating && opener && opener.isConnected && opener.focus) opener.focus({ preventScroll: true });
    shell.dispatchEvent(new CustomEvent("g-palette:close", { bubbles: true }));
  }
  shell.setAttribute("data-go", "");

  /* Cmd+K or Ctrl+K (never with Shift: that is the admin overlay). The innermost shell with Go
     answers; an outer one leaves it. */
  function onKey(e) {
    if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey || (e.key || "").toLowerCase() !== "k") return;
    if (!shell.isConnected || shell.querySelector(".g-shell[data-go]")) return;
    e.preventDefault();
    toggle();
  }
  function onSheetKey(e) {
    if (e.key === "Escape" && open && sheet) { e.preventDefault(); close(); }
  }

  /* ---- the dock steps aside while a field has focus */

  function typing() {
    const t = editing(document.activeElement);
    shell.toggleAttribute("data-dock-typing", t);
    kb();
  }
  const onFocusIn = () => typing();
  const onFocusOut = () => setTimeout(typing, 0);
  /* The keyboard's height, for the sheet to ride above it. */
  const vv = window.visualViewport;
  function kb() {
    const h = vv ? Math.max(0, Math.round(innerHeight - vv.height - vv.offsetTop)) : 0;
    shell.style.setProperty("--g-kb", `${h}px`);
  }

  /* ---- keep up with the rail and the page */

  let queued = false;
  const refresh = () => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      if (!shell.isConnected) return;
      render();
      record();
      light();
      if (open) fill();
    });
  };
  const railObs = new MutationObserver(refresh);
  const watchRail = () => {
    railObs.disconnect();
    const aside = asideOf(shell);
    if (aside) railObs.observe(aside, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["href", "aria-current", "data-pin", "data-dock-label", "class"] });
  };
  /* A host with a guest drops data-dock-guest when the guest goes, even if the guest's copy of
     this file never got to say so. */
  const mainObs = new MutationObserver(() => {
    if (shell.hasAttribute("data-dock-guest") && !shell.querySelector(":scope > main .g-shell[data-dock]")) shell.removeAttribute("data-dock-guest");
  });
  const main = shell.querySelector(":scope > main");
  if (main) mainObs.observe(main, { subtree: true, childList: true });
  const onPhone = () => { guest(); if (open) close(); };
  const onNav = () => refresh();

  watchRail();
  render();
  record();
  light();
  typing();
  addEventListener("keydown", onKey);
  addEventListener("keydown", onSheetKey);
  addEventListener("hashchange", onNav);
  addEventListener("popstate", onNav);
  addEventListener("pageshow", onNav);
  document.addEventListener("focusin", onFocusIn);
  document.addEventListener("focusout", onFocusOut);
  vv && vv.addEventListener("resize", kb);
  vv && vv.addEventListener("scroll", kb);
  phone.addEventListener("change", onPhone);

  function unwire() {
    railObs.disconnect();
    mainObs.disconnect();
    removeEventListener("keydown", onKey);
    removeEventListener("keydown", onSheetKey);
    removeEventListener("hashchange", onNav);
    removeEventListener("popstate", onNav);
    removeEventListener("pageshow", onNav);
    document.removeEventListener("focusin", onFocusIn);
    document.removeEventListener("focusout", onFocusOut);
    vv && vv.removeEventListener("resize", kb);
    vv && vv.removeEventListener("scroll", kb);
    phone.removeEventListener("change", onPhone);
    if (open) close(true);
    clearTimeout(closeTimer);
    dock.remove(); pal.remove(); scrim.remove();
    ["data-dock", "data-go", "data-dock-typing", "data-go-open"].forEach((a) => shell.removeAttribute(a));
    if (host && !host.querySelector(":scope > main .g-shell[data-dock]")) host.removeAttribute("data-dock-guest");
    delete shell.gDock;
  }
  unwire.open = show;
  unwire.close = close;
  shell.gDock = unwire;
  return unwire;
}
