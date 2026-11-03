/* g-design@1.6.0 g-ui-preact, vendored, do not edit. Update: node scripts/vendor-preact.mjs from the g-design repo. */
// Building blocks on g-design classes: toasts, dialogs, buttons, menus, states, page head,
// fields, badges and a few hooks. Every visual is a g.css or kit.css class; this file only
// composes them. Nothing here knows which app it is in: what an app adds (where errors are
// reported, what the button says) comes in through configure().
import { html, useEffect, useLayoutEffect, useRef, useState, useCallback } from "./html.js";
import { Icon } from "./icon.js";

/* ------------------------------------------------------------------ app wiring */

/* report(err) files an error with whoever looks after the app and resolves true when it was
   sent; without it, errors carry no report button. offlineTitle heads an ErrorState whose
   error.code is "offline". errorCopy maps an error code to [title, sentence] for ErrorState:
   the sentence says what happened and what to do next, and the server's terse message for that
   code ("No such collection.") moves under Details. Codes it leaves out keep the server's
   message as the body, and errorFallback is the body when there is no message at all. */
const config = {
  report: null,
  reportLabel: "Report this",
  reportedLabel: "Reported",
  offlineTitle: "Cannot reach the server",
  errorCopy: {},
  errorFallback: "Something went wrong while loading this.",
};
export function configure(opts) { Object.assign(config, opts); }

/* ------------------------------------------------------------------ toasts */

export const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const esc = escapeHtml;

/* g.toast renders title/desc as HTML, so everything is escaped here first. */
export function toast(opts) {
  const o = typeof opts === "string" ? { title: opts } : { ...opts };
  o.title = esc(o.title);
  if (o.desc) o.desc = esc(o.desc);
  return showToast(o);
}
/* g.toast as is: title and desc are HTML. Escape anything that came from data. */
export function showToast(o) {
  if (window.g && window.g.toast) return window.g.toast(o);
  console.info("[toast]", o.title, o.desc || "");
  return { update() {}, dismiss() {}, progress() {} };
}
export const toastOk = (title, desc) => toast({ title, desc, kind: "ok" });

/* Every error a person sees: the sentence in the toast's text, the redacted raw error
   (err.extra.raw) under it in small type when the server sent one, and the report action. */
export const rawOf = (err) => (err && err.extra && typeof err.extra.raw === "string" ? err.extra.raw : "");
export const sendable = (err) => !!config.report && !(err && (err.code === "aborted" || err.name === "AbortError"));
export const toastError = (err, title) => {
  const raw = rawOf(err);
  return showToast({
    title: esc(title || "That did not work"),
    desc: esc((err && err.message) || String(err || "")) + (raw ? `<div class="mono faint wrap-any">${esc(raw)}</div>` : ""),
    kind: "danger",
    duration: 10000,
    action: sendable(err) ? { label: config.reportLabel, onClick: () => { config.report(err); } } : undefined,
  });
};

/* The report button on an error shown in place (ErrorState, dialogs). Null when the app
   configured no report(). */
export function ReportButton({ error, size = "sm", kind = "tertiary" }) {
  const [state, setState] = useState("idle");
  if (!sendable(error)) return null;
  const send = async () => {
    setState("busy");
    setState((await config.report(error)) ? "sent" : "idle");
  };
  return html`<${Button} kind=${kind} size=${size} busy=${state === "busy"} disabled=${state === "sent"} onClick=${send}>
    ${state === "sent" ? config.reportedLabel : config.reportLabel}<//>`;
}

/* ------------------------------------------------------------------ dialog */

/* Native <dialog class="dlg">. Focus moves into it on open (an [autofocus]
   element, else the first field, else the first button) and returns to
   whatever opened it on close. Escape and a backdrop click close it unless
   `busy` is set. */
