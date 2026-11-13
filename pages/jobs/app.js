import {
  html, PageHead, Loaded, Empty, ErrorState, SkeletonRows, Button, Badge,
  Dialog, Field, mount, useJson, useState, useEffect, toastOk, toastError,
} from "../../core/app/boot.js";
import "./app.css";

const VIEWS = [
  ["interviews", "Interviews"], ["roster", "Daytime tap"], ["applications", "Applications"],
  ["letters", "Cover letters"], ["questions", "Screening questions"], ["runs", "Runs"],
];
const TONES = { ok: "ok", warn: "warn", bad: "danger", inert: "plain" };
const plain = (value) => window.g?.plain ? window.g.plain(String(value ?? "")) : String(value ?? "");
const copy = (value) => plain(value).replace(/\s*[\u2014\u00b7]\s*/g, ", ");
const when = (value) => {
  if (!value) return "Not recorded";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? copy(value) : date.toLocaleString("en-GB");
};
const url = (value) => {
  try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) ? u.href : null; }
  catch { return null; }
};

function Status({ record }) {
  return html`<${Badge} kind=${TONES[record.tone] || "plain"}>${copy(record.status_label)}<//>`;
}

function Actions({ record }) {
  const href = url(record.url);
  return html`<div class="jobs-actions">
    ${href && html`<a class="btn btn-secondary btn-sm" href=${href} target="_blank" rel="noreferrer">Open the form</a>`}
    ${record.has_pdf && html`<a class="btn btn-secondary btn-sm" href=${`/api/jobs/cv/${encodeURIComponent(record.stem)}.pdf`}>Download CV</a>`}
  </div>`;
}

function LetterText({ letter }) {
  return html`<div class="jobs-stack">
    <div class="jobs-muted num">${letter.words} words</div>
    <div class="prose jobs-letter">${letter.text}</div>
  </div>`;
}

function Roster({ items, onDetails }) {
  if (!items.length) return html`<${Empty} title="Nothing waiting" desc="No application is parked on a human check. Review the archive for other outcomes.">
    <a class="btn btn-secondary btn-sm" href="/jobs?view=applications">View applications</a><//>`;
  return html`<div class="jobs-stack">
    ${items.map((record) => html`<article class="card jobs-stack" key=${record.stem}>
      <div class="jobs-heading"><h2 class="card-title">${plain(record.employer)}</h2><${Status} record=${record} /></div>
      <p>${plain(record.role)}</p><p class="jobs-muted">${copy(record.send_note)}</p>
      <${Actions} record=${record} />
      <${Button} size="sm" kind="tertiary" onClick=${() => onDetails(record)}>View record<//>
      ${record.letter ? html`<details><summary>Read cover letter</summary><${LetterText} letter=${record.letter} /></details>`
        : html`<p class="jobs-muted">No cover letter on disk matches this record.</p>`}
    </article>`)}
    <div class="card prose"><h2>Finish an application</h2><ol>
      <li>Open the form and fill it in. The earlier run did not save a draft.</li>
      <li>Attach the archived CV and use the matching cover letter.</li>
      <li>Complete the human check in your own browser.</li>
      <li>Press Submit once and wait. Confirm from the acknowledgement email.</li>
    </ol></div>
  </div>`;
}

function Applications({ data, onDetails }) {
  if (!data.items.length) return html`<${Empty} title="No applications yet" desc="Refresh after the Jobs runner records an application." />`;
  return html`<div class="jobs-stack">${data.groups.map((group) => html`<section class="card jobs-stack" key=${group.status}>
    <div class="jobs-heading"><h2 class="card-title">${copy(group.label)}</h2><${Badge} kind=${TONES[group.tone] || "plain"} class="num">${group.items.length}<//></div>
    <p class="jobs-muted">${copy(group.gloss)}</p>
    <div class="table-wrap"><table class="table jobs-table" aria-label=${copy(group.label)}>
      <thead><tr><th>Employer and role</th><th>Sent</th><th>What happened</th><th>Record</th></tr></thead>
      <tbody>${group.items.map((record) => html`<tr key=${record.stem}>
        <td><strong>${plain(record.employer)}</strong><div>${plain(record.role)}</div><div class="jobs-muted">${copy(record.ats)}</div></td>
        <td class="num">${record.sent_at || "Not recorded"}</td><td>${copy(record.send_note)}</td>
        <td><${Button} size="sm" kind="tertiary" onClick=${() => onDetails(record)}>View record<//>
          ${record.has_pdf && html`<a href=${`/api/jobs/cv/${encodeURIComponent(record.stem)}.pdf`}>Download CV</a>`}</td>
      </tr>`)}</tbody>
    </table></div>
  </section>`)}</div>`;
}

