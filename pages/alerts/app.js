// Alerts: the ntfy alert spine (GET /api/alerts, core/api/alerts.py), newest first, the
// last 12 hours. The old native app had this screen; the thin shell draws the web, so it
// lives here. View contract (pages/CLAUDE.md, "New views"): PageHead, Loaded, Empty.
import { html, useState, useEffect, useCallback, PageHead, Loaded, Empty, Badge, SkeletonRows, mount } from "../../core/app/boot.js";
import "./app.css";

const TONE = { danger: ["danger", "Urgent"], warn: ["warn", "Warning"], accent: ["info", "Vital"] };

// What each failure means, so the error says what happened and what happens next.
const FAILED = {
  503: "Alerts are not set up on this server. Set NTFY_URL in its .env, then restart Command.",
  502: "The alert feed did not answer. Try again in a minute.",
  401: "You are signed out. Sign in again to see alerts.",
};

function useAlerts() {
  const [state, setState] = useState({ data: undefined, error: null });
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => { setState({ data: undefined, error: null }); setTick((t) => t + 1); }, []);
  useEffect(() => {
    let live = true;
    fetch("/api/alerts", { credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) throw { message: FAILED[r.status] || "Alerts did not load. Try again in a minute." };
        return r.json();
      })
      .catch((e) => { throw e && e.message ? e : { message: "Command could not be reached. Check the connection and try again." }; })
      .then((data) => live && setState({ data, error: null }), (error) => live && setState({ data: undefined, error }));
    return () => { live = false; };
  }, [tick]);
  return { ...state, reload };
}

const clock = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const day = new Intl.DateTimeFormat("en-GB", { weekday: "short", hour: "2-digit", minute: "2-digit" });
function when(t) {
  const d = new Date(t * 1000);
  return d.toDateString() === new Date().toDateString() ? clock.format(d) : day.format(d);
}

function Rows({ alerts }) {
  if (!alerts.length) return html`<${Empty} title="No alerts" desc="Nothing has been sent in the last 12 hours." />`;
  return html`<div class="card alerts-list"><div class="list">
    ${alerts.map((a) => {
      const tone = TONE[a.tone];
      return html`<div class="list-item" key=${a.id}>
        <a class="main" href=${a.link || "/"}>
          <span>${a.title}</span>
          ${a.message && html`<span class="sub">${a.message}</span>`}
        </a>
        <span class="end">
          ${tone && html`<${Badge} kind=${tone[0]}>${tone[1]}<//>`}
          <span class="when">${when(a.time)}</span>
        </span>
      </div>`;
    })}
  </div></div>`;
}

function Page() {
  const state = useAlerts();
  return html`
    <${PageHead} title="Alerts" sub="What the system sent you in the last 12 hours, newest first." />
    <${Loaded} state=${state} skeleton=${html`<${SkeletonRows} rows=${4} />`}>
      ${(data) => html`<${Rows} alerts=${data.alerts || []} />`}
    <//>`;
}

mount(Page);
