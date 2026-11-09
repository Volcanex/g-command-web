/* The essentials (Home's agenda card, pages/index): an element with
   data-lines="<panel>" gets that panel's bullets as up to three plain lines.
   The agenda panel (core/panels/agenda.py) already turns a brain failure into
   a line; this only covers Command itself not answering, so the slot is never
   blank. */
(() => {
  const essentials = [...document.querySelectorAll("[data-lines]")];
  if (!essentials.length) return;
  const plain = (t) => (window.g && window.g.plain ? window.g.plain(t) : String(t));
  const key = (el) => `g-lines:${el.dataset.lines}`;
  const fill = (el, lines, keep) => {
    const texts = lines.slice(0, 3).map(plain);
    el.replaceChildren(...texts.map((text) => {
      const p = document.createElement("p");
      p.className = "essentials-line";
      p.textContent = text;
      return p;
    }));
    // The last good lines, for the next visit this session to show at once (the inline script
    // after the slot, pages/index), then refresh in place.
    if (keep) try { sessionStorage.setItem(key(el), JSON.stringify(texts)); } catch (e) { /* not kept */ }
    document.dispatchEvent(new Event("g-essentials"));
  };
  for (const el of essentials) {
    fetch(`/api/panels/${encodeURIComponent(el.dataset.lines)}`, { credentials: "same-origin" })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then((d) => {
        const items = ((d.blocks || [])[0] || {}).items || [];
        const lines = items.map((item) => item.text).filter(Boolean);
        fill(el, lines.length ? lines : [d.message || "Calendar unavailable: no lines came back."], lines.length > 0);
      }, (e) => fill(el, [`Calendar unavailable: Command did not answer (${e.message}).`]));
  }
})();
