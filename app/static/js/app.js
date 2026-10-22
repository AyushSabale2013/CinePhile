(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  /* Navbar becomes solid after scrolling ---------------------------------- */
  const nav = $("#nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 24);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* Toast feedback (visibility of system status) -------------------------- */
  const toastEl = $("#toast");
  let toastTimer;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2600);
  }

  /* Carousel arrows ------------------------------------------------------- */
  $$(".row-wrap").forEach((wrap) => {
    const track = $(".row-track", wrap);
    $$(".row-btn", wrap).forEach((btn) =>
      btn.addEventListener("click", () =>
        track.scrollBy({ left: Number(btn.dataset.dir) * track.clientWidth * 0.85, behavior: "smooth" })
      )
    );
  });

  /* My List toggle (optimistic UI, undo-able) ----------------------------- */
  const badge = $("#list-count");
  function paint(btn, on) {
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-pressed", on);
    $(".ico", btn).textContent = on ? "✓" : "+";
    $(".lbl", btn).textContent = on ? "In My List" : "Add to My List";
  }
  $$(".list-toggle").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const was = btn.getAttribute("aria-pressed") === "true";
      paint(btn, !was);
      btn.disabled = true;
      try {
        const res = await fetch(`/api/my-list/${btn.dataset.movieId}`, { method: "POST", headers: { "X-Requested-With": "fetch" } });
        if (!res.ok) throw new Error();
        const data = await res.json();
        paint(btn, data.in_list);
        badge.textContent = data.count;
        badge.hidden = data.count === 0;
        toast(data.in_list ? `Added “${data.title}” to My List` : `Removed “${data.title}” from My List`);
      } catch {
        paint(btn, was);
        toast("Couldn't update your list. Please try again.");
      } finally {
        btn.disabled = false;
      }
    })
  );

  /* Live search with keyboard support ------------------------------------- */
  const input = $("#q");
  const list = $("#results");
  const status = $("#search-status");
  let items = [], active = -1, timer, ctrl;

  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); active = -1; }
  function highlight(i) {
    items.forEach((li, n) => li.setAttribute("aria-selected", n === i));
    active = i;
  }
  function render(rows, q) {
    if (!rows.length) {
      list.innerHTML = `<li class="none">No matches for “${esc(q)}”. Try a genre or actor.</li>`;
      items = [];
      status.textContent = "No suggestions found";
    } else {
      list.innerHTML = rows.map((m, n) =>
        `<li role="option" id="opt-${n}" aria-selected="false"><a href="${m.url}"><span>${esc(m.title)} <small>${m.year}</small></span><small>★ ${m.rating.toFixed(1)}</small></a></li>`
      ).join("") + `<li class="more" role="option"><a href="/search?q=${encodeURIComponent(q)}">See all results for “${esc(q)}”</a></li>`;
      items = $$("li[role=option]", list);
      status.textContent = `${rows.length} suggestion${rows.length > 1 ? "s" : ""} available. Use up and down arrows to review.`;
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    active = -1;
  }
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) return close();
    timer = setTimeout(async () => {
      ctrl?.abort();
      ctrl = new AbortController();
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: ctrl.signal });
        render(await res.json(), q);
      } catch (e) { /* aborted or offline: keep the form usable */ }
    }, 220);
  });
  input.addEventListener("keydown", (e) => {
    if (list.hidden || !items.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); highlight((active + 1) % items.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); highlight((active - 1 + items.length) % items.length); }
    else if (e.key === "Enter" && active >= 0) { e.preventDefault(); $("a", items[active]).click(); }
    else if (e.key === "Escape") close();
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) close(); });

  /* Press "/" anywhere to search (shortcut for experts) ------------------- */
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey) { e.preventDefault(); input.focus(); input.select(); }
  });
})();
