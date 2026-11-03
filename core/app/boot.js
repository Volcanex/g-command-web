// The one entry every Preact page goes through (pages/CLAUDE.md, "Preact pages").
// A page's app.js calls `mount(Page)`: the kit is configured once, the component
// renders into the page's [data-page-app] slot inside the shell, and the shell's
// own chrome (nav, tabs, theme, reveal) stays as it is.
import { render } from "preact";
import { html, useState, useEffect, useCallback } from "../static/css/gsys/kit/html.js";
import { setIcons, configure } from "../static/css/gsys/kit/index.js";
import iconPaths from "./icon-paths.js";

export * from "../static/css/gsys/kit/html.js";
export * from "../static/css/gsys/kit/index.js";

setIcons(iconPaths);
configure({ offlineTitle: "Command is offline" });

export function mount(Page, props = {}) {
  const slot = document.querySelector("[data-page-app]");
  if (!slot) return;
  slot.textContent = "";
  render(html`<${Page} ...${props} />`, slot);
}

/* GET a JSON URL. A non-2xx answer or an {error} body throws. */
export async function getJson(url) {
  const r = await fetch(url, { credentials: "same-origin" });
  if (!r.ok) throw new Error(`${url.split("?")[0]} answered ${r.status}`);
  const body = await r.json();
  if (body && typeof body === "object" && !Array.isArray(body) && body.error) throw new Error(String(body.error));
  return body;
}

/* A load state {data, error, reload}, the shape the kit's Loaded takes. */
export function useJson(url) {
  const [state, setState] = useState({ data: undefined, error: null });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    getJson(url).then(
      (data) => live && setState({ data, error: null }),
      (error) => live && setState((s) => ({ data: s.data, error })),
    );
    return () => { live = false; };
  }, [url, tick]);
  return { ...state, reload };
}

/* A classic script (a CDN library the page used before its port), loaded once. */
const scripts = {};
export function loadScript(src) {
  return (scripts[src] ||= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => { delete scripts[src]; fail(new Error(`${src} did not load`)); };
    document.head.appendChild(s);
  }));
}
