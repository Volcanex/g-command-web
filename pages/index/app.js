// Home, at /: a tile per place Gabriel goes, each with a live line where one is
// cheap. Every line comes from an API an existing page already calls, and a
// failed fetch leaves the line off rather than breaking the grid.
import { html, useState, useEffect, PageHead, mount, getJson } from "../../core/app/boot.js";
import "./app.css";

const BRAIN = window.BRAIN_API || "/api/brain";
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;

/* Each line resolves to {text, tone} or null. Same sources as the pages:
   /system reads the brain status, the dashes read the panels. */
const LINES = {
  async system() {
    const d = await getJson(`${BRAIN}/api/status`);
    const services = (d.services || []).filter((s) => s.state !== "paused");
    const down = services.filter((s) => s.state === "down").length;
    if (down) return { text: `${plural(down, "service")} down`, tone: "danger" };
    return { text: `All ${services.length} services up`, tone: "ok" };
  },
  async calendar() {
    const d = await getJson("/api/panels/calendar");
    return d.state === "ok" && d.meta ? { text: d.meta } : null;
  },
  async tickets() {
    const d = await getJson("/api/panels/tickets");
    return d.state === "ok" && d.meta ? { text: d.meta } : null;
  },
  async todos() {
    const d = await getJson(`${BRAIN}/api/todos?status=open`);
    const items = Array.isArray(d) ? d : d.todos || [];
    return { text: `${items.length} open` };
  },
};

const TILES = [
  { href: "/ops", label: "System", icon: "heartbeat", line: "system", note: "What is down, compute, crons" },
  { href: "/studio", label: "Studio", icon: "paint-brush-broad", note: "Edit and publish the sites" },
  { href: "/home", label: "Life", icon: "sun-horizon", note: "Today, todos, money, the brief" },
  { href: "/full-dash", label: "Full dash", icon: "gauge", note: "Life and system at once" },
  { href: "/calendar", label: "Calendar", icon: "calendar-blank", line: "calendar", note: "Every dated todo" },
  { href: "/todos", label: "Todos", icon: "check-square", line: "todos", note: "Open todos across the brain" },
  { href: "/tickets", label: "Tickets", icon: "ticket", line: "tickets", note: "g-admin tickets, every project" },
  { href: "/notes", label: "Notes", icon: "list-bullets", note: "Every note in the brain" },
  { href: "/brain", label: "Brain", icon: "brain", note: "The knowledge base" },
  { href: "/drive", label: "Files", icon: "squares-four", note: "Workspaces and uploads" },
  { href: "/sessions", label: "Terminal", icon: "terminal", note: "tmux on any host" },
  { href: "/browser", label: "Browser", icon: "browser", note: "The always-on Chrome" },
  { href: "/runners", label: "Runners", icon: "devices", note: "The device fleet" },
  { href: "/projects", label: "Projects", icon: "folders", note: "Every project at a glance" },
  { href: "/levels", label: "Levels", icon: "stairs", note: "Gates and charters" },
  { href: "/design", label: "Design", icon: "palette", note: "The g-design language" },
  { href: "/diagram", label: "Diagram", icon: "graph", note: "The system drawn" },
];

function Tile({ tile, line }) {
  return html`<li class="card tile tile-1x1 home-tile">
    <div class="tile-head">
      <a class="tile-title ellipsis" href=${tile.href}>${tile.label}</a>
      <i class=${`ph ph-${tile.icon} muted`} aria-hidden="true"></i>
    </div>
    <div class="tile-body">
      ${line
        ? html`<p class=${`tile-strong home-line${line.tone ? " is-" + line.tone : ""}`}>${line.text}</p>`
        : null}
      <p class="muted tile-note">${tile.note}</p>
    </div>
  </li>`;
}

function Home() {
  const [lines, setLines] = useState({});
  useEffect(() => {
    let live = true;
    for (const [key, load] of Object.entries(LINES)) {
      load().then(
        (line) => live && line && setLines((l) => ({ ...l, [key]: line })),
        () => {}, // a failed source leaves its line off
      );
    }
    return () => { live = false; };
  }, []);
  return html`
    <${PageHead} title="Home" sub="Everything here, one click away." />
    <ul class="tile-grid home-tiles" aria-label="Places">
      ${TILES.map((t) => html`<${Tile} key=${t.href} tile=${t} line=${t.line && lines[t.line]} />`)}
    </ul>`;
}

mount(Home);
