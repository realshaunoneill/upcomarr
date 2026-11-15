// upcomarr: optional enhancements. The page is complete without this file.
// - relabels days ("Today", "Tomorrow") against the viewer's clock, and hides days that have
//   passed since the page was built;
// - shows "Updated 12 minutes ago" instead of an absolute time;
// - the TV/Movies filter and "hide what is already on Plex", remembered per browser, in a bar that
//   stays at the top of the screen, with a count on each button.
(() => {
  "use strict";
  const root = document.documentElement;
  const body = document.body;
  const tz = root.dataset.tz || undefined;

  let store = null;
  try {
    store = window.localStorage;
  } catch {
    store = null;
  }

  let today;
  try {
    today = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  } catch {
    today = new Date().toISOString().slice(0, 10);
  }
  const plusDays = (iso, n) => {
    const d = new Date(`${iso}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const tomorrow = plusDays(today, 1);
  const weekday = new Intl.DateTimeFormat("en-GB", { weekday: "long", timeZone: "UTC" });

  for (const section of document.querySelectorAll("section.day[data-date]")) {
    const day = section.dataset.date;
    if (day < today) {
      section.dataset.past = "true";
      section.hidden = true;
      continue;
    }
    const name = section.querySelector(".day-name");
    if (name) {
      name.textContent = day === today ? "Today" : day === tomorrow ? "Tomorrow" : weekday.format(new Date(`${day}T12:00:00Z`));
    }
  }

  const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const ago = (iso) => {
    const seconds = (Date.parse(iso) - Date.now()) / 1000;
    const size = Math.abs(seconds);
    if (Number.isNaN(seconds)) return null;
    if (size < 60) return "just now";
    if (size < 3600) return relative.format(Math.round(seconds / 60), "minute");
    if (size < 86400) return relative.format(Math.round(seconds / 3600), "hour");
    return relative.format(Math.round(seconds / 86400), "day");
  };
  for (const el of document.querySelectorAll("time[data-relative]")) {
    const text = ago(el.getAttribute("datetime"));
    if (text) {
      el.title = el.textContent;
      el.textContent = text;
    }
  }

  const nav = document.querySelector(".filters");
  if (!nav) return;
  const buttons = [...nav.querySelectorAll("button[data-filter]")];
  const hideOnPlex = nav.querySelector("input[data-hide-on-plex]");
  const sections = [...document.querySelectorAll("section.day, section.recent")].filter((s) => s.dataset.past !== "true");
  const filteredEmpty = document.querySelector("[data-filtered-empty]");
  const current = () => body.dataset.filter || "all";
  const kindOk = (card, kind) => kind === "all" || card.dataset.kind === kind;
  const plexOk = (card) => !(hideOnPlex.checked && card.dataset.onPlex === "true");

  const apply = () => {
    const counts = { all: 0, tv: 0, movie: 0 };
    let any = false;
    for (const section of sections) {
      let visible = false;
      for (const card of section.querySelectorAll(".card")) {
        if (!plexOk(card)) continue;
        counts.all += 1;
        counts[card.dataset.kind] = (counts[card.dataset.kind] || 0) + 1;
        if (kindOk(card, current())) visible = true;
      }
      section.hidden = !visible;
      any ||= visible;
    }
    for (const el of nav.querySelectorAll("[data-count]")) el.textContent = String(counts[el.dataset.count] ?? 0);
    if (filteredEmpty) filteredEmpty.hidden = any;
  };
  // Changing the filter while scrolled down would leave the viewer somewhere arbitrary in a
  // shorter list, so go back to its start, just under the bar.
  const header = document.querySelector(".site-header");
  const toListStart = () => {
    const top = header ? header.offsetTop + header.offsetHeight : 0;
    if (window.scrollY > top) window.scrollTo({ top });
  };
  const setFilter = (value, user = false) => {
    body.dataset.filter = value;
    for (const button of buttons) button.setAttribute("aria-pressed", String(button.dataset.filter === value));
    store?.setItem("upcomarr.filter", value);
    apply();
    if (user) toListStart();
  };
  const setHide = (on, user = false) => {
    hideOnPlex.checked = on;
    body.toggleAttribute("data-hide-on-plex", on);
    store?.setItem("upcomarr.hideOnPlex", on ? "1" : "0");
    apply();
    if (user) toListStart();
  };

  for (const button of buttons) button.addEventListener("click", () => setFilter(button.dataset.filter, true));
  hideOnPlex.addEventListener("change", () => setHide(hideOnPlex.checked, true));

  const saved = store?.getItem("upcomarr.filter");
  setFilter(["all", "tv", "movie"].includes(saved) ? saved : "all");
  setHide(store?.getItem("upcomarr.hideOnPlex") === "1");
  nav.hidden = false;

  // Day headings stick just under the bar, whose height changes when it wraps on a narrow screen.
  const measure = () => root.style.setProperty("--filters-height", `${nav.offsetHeight}px`);
  measure();
  if ("ResizeObserver" in window) new ResizeObserver(measure).observe(nav);
  else window.addEventListener("resize", measure);
})();