export function Dialog({ open, onClose, title, desc, size = "md", busy = false, children, foot, class: cls = "", label }) {
  const ref = useRef(null);
  const opener = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      opener.current = document.activeElement;
      el.showModal();
      requestAnimationFrame(() => {
        const target = el.querySelector("[autofocus]") ||
          el.querySelector(".dlg-body input:not([type=hidden]):not([disabled]), .dlg-body textarea, .dlg-body select") ||
          el.querySelector(".dlg-foot .btn-primary, .dlg-foot .btn-danger, .dlg-foot .btn");
        target && target.focus();
      });
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);
  useEffect(() => () => {
    const o = opener.current;
    if (o && o.isConnected && typeof o.focus === "function") o.focus();
  }, []);
  useEffect(() => {
    if (open) return;
    const o = opener.current;
    if (o && o.isConnected && typeof o.focus === "function") o.focus();
    opener.current = null;
  }, [open]);
  const onCancel = (e) => { e.preventDefault(); if (!busy) onClose && onClose(); };
  const onClick = (e) => { if (e.target === ref.current && !busy) onClose && onClose(); };
  const titleId = useId("dlg-title");
  return html`<dialog ref=${ref} class=${`dlg dlg-${size} ${cls}`} onCancel=${onCancel} onClick=${onClick}
      aria-labelledby=${title ? titleId : undefined} aria-label=${!title ? label : undefined}>
    ${open && html`
      <div class="dlg-body">
        ${title && html`<div class="dlg-head"><h2 class="dlg-title" id=${titleId}>${title}</h2>
          <button class="btn btn-tertiary btn-sm btn-icon dlg-x" type="button" aria-label="Close" onClick=${() => !busy && onClose && onClose()} disabled=${busy}><${Icon} name="x" /></button></div>`}
        ${desc && html`<p class="dlg-desc">${desc}</p>`}
        ${children}
      </div>
      ${foot && html`<div class="dlg-foot">${foot}</div>`}`}
  </dialog>`;
}

let idSeq = 0;
export function useId(prefix = "id") {
  const r = useRef(null);
  if (r.current === null) r.current = `${prefix}-${++idSeq}`;
  return r.current;
}

/* Confirm dialog for one decision. `danger` makes the confirm button red. */
export function Confirm({ open, onClose, onConfirm, title, desc, confirmLabel = "Confirm", danger = false, children }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { await onConfirm(); onClose(); }
    catch (e) { toastError(e); }
    finally { setBusy(false); }
  };
  return html`<${Dialog} open=${open} onClose=${onClose} title=${title} desc=${desc} size="sm" busy=${busy}
    foot=${html`
      <button class="btn btn-secondary" type="button" onClick=${onClose} disabled=${busy}>Cancel</button>
      <${Button} kind=${danger ? "danger" : "primary"} busy=${busy} onClick=${run} icon=${danger ? "trash" : null}>${confirmLabel}<//>`}>
    ${children}
  <//>`;
}

/* ------------------------------------------------------------------ buttons */

export function Button({ kind = "secondary", size, icon, busy, children, class: cls = "", type = "button", ...rest }) {
  const c = `btn btn-${kind} ${size ? "btn-" + size : ""} ${!children ? "btn-icon" : ""} ${cls}`;
  return html`<button class=${c} type=${type} data-loading=${busy ? "" : undefined} aria-busy=${busy ? "true" : undefined} ...${rest}>
    ${icon && html`<${Icon} name=${icon} />`}${children && html`<span>${children}</span>`}
    <span class="spinner" aria-hidden="true"></span>
  </button>`;
}

export function IconButton({ icon, label, size = "sm", kind = "tertiary", tip = true, ...rest }) {
  return html`<button class=${`btn btn-${kind} btn-${size} btn-icon`} type="button" aria-label=${label} data-tip=${tip ? label : undefined} ...${rest}>
    <${Icon} name=${icon} /></button>`;
}

/* Copy to clipboard with g-design's copy animation (.copy-btn[data-copied]). */
export function CopyButton({ text, label = "Copy", size = "sm", kind = "secondary", class: cls = "" }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef(0);
  const copy = async () => {
    let ok = true;
    try { await navigator.clipboard.writeText(String(text ?? "")); }
    catch {
      ok = fallbackCopy(String(text ?? ""));
    }
    if (!ok) { toast({ title: "Copy did not work", desc: "Select the text and copy it by hand.", kind: "danger" }); return; }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1800);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  return html`<button class=${`btn btn-${kind} btn-${size} copy-btn ${cls}`} type="button" onClick=${copy} data-copied=${copied ? "" : undefined}>
    <span class="copy-icons" dangerouslySetInnerHTML=${{ __html: copyIcons() }}></span>
    ${label && html`<span class="copy-label">${copied ? "Copied" : label}</span>`}
    <span class="sr-only" aria-live="polite">${copied ? "Copied to clipboard" : ""}</span>
  </button>`;
}
function copyIcons() {
  const g = window.g;
  return g && g.icon ? g.icon("copy") + g.icon("check") : "";
}
export function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.append(ta); ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch {}
  ta.remove();
  return ok;
}