function Letters({ items }) {
  if (!items.length) return html`<${Empty} title="No cover letters yet" desc="Refresh after a cover letter has been prepared in Jobs." />`;
  return html`<div class="jobs-stack">${items.map((letter) => html`<article class="card jobs-stack" key=${letter.stem} id=${letter.stem}>
    <h2 class="card-title">${plain(letter.stem)}</h2>
    ${letter.applications.length ? html`<div class="jobs-stack">${letter.applications.map((record) => html`
      <a href=${`/jobs?view=applications&application=${encodeURIComponent(record.stem)}`}>${plain(record.employer)}: ${plain(record.role)}</a>`)}</div>`
      : html`<${Badge} kind="warn">No archived application matches this filename<//>`}
    <${LetterText} letter=${letter} />
  </article>`)}</div>`;
}

function Answer({ value }) {
  const text = typeof value === "boolean" ? (value ? "Yes" : "No")
    : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "");
  return html`<div class="prose jobs-letter">${text}</div>`;
}

function Questions({ items }) {
  if (!items.length) return html`<${Empty} title="No screening questions yet" desc="Refresh after the runner records a question it cannot answer." />`;
  return html`<div class="jobs-stack">${items.map((q) => html`<article class="card jobs-stack" key=${q.id}>
    <div class="jobs-heading"><h2 class="card-title">${plain(q.question)}</h2><${Badge} kind=${q.open ? "warn" : "ok"}>${q.open ? "Needs Gabriel" : "Answered"}<//></div>
    ${q.answer_found ? html`<${Answer} value=${q.answer} />` : html`<p class="jobs-muted">${q.answer_key
      ? `The answer key ${q.answer_key} no longer resolves. Check the screening answers in Jobs.`
      : "No answer is recorded. Gabriel needs to supply this in Jobs."}</p>`}
    ${q.note && html`<p class="jobs-muted">${copy(q.note)}</p>`}
    ${(q.blocked || []).length > 0 && html`<div><span class="jobs-muted">Blocked applications</span><ul>${q.blocked.map((b) => html`<li>${copy(b)}</li>`)}</ul></div>`}
    ${q.answer_key && html`<div class="jobs-muted mono">${q.answer_key}</div>`}
  </article>`)}</div>`;
}

function RunStatus({ run }) {
  if (run.end?.outcome === "stood-down") return html`<${Badge} kind="plain">Stood down<//>`;
  if (run.crashed) return html`<${Badge} kind="danger">Died during run<//>`;
  if (!run.finished) return html`<${Badge} kind="warn">Unfinished<//>`;
  if (run.walled.length || run.end?.notice_walled) return html`<${Badge} kind="warn">Ended on a bot wall<//>`;
  return html`<${Badge} kind="plain">Finished<//>`;
}

function Runs({ data }) {
  const b = data.budget;
  return html`<div class="jobs-stack">
    <section class="card jobs-stack"><h2 class="card-title">Pace</h2>
      <div class="jobs-actions"><${Badge} kind=${b.blocked ? "warn" : "ok"} class="num">${Math.floor(b.available)} of ${b.capacity} tokens<//>
        <span class="num">${Math.ceil(b.cooling_s / 60)} min cooldown</span><span class="num">${b.streak} consecutive walls</span></div>
      <p class="jobs-muted">Refills at ${b.rate_per_hour} tokens an hour. Search costs ${b.costs.search}; description costs ${b.costs.describe}; application costs ${b.costs.apply}.</p>
      ${b.blocked && html`<p>The next run will stand down: ${copy(b.blocked)}</p>`}
      ${b.walls.length > 0 && html`<details><summary>Recent bot walls</summary><div class="jobs-stack">${b.walls.map((w) => html`<div key=${w.at}>
        <span class="num">Wall ${w.streak}, ${when(w.at)}, ${Math.round((w.until - w.at) / 60)} min cooldown</span><p class="jobs-muted">${copy(w.note)}</p></div>`)}</div></details>`}
    </section>
    ${!data.items.length ? html`<${Empty} title="No runs yet" desc="Refresh after the Jobs timer records a batch." />`
      : data.items.map((run) => html`<article class="card jobs-stack" key=${run.name}>
        <div class="jobs-heading"><h2 class="card-title">${plain(run.name)}</h2><${RunStatus} run=${run} /></div>
        <div class="jobs-actions jobs-muted num"><span>${run.applied.length} sent</span><span>${run.confirmed.length} confirmed by the page</span>
          <span>${run.assists.length} human requests</span><span>${run.walled.length} walls</span><span>${run.skipped.length} skipped</span>
          ${run.end?.elapsed_s != null && html`<span>${run.end.elapsed_s} seconds</span>`}</div>
        <details><summary>View every event (${run.rows.length})</summary><div class="table-wrap"><table class="table jobs-table" aria-label="Run events">
          <thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead><tbody>${run.rows.map((row, i) => html`<tr key=${i}>
            <td class="num">${when(row.at)}</td><td>${copy(row.event).replaceAll("_", " ")}</td>
            <td>${Object.entries(row).filter(([k, v]) => !["at", "event"].includes(k) && v != null && v !== "")
              .map(([k, v]) => html`<div><span class="mono jobs-muted">${k}: </span>${copy(typeof v === "object" ? JSON.stringify(v) : v)}</div>`)}</td>
          </tr>`)}</tbody></table></div></details>
      </article>`)}
  </div>`;
}

