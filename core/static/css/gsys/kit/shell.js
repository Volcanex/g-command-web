/* g-design@1.6.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// The app shell (g-design .g-shell): sidebar with brand, nav and user foot, the top bar, the
// phone nav sheet, and the theme switch. The app passes in what is its own (brand name, nav
// items, menu items, what closes the sheet) as props; nothing here knows its routes.
import { html, useEffect, useState } from "./html.js";
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

/* A rail parent with its children, one level deep (kit.css .nav-group). The parent is a page
   (`item`, NavItem props); `children` are NavItems given class "nav-child". The children show
   while the parent or a child is current (`current`), and the twist opens them by hand. */
export function NavGroup({ item, current, label = "Show pages", children }) {
  const [manual, setManual] = useState(null);
  const open = manual === null ? !!current : manual;
  return html`<div class="nav-group" data-open=${open ? "" : undefined}>
    <div class="nav-group-row">
      <${NavItem} ...${item} />
      <button class="nav-twist" type="button" aria-label=${label} aria-expanded=${open ? "true" : "false"}
        onClick=${() => setManual(!open)}></button>
    </div>
    <div class="nav-children">${children}</div>
  </div>`;
}

/* ------------------------------------------------------------------ sidebar */

export function Brand({ href, name }) {
  return html`<a class="brand" href=${href}>
    <span class="g-mark" aria-hidden="true"></span>
    <b>${name}</b>
  </a>`;
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

/* brand, nav and foot fill the sidebar; title shows in the top bar on a phone; actions sit
   at the top bar's end. topbar=false drops the top bar (an app that draws its own). The bar is
   .app-topbar, plus .has-actions when it carries actions, so an app can drop a bar that is only
   the menu button wherever the rail sits beside the content. */
export function AppShell({ brand, nav, foot, title, actions, topbar = true, closeKey, children }) {
  const [open, setOpen] = useNavSheet(closeKey);
  return html`<div class="g-shell" data-nav-open=${open ? "" : undefined}>
    <aside aria-label="Main">
      ${brand}
      ${nav}
      ${foot}
    </aside>
    <main>
      ${topbar && html`<header class=${`topbar app-topbar${actions ? " has-actions" : ""}`}>
        <${NavToggle} open=${open} setOpen=${setOpen} />
        <span class="topbar-title show-sm">${title}</span>
        <span class="grow"></span>
        ${actions}
      </header>`}
      <div class="content" id="main-content">${children}</div>
    </main>
    <div class="g-scrim" onClick=${() => setOpen(false)}></div>
  </div>`;
}
