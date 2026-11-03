/* Live lines for hub tiles, Home's band heads and a hub's pulse tagline
   (compile.py hub_head, hub_tiles, core/panels/layout.py bands). An element
   with data-line="<key>" gets one short line from the source the key names.
   Every source is one an existing page already reads; a failed fetch leaves
   the line empty, and an empty line takes no room. */
(() => {
  const slots = [...document.querySelectorAll("[data-line]")];
  if (!slots.length) return;
  const BRAIN = window.BRAIN_API || "/api/brain";
  const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  const plain = (t) => (window.g && window.g.plain ? window.g.plain(t) : String(t));
  const memo = {};
  const get = (url) => (memo[url] ||= fetch(url, { credentials: "same-origin" }).then((r) => {
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }));

  const SOURCES = {
    async services() {
      const d = await get(`${BRAIN}/api/status`);
      const live = (d.services || []).filter((s) => s.state !== "paused");
      const down = live.filter((s) => s.state === "down").length;
      return down ? { text: `${plural(down, "service")} down`, tone: "danger" } : { text: `All ${live.length} services up`, tone: "ok" };
    },
    async todos() {
      const d = await get(`${BRAIN}/api/todos?status=open`);
      const items = Array.isArray(d) ? d : d.todos || [];
      return { text: `${items.length} open` };
    },
    async notes() {
      const d = await get(`${BRAIN}/api/home/stats`);
      const total = (d.kinds || []).reduce((n, k) => n + (k.total || 0), 0);
      return { text: plural(total, "note") };
    },
    async refs() {
      const d = await get(`${BRAIN}/api/home/stats`);
      return d.refs ? { text: `${d.refs.total_urls} URLs` } : null;
    },
    async panel(name) {
      const d = await get(`/api/panels/${encodeURIComponent(name)}`);
      return d.meta && d.state !== "error" ? { text: plain(d.meta) } : null;
    },
    /* the pulse brief's first line, as a hub's one-line tagline */
    async tagline(name) {
      const d = await get(`/api/panels/${encodeURIComponent(name)}`);
      const item = ((d.blocks || [])[0]?.items || [])[0];
      if (!item) return null;
      return { text: plain(item.label ? `${item.label}: ${item.text}` : item.text) };
    },
  };

  for (const el of slots) {
    const [key, arg] = el.dataset.line.split(":");
    const source = SOURCES[key];
    if (!source) continue;
    source(arg).then((line) => {
      if (!line || !line.text) return;
      el.textContent = line.text;
      if (line.tone) el.classList.add(`is-${line.tone}`);
      el.hidden = false;
    }, () => {});
  }
})();