function RecordDialog({ record, onClose }) {
  return html`<${Dialog} open=${!!record} onClose=${onClose} title=${record ? plain(record.employer) : "Application record"}
    desc=${record ? plain(record.role) : ""} size="lg" foot=${html`<${Button} onClick=${onClose}>Close record<//>`}>
    ${record && html`<div class="jobs-stack"><${Status} record=${record} /><p>${copy(record.status_gloss)}</p>
      <p>${copy(record.send_note)}</p><${Actions} record=${record} />
      <dl class="jobs-record">${[["Sent", record.sent_at], ["Route", record.ats], ["Salary stated", record.salary_stated],
        ["Notes", record.notes], ["Archived record", record.stem], ["CV checksum", record.sha256]]
        .filter(([, value]) => value != null && value !== "").map(([label, value]) => html`<div><dt>${label}</dt><dd>${copy(value)}</dd></div>`)}</dl>
      ${(record.claims || []).length > 0 && html`<details><summary>Read archived CV claims (${record.claims.length})</summary><ul>${record.claims.map((claim) => html`<li>${plain(claim.text)}</li>`)}</ul></details>`}
    </div>`}
  <//>`;
}

const OUTCOMES = {
  passed: ["Passed", "ok"], failed: ["Failed", "danger"], missed: ["Missed", "danger"],
  held: ["Held", "plain"], upcoming: ["Booked", "info"], unknown: ["Not confirmed", "warn"],
};
const STATUSES = [["interviewing", "Interviewing"], ["lead", "Lead"], ["offer", "Offer"],
  ["rejected", "Rejected"], ["withdrawn", "Withdrawn"], ["closed", "Closed"]];
const day = (iso, time) => {
  const d = new Date(`${String(iso).slice(0, 10)}T12:00:00`);
  if (Number.isNaN(d.getTime())) return copy(iso);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) + (time ? ` ${time}` : "");
};
const onCalendar = (r) => `/calendar?item=${encodeURIComponent(r.slug)}&date=${encodeURIComponent(r.date)}`;

async function post(path, body) {
  const r = await fetch(path, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.status === 401) { location.href = "/login"; throw new Error("Signed out"); }
  let j = {};
  try { j = await r.json(); } catch { /* empty body */ }
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `Jobs answered ${r.status}`);
  return j;
}

function Outcome({ value }) {
  const [label, kind] = OUTCOMES[value] || OUTCOMES.unknown;
  return html`<${Badge} kind=${kind}>${label}<//>`;
}

function Rounds({ item }) {
  if (!item.rounds.length) {
    const word = (item.match || [item.company])[0];
    return html`<p class="jobs-muted">No rounds yet. Put the next one on the calendar with ${plain(word)} in the title and it shows here.</p>`;
  }
  return html`<div class="table-wrap"><table class="table jobs-rounds" aria-label=${`${plain(item.company)} rounds`}>
    <thead><tr><th>When</th><th>Round</th><th>With</th><th>How it went</th></tr></thead>
    <tbody>${item.rounds.map((r) => html`<tr key=${r.date}>
      <td class="num">${r.slug ? html`<a href=${onCalendar(r)}>${day(r.date, r.time)}</a>` : day(r.date, r.time)}</td>
      <td>${plain(r.stage)}</td><td>${plain(r.with || "")}</td><td><${Outcome} value=${r.outcome} /></td>
    </tr>`)}</tbody>
  </table></div>`;
}

function Recruiter({ person }) {
  const tel = person.phone && String(person.phone).replace("(0)", "").replace(/[^+\d]/g, "");
  return html`<dd>${plain(person.name)}${person.agency && `, ${plain(person.agency)}`}
    <div class="jobs-actions jobs-muted">
      ${person.email && html`<a href=${`mailto:${person.email}`}>${person.email}</a>`}
      ${tel && html`<a class="num" href=${`tel:${tel}`}>${plain(person.phone)}</a>`}
    </div></dd>`;
}