/* ------------------------------------------------------------------ menus */

/* A popover menu anchored to its trigger.
   items: [{label, icon, onClick, danger, href, target, disabled} | {heading} | "-"]
   side="right" opens it beside its button, bottoms level, for a button at the foot of a rail:
   opening upward there covers the rail's last links. Where there is no room beside it (a
   phone's sheet) it opens above or below as usual. */
export function Menu({ label, icon = "dots-three", items, trigger, align = "end", side, size = "sm", kind = "tertiary" }) {
  const id = useId("menu");
  const menuRef = useRef(null);
  const btnRef = useRef(null);
  const place = () => {
    const m = menuRef.current, b = btnRef.current;
    if (!m || !b) return;
    m.style.maxHeight = "";
    const r = b.getBoundingClientRect();
    if (side === "right" && r.right + 8 + m.offsetWidth <= innerWidth - 8) {
      m.style.setProperty("--_origin", "left bottom");
      m.style.left = r.right + 8 + "px";
      m.style.top = Math.max(8, r.bottom - m.offsetHeight) + "px";
      return;
    }
    const fitsBelow = r.bottom + 4 + m.offsetHeight < innerHeight;
    const fitsAbove = r.top - 4 - m.offsetHeight > 0;
    const below = fitsBelow || !fitsAbove;
    m.style.setProperty("--_origin", below ? "top" : "bottom");
    const left = align === "end" ? r.right - m.offsetWidth : r.left;
    m.style.left = Math.max(8, Math.min(left, innerWidth - m.offsetWidth - 8)) + "px";
    m.style.top = (below ? r.bottom + 4 : r.top - m.offsetHeight - 4) + "px";
    if (below && !fitsBelow) m.style.maxHeight = innerHeight - r.bottom - 12 + "px";
  };
  const onToggle = (e) => {
    const open = e.newState === "open";
    btnRef.current && btnRef.current.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) { place(); const first = menuRef.current.querySelector(".menu-item:not(:disabled)"); first && first.focus({ preventScroll: true }); }
  };
  const onKey = (e) => {
    const list = [...menuRef.current.querySelectorAll(".menu-item:not(:disabled)")];
    const cur = list.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); (list[(cur + 1) % list.length] || list[0]).focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (list[(cur - 1 + list.length) % list.length] || list[0]).focus(); }
    if (e.key === "Tab") menuRef.current.hidePopover();
  };
  const pick = (it) => (e) => {
    menuRef.current.hidePopover();
    btnRef.current && btnRef.current.focus();
    it.onClick && it.onClick(e);
  };
  return html`
    ${trigger ? trigger({ ref: btnRef, popovertarget: id, "aria-haspopup": "menu", "aria-expanded": "false" }) : html`
      <button ref=${btnRef} class=${`btn btn-${kind} btn-${size} btn-icon`} type="button" popovertarget=${id}
        aria-haspopup="menu" aria-expanded="false" aria-label=${label} data-tip=${label}><${Icon} name=${icon} /></button>`}
    <div ref=${menuRef} id=${id} class="menu" popover="auto" role="menu" onToggle=${onToggle} onKeyDown=${onKey}>
      ${items.filter(Boolean).map((it) => it === "-" ? html`<hr class="separator" />` :
        it.heading ? html`<div class="menu-heading">${it.heading}</div>` :
        it.href ? html`<a class=${`menu-item ${it.danger ? "danger" : ""}`} role="menuitem" href=${it.href} target=${it.target} rel=${it.target ? "noopener" : undefined}
            onClick=${() => menuRef.current.hidePopover()}>${it.icon && html`<${Icon} name=${it.icon} />`}<span>${it.label}</span></a>` :
        html`<button class=${`menu-item ${it.danger ? "danger" : ""}`} role="menuitem" type="button" disabled=${it.disabled} onClick=${pick(it)}>
          ${it.icon && html`<${Icon} name=${it.icon} />`}<span>${it.label}</span></button>`)}
    </div>`;
}

/* ------------------------------------------------------------------ states */

