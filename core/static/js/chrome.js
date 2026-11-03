/* g-command-web chrome interactions on g-design:
   off-canvas nav (data-nav-open, .g-nav-toggle, .g-scrim), theme and
   density toggles via g.theme/g.density, the current rail link (the page's
   own, or the one its config names in data-nav-current), footer clock. The
   rail's groups, hover and pin are the kit's (gsys/kit/rail.js), which runs
   after this and opens the group holding the current link. */
(() => {
  /* reveal the page: this script is deferred, so every body <style> has been
     parsed by now and the content can enter without a restyle jump */
  const main = document.querySelector(".site-main");
  if (main) { main.classList.add("g-ready", "enter"); }

  window.toggleNav = (force) => {
    const open = force !== undefined ? force : !document.body.hasAttribute("data-nav-open");
    document.body.toggleAttribute("data-nav-open", open);
    const t = document.querySelector(".g-nav-toggle"); t?.setAttribute("aria-expanded", open); t?.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  };
  document.querySelector(".g-scrim")?.addEventListener("click", () => toggleNav(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggleNav(false); });
  /* close the sheet when a nav link is chosen */
  document.querySelectorAll("a.nav-item").forEach((a) =>
    a.addEventListener("click", () => toggleNav(false)));

  document.getElementById("t-theme")?.addEventListener("click", () => {
    g.theme(document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light");
  });
  document.getElementById("t-density")?.addEventListener("click", () => {
    g.density(document.documentElement.hasAttribute("data-density") ? "comfortable" : "compact");
  });

  /* the current rail link: this URL's own, else the one the page's config
     names (a detail route lights its view). A child lights itself. */
  const here = location.pathname.replace(/\/$/, "") || "/";
  const links = [...document.querySelectorAll(".nav-list a.nav-item")];
  const path = (a) => a.getAttribute("href").split("?")[0].replace(/\/$/, "") || "/";
  let current = links.filter((a) => path(a) === here);
  if (!current.length) current = links.filter((a) => path(a) === (document.body.dataset.navCurrent || ""));
  current.forEach((a) => a.setAttribute("aria-current", "page"));
  /* bring it into view by scrolling the rail only, never sideways: the
     collapsed rail clips its open-width items, and scrollIntoView would slide them */
  const rail = current[0]?.closest("aside");
  if (rail) {
    const r = current[0].getBoundingClientRect(), box = rail.getBoundingClientRect();
    if (r.bottom > box.bottom || r.top < box.top) rail.scrollTop += r.top - box.top - box.height / 2;
  }

  const clock = document.querySelector("[data-clock]");
  if (clock) {
    const tick = () => { clock.textContent = new Date().toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); };
    tick();
    setInterval(tick, 30000);
  }
})();