function Interview({ item, onLog }) {
  const next = item.next_round;
  return html`<article class="card jobs-stack" id=${item.id}>
    <div class="jobs-heading"><h2 class="card-title">${plain(item.company)}</h2>
      <${Badge} kind=${item.tone}>${copy(item.status_label)}<//></div>
    ${item.role && html`<p>${plain(item.role)}</p>`}
    <dl class="jobs-facts">
      <div><dt>Salary</dt><dd>${item.salary ? plain(item.salary) : "Not stated yet"}
        ${item.salary_note && html`<div class="jobs-muted">${copy(item.salary_note)}</div>`}</dd></div>
      ${item.location && html`<div><dt>Where</dt><dd>${copy(item.location)}</dd></div>`}
      ${item.recruiter?.name && html`<div><dt>Recruiter</dt><${Recruiter} person=${item.recruiter} /></div>`}
    </dl>
    ${(next || item.next) && html`<div class="jobs-next">
      <span class="jobs-muted">Next</span>
      ${next && html`<a href=${onCalendar(next)}><span class="num">${day(next.date, next.time)}</span>, ${plain(next.stage)}</a>`}
      ${item.next && html`<p>${copy(item.next)}</p>`}
    </div>`}
    ${item.feedback && html`<div class="jobs-next"><span class="jobs-muted">Feedback</span><p>${copy(item.feedback)}</p></div>`}
    <${Rounds} item=${item} />
    <details><summary>About the role, contacts and history</summary><div class="jobs-stack jobs-more">
      ${item.about && html`<p>${copy(item.about)}</p>`}
      ${(item.contacts || []).length > 0 && html`<div><span class="jobs-muted">At the company</span><ul>${item.contacts.map((c) => html`<li key=${c.name + c.email}>
        ${plain(c.name)}${c.title && `, ${plain(c.title)}`}${c.email && html` <a href=${`mailto:${c.email}`}>${c.email}</a>`}</li>`)}</ul></div>`}
      ${(item.log || []).length > 0 && html`<div><span class="jobs-muted">Log</span><ul>${[...item.log].reverse().map((l, i) => html`<li key=${i}>
        <span class="num">${day(l.date)}</span>: ${copy(l.text)}</li>`)}</ul></div>`}
      ${(item.sources || []).length > 0 && html`<div><span class="jobs-muted">Where this came from</span><ul class="jobs-muted">${item.sources.map((src, i) => html`<li key=${i}>${copy(src)}</li>`)}</ul></div>`}
    </div></details>
    <${Button} size="sm" onClick=${() => onLog(item)}>Log an update<//>
  </article>`;
}

function Interviews({ data, onLog }) {
  if (!data.items.length) return html`<${Empty} title="No interviews logged" desc="Ask an agent to log one from the recruiter's email, or run gjobs interview add on the server." />`;
  const live = data.items.filter((x) => x.live);
  const done = data.items.filter((x) => !x.live);
  return html`<div class="jobs-stack">
    ${!data.calendar && html`<p class="jobs-muted">The calendar did not answer, so booked rounds are missing. Refresh to try again.</p>`}
    ${live.map((item) => html`<${Interview} key=${item.id} item=${item} onLog=${onLog} />`)}
    ${done.length > 0 && html`<details class="jobs-done"><summary>Crossed off: ${done.map((x) => plain(x.company)).join(", ")}</summary>
      <div class="jobs-stack">${done.map((item) => html`<${Interview} key=${item.id} item=${item} onLog=${onLog} />`)}</div>
    </details>`}
  </div>`;
}

function InterviewCounts({ items }) {
  const n = (status) => items.filter((x) => x.status === status).length;
  const crossed = items.filter((x) => !x.live).length;
  return html`<div class="jobs-actions jobs-muted num" aria-label="Interview summary">
    ${n("offer") > 0 && html`<span>${n("offer")} with an offer</span>`}
    <span>${n("interviewing")} interviewing</span><span>${n("lead")} leads</span><span>${crossed} crossed off</span>
  </div>`;
}

