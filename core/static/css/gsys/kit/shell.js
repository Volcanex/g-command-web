/* g-design@1.6.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// The app shell (g-design .g-shell): sidebar with brand, nav and user foot, the top bar, the
// phone nav sheet, and the theme switch. The app passes in what is its own (brand name, nav
// items, menu items, what closes the sheet) as props; nothing here knows its routes.
import { html, useEffect, useRef, useState } from "./html.js";
import { wireRailToggle, railPinned, groupOpen, setGroupOpen, RAIL_KEY } from "./rail.js";
import { Icon } from "./icon.js";
import { Menu } from "./core.js";

/* ------------------------------------------------------------------ theme */

export function currentTheme() {
  return document.documentElement.getAttribute("data-theme") || "dark";
}
export function setTheme(mode) {
  if (window.g && window.g.theme) window.g.theme(mode);
  else if (mode === "dark") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);
}
/* The menu item that flips dark and light, for a user menu. */
export function themeMenuItem() {
  const theme = currentTheme();
  return { label: theme === "light" ? "Use dark theme" : "Use light theme", icon: theme === "light" ? "moon" : "sun",
    onClick: () => setTheme(theme === "light" ? "dark" : "light") };
}

/* ------------------------------------------------------------------ nav sheet */

/* Under 720px the sidebar is an off-canvas sheet. It closes when closeKey changes (pass the
   current route, so following a link closes it) and on Escape, and focuses its first link
   when it opens. */
export function useNavSheet(closeKey) {
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [closeKey]);
  useEffect(() => {
    const el = document.querySelector(".g-shell");
    if (el) el.toggleAttribute("data-nav-open", open);
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    addEventListener("keydown", onKey);
    const first = document.querySelector(".g-shell > aside a, .g-shell > aside button");
    first && first.focus();
    return () => removeEventListener("keydown", onKey);
  }, [open]);
  return [open, setOpen];
}

export function NavToggle({ open, setOpen }) {
  return html`<button class="btn btn-tertiary btn-sm btn-icon g-nav-toggle" type="button" aria-label=${open ? "Close menu" : "Open menu"}
    aria-expanded=${open ? "true" : "false"} onClick=${() => setOpen(!open)}><${Icon} name="list" /></button>`;
}

/* A rail item. children go after the label (presence dots, counts), badge last.
   Any other prop (data-*, aria-*) lands on the link. */
export function NavItem({ to, icon, label, current, badge, onClick, target, children, ...rest }) {
  return html`<a class="nav-item" href=${to} aria-current=${current ? "page" : undefined} onClick=${onClick}
      target=${target} rel=${target ? "noopener" : undefined} ...${rest}>
    <${Icon} name=${icon} /><span class="ellipsis">${label}</span>
    ${children}
    ${badge}
  </a>`;
}

/* A rail group, one level deep (kit.css .nav-group): the parent is a disclosure row with the
   group's icon and label that opens and closes its children in place, never a page of its own.
   Open by default; closed by hand is remembered per viewer under the rail's key, and a group
   holding the current page (`current`) always opens. `children` are NavItems given class
   "nav-child", each with its own icon. */
export function NavGroup({ id, icon, label, current, railKey = RAIL_KEY, children }) {
  const ref = useRef(null);
  const [open, setOpen] = useState(() => !!current || groupOpen(id, railKey));
  useEffect(() => { if (current) setOpen(true); }, [current]);
  const flip = () => {
    const next = !open;
    setOpen(next);
    if (ref.current) setGroupOpen(ref.current, next, railKey);
  };
  return html`<div ref=${ref} class="nav-group" data-group=${id} data-open=${open ? "" : undefined}>
    <button class="nav-item nav-group-toggle" type="button" aria-expanded=${open ? "true" : "false"} onClick=${flip}>
      <${Icon} name=${icon} /><span class="ellipsis">${label}</span><span class="nav-caret" aria-hidden="true"></span>
    </button>
    <div class="nav-children">${children}</div>
  </div>`;
}

/* ------------------------------------------------------------------ sidebar */

/* The brand, with the rail's pin toggle beside it (rail.js: "Keep open", then "Collapse").
   railKey names where this rail's state is remembered, so two apps on one page (Studio inside
   Command) keep their own; railOpen starts it pinned open until the viewer collapses it;
   collapse=false leaves the toggle out. */
export function Brand({ href, name, collapse = true, railKey = RAIL_KEY, railOpen = false }) {
  return html`<div class="brand-row">
    <a class="brand" href=${href}>
      <span class="g-mark" aria-hidden="true"></span>
      <b>${name}</b>
    </a>
    ${collapse && html`<${RailToggle} railKey=${railKey} railOpen=${railOpen} />`}
  </div>`;
}

export function RailToggle({ railKey = RAIL_KEY, railOpen = false }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) wireRailToggle(ref.current, railKey, railOpen); }, []);
  const pinned = railPinned(railKey, railOpen);
  return html`<button ref=${ref} class="g-rail-toggle" type="button" aria-label=${pinned ? "Collapse" : "Keep open"}
    aria-pressed=${pinned ? "true" : "false"}></button>`;
}

/* The signed-in person at the foot of the sidebar, with their menu. menuSide="right" opens the
   menu beside the rail instead of over its last links (Menu's side). */
export function UserFoot({ name, email, initials, items, menuLabel = "Account", menuSide }) {
  return html`<div class="side-foot">
    <span class="avatar" aria-hidden="true">${initials}</span>
    <span class="who"><span>${name}</span><span>${email}</span></span>
    <${Menu} label=${menuLabel} icon="dots-three" align="end" side=${menuSide} items=${items} />
  </div>`;
}

/* ------------------------------------------------------------------ shell */

/* brand, nav and foot fill the sidebar (railKey: the same key as the Brand's toggle); title
   shows in the top bar at every width (g-navigation R7: the bar says where you are, and the
   page head never repeats it; PageHead's h1 is .sr-only); actions sit
   at the top bar's end. topbar=false drops the top bar (an app that draws its own). The bar is
   .app-topbar, plus .has-actions when it carries actions, so an app can drop a bar that is only
   the menu button wherever the rail sits beside the content. */
export function AppShell({ brand, nav, foot, title, actions, topbar = true, closeKey, railKey = RAIL_KEY, railOpen = false, children }) {
  const [open, setOpen] = useNavSheet(closeKey);
  // The rail's first state, so a pinned rail never flashes collapsed; rail.js owns it after.
  const [rail] = useState(() => (railPinned(railKey, railOpen) ? "pinned" : "collapsed"));
  return html`<div class="g-shell" data-rail=${rail} data-nav-open=${open ? "" : undefined}>
    <aside aria-label="Main">
      ${brand}
      ${nav}
      ${foot}
    </aside>
    <main>
      ${topbar && html`<header class=${`topbar app-topbar${actions ? " has-actions" : ""}`}>
        <${NavToggle} open=${open} setOpen=${setOpen} />
        <span class="topbar-title">${title}</span>
        <span class="grow"></span>
        ${actions}
      </header>`}
      <div class="content" id="main-content">${children}</div>
    </main>
    <div class="g-scrim" onClick=${() => setOpen(false)}></div>
  </div>`;
}