export function Empty({ icon = "info", title, desc, children }) {
  return html`<div class="empty">
    <${Icon} name=${icon} />
    <div class="e-title">${title}</div>
    ${desc && html`<div class="e-desc">${desc}</div>`}
    ${children && html`<div class="empty-actions">${children}</div>`}
  </div>`;
}

/* A designed error in the slot the data would have filled. The redacted raw error stays
   visible in small type; configure's errorCopy supplies the plain sentence per code. */
export function ErrorState({ error, retry, title }) {
  const code = error && error.code;
  const [t0, sentence] = config.errorCopy[code] || [];
  const msg = (error && error.message) || "";
  const t = title || t0 || (code === "not_found" ? "Not found" :
    code === "denied" ? "You do not have access to this" :
    code === "offline" ? config.offlineTitle : "This did not load");
  const body = sentence || msg || config.errorFallback;
  const detail = sentence && msg && msg !== sentence ? msg : "";
  const raw = rawOf(error);
  return html`<div class="empty state-error" role="alert">
    <${Icon} name="warning-circle" />
    <div class="e-title">${t}</div>
    <div class="e-desc">${body}</div>
    ${raw && html`<div class="e-desc mono faint wrap-any">${raw}</div>`}
    ${detail && html`<details class="state-error-more"><summary>Details</summary><div class="e-desc faint">${detail}</div></details>`}
    <div class="empty-actions">
      ${retry && html`<button class="btn btn-secondary btn-sm" type="button" onClick=${retry}>Try again</button>`}
      <${ReportButton} error=${error || { message: body }} />
    </div>
  </div>`;
}

/* Skeleton rows that mirror a list while it loads. */
export function SkeletonRows({ rows = 4, height = 40 }) {
  return html`<div class="skel-rows" aria-busy="true" aria-label="Loading">
    ${Array.from({ length: rows }, (_, i) => html`<div class="skeleton" style=${`height:${height}px;width:${100 - (i % 3) * 12}%`}></div>`)}
  </div>`;
}

/* Wraps a load state {data, error, reload}: skeleton, error, or children(data). */
export function Loaded({ state, skeleton, children }) {
  if (state.error && state.data === undefined) return html`<${ErrorState} error=${state.error} retry=${state.reload} />`;
  if (state.data === undefined) return skeleton || html`<${SkeletonRows} />`;
  return children(state.data);
}

/* ------------------------------------------------------------------ layout */

export function PageHead({ title, count, children, sub }) {
  return html`<div class="page-head">
    <div class="page-head-text">
      <h1 class="page-title">${title}${count != null && html` <span class="badge badge-plain num">${count}</span>`}</h1>
      ${sub && html`<p class="page-sub">${sub}</p>`}
    </div>
    ${children && html`<div class="page-actions">${children}</div>`}
  </div>`;
}

export function Field({ label, hint, error, optional, count, max, children, id, class: cls = "" }) {
  const over = max && count > max;
  return html`<div class=${`field ${cls}`}>
    ${label && html`<div class="field-top"><label class="label" for=${id}>${label}${optional && html` <span class="optional">optional</span>`}</label>
      ${max && html`<span class=${`char-count num ${over ? "over" : ""}`} aria-live="polite">${count || 0} of ${max}</span>`}</div>`}
    ${children}
    ${error ? html`<div class="error" role="alert"><${Icon} name="warning-circle" size="14" />${error}</div>` : hint && html`<div class="hint">${hint}</div>`}
  </div>`;
}

export const Badge = ({ kind, children, class: cls = "" }) => html`<span class=${`badge ${kind ? "badge-" + kind : ""} ${cls}`}>${children}</span>`;

/* ------------------------------------------------------------------ hooks */

export function useEvent(target, type, handler, deps = []) {
  useEffect(() => {
    target.addEventListener(type, handler);
    return () => target.removeEventListener(type, handler);
  }, deps);
}

export function useDebounced(value, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/* Re-run g-design's behaviour layer (tooltips, tabs, copy, hold buttons) on a subtree. */
export function useGInit(ref, deps = []) {
  useEffect(() => { if (ref.current && window.g && window.g.init) window.g.init(ref.current); }, deps);
}

export const useToggle = (init = false) => {
  const [v, setV] = useState(init);
  return [v, useCallback((x) => setV((p) => (typeof x === "boolean" ? x : !p)), [])];
};