function LogDialog({ item, onClose, onSaved }) {
  const [f, setF] = useState({ status: "", next: "", note: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (item) setF({ status: item.status, next: item.next || "", note: "" }); }, [item]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const body = {};
  if (item && f.status !== item.status) body.status = f.status;
  if (item && f.next.trim() !== (item.next || "")) body.next = f.next.trim();
  if (f.note.trim()) body.note = f.note.trim();
  const save = async () => {
    setBusy(true);
    try { await post(`/api/jobs/interviews/${encodeURIComponent(item.id)}`, body); toastOk("Update logged", plain(item.company)); onSaved(); }
    catch (e) { toastError(e, "Update not logged"); } finally { setBusy(false); }
  };
  return html`<${Dialog} open=${!!item} onClose=${onClose} size="sm" busy=${busy}
      title=${item ? `Log an update for ${plain(item.company)}` : "Log an update"}
      foot=${html`<${Button} kind="secondary" onClick=${onClose}>Cancel<//>
        <${Button} kind="primary" busy=${busy} disabled=${!Object.keys(body).length} onClick=${save}>Log update<//>`}>
    <${Field} label="Status" id="iv-status"><span class="select-wrap"><select id="iv-status" class="select" value=${f.status} onChange=${set("status")}>
      ${STATUSES.map(([id, label]) => html`<option key=${id} value=${id}>${label}</option>`)}</select></span><//>
    <${Field} label="Next step" optional hint="One line. Clear it once nothing is pending." id="iv-next">
      <input id="iv-next" class="input" value=${f.next} onInput=${set("next")} /><//>
    <${Field} label="Note" optional hint="Goes in the log under today's date." id="iv-note">
      <textarea id="iv-note" class="textarea" rows="3" value=${f.note} onInput=${set("note")}></textarea><//>
  <//>`;
}

function Sources({ data }) {
  return html`<details class="card jobs-sources"><summary>Where these records come from</summary>
    <p class="jobs-muted">Read from Jobs on every request. Read at ${when(data.read_at)}.</p>
    <div class="jobs-stack">${data.summary.sources.map((s) => html`<div key=${s.path}>
      <div>${copy(s.label)}: <span class="num">${s.n} ${s.unit}</span></div><div class="jobs-muted mono">${s.path}</div>
      <div class="jobs-muted num">Last written ${when(s.mtime)}</div>
    </div>`)}</div>
  </details>`;
}

function Page() {
  const params = new URLSearchParams(location.search);
  const view = VIEWS.some(([id]) => id === params.get("view")) ? params.get("view") : "interviews";
  const state = useJson(`/api/jobs?view=${view}`);
  const [selected, setSelected] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const [logging, setLogging] = useState(null);
  return html`
    <${PageHead} title="Jobs" sub="Interviews, applications, and what needs your help.">
      <${Button} size="sm" onClick=${state.reload}>Refresh records<//>
    <//>
    <nav class="tabs jobs-tabs" aria-label="Jobs views">${VIEWS.map(([id, title]) => html`
      <a class="tab" aria-current=${view === id ? "page" : undefined} href=${`/jobs?view=${id}`}>${title}</a>`)}</nav>
    ${state.error && state.data !== undefined && html`<${ErrorState} title="Jobs records did not refresh" error=${new Error("The records below are from the previous load. Try again for the latest records.")} retry=${state.reload} />`}
    <${Loaded} state=${state.error && state.data === undefined ? { ...state, error: new Error("Jobs records could not be read. Try again.") } : state}
      skeleton=${html`<${SkeletonRows} rows=${4} />`}>
      ${(data) => {
        const record = selected || (!dismissed && data.items.find((r) => r.stem === params.get("application")));
        return html`${view === "interviews" ? html`<${InterviewCounts} items=${data.items} />`
          : html`<div class="jobs-actions jobs-muted num" aria-label="Archive summary">
          <span>${data.summary.tap} waiting on a human check</span><span>${data.summary.open_questions} open questions</span>
          <span>${data.summary.counts.CONFIRMED || 0} sent and confirmed</span>
          <span>${Object.values(data.summary.counts).reduce((a, b) => a + b, 0)} archived records</span>
        </div>`}
        ${view === "interviews" && html`<${Interviews} data=${data} onLog=${setLogging} />`}
        ${view === "roster" && html`<${Roster} items=${data.items} onDetails=${setSelected} />`}
        ${view === "applications" && html`<${Applications} data=${data} onDetails=${setSelected} />`}
        ${view === "letters" && html`<${Letters} items=${data.items} />`}
        ${view === "questions" && html`<${Questions} items=${data.items} />`}
        ${view === "runs" && html`<${Runs} data=${data} />`}
        <${Sources} data=${data} />
        <${RecordDialog} record=${record} onClose=${() => { setSelected(null); setDismissed(true); }} />
        <${LogDialog} item=${logging} onClose=${() => setLogging(null)} onSaved=${() => { setLogging(null); state.reload(); }} />`;
      }}
    <//>`;
}

mount(Page);
