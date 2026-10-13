/* g-command-web chrome interactions on g-design:
   off-canvas nav (data-nav-open, .g-nav-toggle, .g-scrim), theme and
   density toggles via g.theme/g.density, active nav link (direct or by tab
   group), footer clock. */
(() => {
  /* reveal the page: this script is deferred, so every body <style> has been
     parsed by now and the content can enter without a restyle jump */
  const main = document.querySelector(".site-main");
  if (main) { main.classList.add("g-ready", "enter"); }

  window.toggleNav = (force) => {
    const open = force !== undefined ? force : !document.body.hasAttribute("data-nav-open");
    document.body.toggleAttribute("data-nav-open", open);
    document.querySelector(".g-nav-toggle")?.setAttribute("aria-expanded", open);
  };
  document.querySelector(".g-scrim")?.addEventListener("click", () => toggleNav(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggleNav(false); });
  /* close the sheet when a nav link is chosen */
  document.querySelectorAll(".nav-drawer-section a").forEach((a) =>
    a.addEventListener("click", () => toggleNav(false)));

  document.getElementById("t-theme")?.addEventListener("click", () => {
    g.theme(document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light");
  });
  document.getElementById("t-density")?.addEventListener("click", () => {
    g.density(document.documentElement.hasAttribute("data-density") ? "comfortable" : "compact");
  });

  /* a page reached through a tab strip lights its group's entry */
  const here = location.pathname.replace(/\/$/, "") || "/";
  const links = [...document.querySelectorAll(".nav-drawer-section a, .side-foot a")];
  const path = (a) => a.getAttribute("href").split("?")[0].replace(/\/$/, "") || "/";
  let current = links.filter((a) => path(a) === here);
  const group = document.querySelector(".g-subnav")?.dataset.tabs;
  if (!current.length && group) current = links.filter((a) => a.dataset.tabs === group);
  current.forEach((a) => a.setAttribute("aria-current", "page"));
  document.querySelector('.g-subnav [aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });

  const clock = document.querySelector("[data-clock]");
  if (clock) {
    const tick = () => { clock.textContent = new Date().toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); };
    tick();
    setInterval(tick, 30000);
  }
})();
