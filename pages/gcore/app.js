// gcore: the topology source of truth, read from the instance checkout on this
// host. Passport key names (values only on a click, through POST /reveal),
// services, the raw manifest and conventions.md. Data: /api/gcore (api.py).
import { html, useState, useEffect, useRef, Badge, Button, Loaded, mount, useJson } from "../../core/app/boot.js";
import "./app.css";

// Em dashes and middle dots in the conventions text are swapped for display (g-design).
const tidy = (t) => (window.g && window.g.tidy ? window.g.tidy(t) : String(t ?? ""));

const MASK = "•".repeat(12);

/* One passport row. The value is fetched when clicked and dropped when hidden. */
function Secret({ name, isSet }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState(null);
  if (!isSet) return html`<span class="masked">(empty)</span>`;
  const toggle = async () => {
    if (value !== null || error) { setValue(null); setError(null); return; }
    try {
      const r = await fetch("/api/gcore/reveal", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: name }),
      });
      if (!r.ok) throw new Error(`reveal ${r.status}`);
      setValue((await r.json()).value);
    } catch (e) {
      setError(e.message);
    }
  };
  const shown = value !== null || error;
  return html`<span class=${`secret ${shown ? "" : "masked"}`} title=${shown ? "Click to hide" : "Click to reveal"} onClick=${toggle}>
    ${error ? `Could not reveal: ${error}` : value !== null ? value : MASK}
  </span>`;
}

const health = (s) => s.health_url || (s.domain ? "via domain" : s.port ? "via port" : "via unit");

function Body({ data }) {
  const [raw, setRaw] = useState(false);
  const convRef = useRef(null);
  // token-select: LLM-token selection highlight, scoped to the prose block.
  // Wider scopes split badge and button labels into flex items.
  useEffect(() => {
    if (!convRef.current) return;
    convRef.current.setAttribute("data-tokens", "");
    if (!document.querySelector('script[src="/js/token-select.js"]')) {
      const s = document.createElement("script");
      s.src = "/js/token-select.js";
      document.body.appendChild(s);
    }
  }, []);
  return html`
    <section class="card gcore-block">
      <div class="block-head">
        <span class="card-title">Passport</span>
        <span class="hint">Secrets from the instance <code>.env</code>. Click a value to reveal it. Anyone with the site password can.</span>
      </div>
      <div class="table-wrap">
        <table class="table kv-table"><tbody>
          ${Object.entries(data.env || {}).map(([k, isSet]) => html`<tr key=${k}><td>${k}</td><td><${Secret} name=${k} isSet=${isSet} /></td></tr>`)}
        </tbody></table>
      </div>
    </section>
    <section class="card gcore-block">
      <div class="block-head"><span class="card-title">Services</span></div>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Service</th><th>Host</th><th>Domain</th><th>Unit</th><th>Health</th></tr></thead>
          <tbody>
            ${(data.manifest?.services || []).map((s) => html`<tr key=${s.id}>
              <td>${s.id}</td><td>${s.host || ""}</td><td>${s.domain || ""}</td><td>${s.unit || ""}</td><td>${health(s)}</td>
            </tr>`)}
          </tbody>
        </table>
      </div>
    </section>
    <section class="card gcore-block">
      <div class="block-head">
        <span class="card-title">manifest.json</span>
        <span class="spacer"></span>
        <${Button} size="sm" onClick=${() => setRaw((r) => !r)}>${raw ? "Hide raw" : "Show raw"}<//>
      </div>
      ${raw && html`<pre class="gcore-pre">${JSON.stringify(data.manifest, null, 2)}</pre>`}
    </section>
    <section class="card gcore-block">
      <div class="block-head"><span class="card-title">conventions.md</span></div>
      <pre class="gcore-pre" ref=${convRef}>${data.conventions ? tidy(data.conventions) : "No conventions file in this checkout."}</pre>
    </section>`;
}

function Gcore() {
  const state = useJson("/api/gcore");
  return html`
    <div class="page-head">
      <div class="page-head-text">
        <div class="row-tight">
          <h1 class="sr-only">Passport</h1>
          <${Badge} kind="plain">Topology source of truth<//>
        </div>
        <p class="page-sub">Read from the instance checkout on this host.</p>
      </div>
    </div>
    <${Loaded} state=${state}>${(data) => html`<${Body} data=${data} />`}<//>`;
}

mount(Gcore);
