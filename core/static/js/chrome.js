/* g-command-web chrome interactions on g-design:
   off-canvas nav (data-nav-open, .g-nav-toggle, .g-scrim), theme and
   density toggles via g.theme/g.density, active nav link, footer clock. */
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

  const here = location.pathname.replace(/\/$/, "") || "/";
  document.querySelectorAll(".nav-drawer-section a").forEach((a) => {
    const path = a.getAttribute("href").split("?")[0].replace(/\/$/, "") || "/";
    if (path === here || (path === "/home" && here === "/")) a.setAttribute("aria-current", "page");
  });

  const clock = document.querySelector("[data-clock]");
  if (clock) {
    const tick = () => { clock.textContent = new Date().toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); };
    tick();
    setInterval(tick, 30000);
  }
})();
