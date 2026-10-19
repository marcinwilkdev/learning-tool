// Progress, step-through walkthroughs, flashcards, concept tooltips and search.
// Progress lives in localStorage only, so every access is guarded: the site must
// still work in private windows or when storage is blocked.
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  const KB = window.KB || { topics: [], concepts: {} };
  const PREFIX = window.KB_PREFIX || "";

  // Interface strings come from data.js in the knowledge base's language (see i18n.py).
  // Templates use {name} for a value and {word:count} for a word that agrees with a count.
  const LANG = KB.lang || "en";
  const plurals = new Intl.PluralRules(LANG);
  function fmt(dict, key, vals) {
    const tpl = (dict && dict[key]) || (KB.en && KB.en[key]) || key;
    return tpl.replace(/\{(\w+)(?::(\w+))?\}/g, (_, name, count) => {
      if (!count) return vals[name];
      const forms = dict[name] || KB.en[name];
      return forms[plurals.select(vals[count])] || forms.other;
    });
  }
  const t = (key, vals = {}) => fmt(KB.strings, key, vals);
  // The results export stays in English: the assess and track-knowledge skills read it.
  const en = (key, vals = {}) => fmt(KB.en, key, vals);
  const NS = "learnkb:";

  const store = {
    get(key) { try { return localStorage.getItem(NS + key); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem(NS + key, value); } catch (e) {} },
    del(key) { try { localStorage.removeItem(NS + key); } catch (e) {} },
  };
  const isDone = (slug) => store.get("done:" + slug) === "1";

  // ---------- progress ----------
  function refreshProgress() {
    const done = KB.topics.filter((t) => isDone(t.slug)).length;
    const pct = KB.topics.length ? Math.round((done / KB.topics.length) * 100) : 0;
    document.querySelectorAll("[data-progress-bar]").forEach((el) => (el.style.width = pct + "%"));
    document.querySelectorAll("[data-progress-text]").forEach(
      (el) => (el.textContent = t("progress", { done, total: KB.topics.length })));
    document.querySelectorAll("[data-topic]").forEach((el) =>
      el.classList.toggle("is-done", isDone(el.dataset.topic)));
    const cont = document.querySelector("[data-continue]");
    if (cont && done > 0) {
      const next = KB.topics.find((t) => !isDone(t.slug));
      if (next) { cont.href = `topics/${next.slug}.html`; cont.textContent = t("continue", { title: next.title }); }
      else { cont.textContent = t("all_complete"); }
    }
  }

  document.querySelectorAll("[data-complete]").forEach((btn) => {
    const slug = btn.dataset.complete;
    const paint = () => {
      const d = isDone(slug);
      btn.classList.toggle("done", d);
      btn.textContent = d ? t("completed_undo") : t("mark_complete");
    };
    btn.addEventListener("click", () => {
      isDone(slug) ? store.del("done:" + slug) : store.set("done:" + slug, "1");
      paint(); refreshProgress();
    });
    paint();
  });

  document.querySelectorAll("[data-objective]").forEach((box) => {
    const key = "obj:" + box.dataset.objective;
    box.checked = store.get(key) === "1";
    box.addEventListener("change", () => (box.checked ? store.set(key, "1") : store.del(key)));
  });

  // ---------- step-through ----------
  document.querySelectorAll("[data-steps]").forEach((root) => {
    const steps = [...root.querySelectorAll(".step")];
    const prev = root.querySelector("[data-prev]");
    const next = root.querySelector("[data-next]");
    const dots = root.querySelector(".step-dots");
    let i = 0;
    steps.forEach((_, n) => {
      const b = document.createElement("button");
      b.setAttribute("aria-label", t("go_to_step", { n: n + 1 }));
      b.addEventListener("click", () => show(n));
      dots.appendChild(b);
    });
    function show(n) {
      i = Math.max(0, Math.min(steps.length - 1, n));
      steps.forEach((s, k) => s.classList.toggle("active", k === i));
      [...dots.children].forEach((d, k) => d.classList.toggle("on", k <= i));
      prev.disabled = i === 0;
      next.textContent = i === steps.length - 1 ? t("done") : t("next");
    }
    prev.addEventListener("click", () => show(i - 1));
    next.addEventListener("click", () => {
      if (i === steps.length - 1) { root.classList.add("show-all"); toggle.textContent = t("one_at_a_time"); }
      else show(i + 1);
    });
    const toggle = root.querySelector("[data-show-all]");
    toggle.addEventListener("click", () => {
      const all = root.classList.toggle("show-all");
      toggle.textContent = all ? t("one_at_a_time") : t("show_all");
    });
    root.addEventListener("keydown", (e) => {
      if (e.target.closest("input, textarea")) return;
      if (e.key === "ArrowRight") show(i + 1);
      if (e.key === "ArrowLeft") show(i - 1);
    });
    show(0);
  });

  // ---------- flashcards ----------
  document.querySelectorAll(".card").forEach((card) =>
    card.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      card.setAttribute("aria-pressed", card.getAttribute("aria-pressed") === "true" ? "false" : "true");
    }));

  // ---------- concept tooltips ----------
  const tip = document.querySelector(".tooltip");
  const hover = window.matchMedia("(hover: hover)").matches;
  function showTip(link) {
    const c = KB.concepts[link.dataset.slug];
    if (!c || !tip) return;
    tip.innerHTML = "";
    const t = document.createElement("strong"); t.textContent = c.title;
    const d = document.createElement("span"); d.textContent = c.definition;
    tip.append(t, d);
    tip.hidden = false;
    const r = link.getBoundingClientRect();
    const w = Math.min(320, window.innerWidth - 32);
    const left = Math.min(Math.max(16, r.left + window.scrollX), window.scrollX + window.innerWidth - w - 16);
    tip.style.left = left + "px";
    tip.style.top = r.bottom + window.scrollY + 8 + "px";
  }
  const hideTip = () => tip && (tip.hidden = true);
  if (hover) {
    document.querySelectorAll("a.wl-concept").forEach((a) => {
      a.addEventListener("mouseenter", () => showTip(a));
      a.addEventListener("mouseleave", hideTip);
      a.addEventListener("focus", () => showTip(a));
      a.addEventListener("blur", hideTip);
    });
  }

  // ---------- admin panel link ----------
  // Only `learnkb-serve` has the panel, so the link stays hidden until it answers.
  const adminLink = document.querySelector("[data-admin-link]");
  if (adminLink && location.protocol !== "file:") {
    fetch(PREFIX + "admin/", { method: "HEAD" }).then((r) => { if (r.ok) adminLink.hidden = false; }, () => {});
  }

  // ---------- mobile menu ----------
  const menu = document.querySelector("[data-menu]");
  menu && menu.addEventListener("click", () => document.body.classList.toggle("menu-open"));
  document.addEventListener("keydown", (e) => e.key === "Escape" && document.body.classList.remove("menu-open"));

  // ---------- search (home) ----------
  const search = document.querySelector("[data-search]");
  if (search) {
    const results = document.querySelector(".search-results");
    const items = [
      ...KB.topics.map((tp) => ({ title: tp.title, sub: t("search_topic") + tp.summary, href: `topics/${tp.slug}.html`, hay: (tp.title + " " + tp.summary).toLowerCase() })),
      ...Object.entries(KB.concepts).map(([slug, c]) => ({ title: c.title, sub: t("search_concept") + c.definition, href: `concepts/${slug}.html`, hay: (c.title + " " + c.aliases.join(" ") + " " + c.definition).toLowerCase() })),
    ];
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      results.innerHTML = "";
      if (!q) { results.hidden = true; return; }
      const hits = items.filter((it) => q.split(/\s+/).every((w) => it.hay.includes(w))).slice(0, 12);
      hits.forEach((h) => {
        const li = document.createElement("li");
        const a = document.createElement("a"); a.href = PREFIX + h.href; a.textContent = h.title;
        const s = document.createElement("small"); s.textContent = h.sub;
        a.appendChild(s); li.appendChild(a); results.appendChild(li);
      });
      if (!hits.length) { const li = document.createElement("li"); li.className = "muted"; li.style.padding = "8px 10px"; li.textContent = t("no_matches"); results.appendChild(li); }
      results.hidden = false;
    });
    document.addEventListener("click", (e) => !e.target.closest(".search") && (results.hidden = true));
  }

  // ---------- glossary filter ----------
  const filter = document.querySelector("[data-filter-input]");
  if (filter) {
    filter.addEventListener("input", () => {
      const q = filter.value.trim().toLowerCase();
      document.querySelectorAll("[data-filter]").forEach((li) => (li.hidden = q && !li.dataset.filter.includes(q)));
    });
  }

  // ---------- quiz score chips ----------
  const quizResult = (slug) => { try { return JSON.parse(store.get("quiz:" + slug)); } catch (e) { return null; } };
  function refreshScores() {
    document.querySelectorAll("[data-quiz-score]").forEach((el) => {
      const r = quizResult(el.dataset.quizScore);
      el.hidden = !r;
      if (r) {
        el.textContent = t("last_quiz", { pct: r.pct });
        el.className = "chip chip-score " + (r.pct >= 80 ? "chip-beginner" : r.pct >= 50 ? "chip-intermediate" : "chip-advanced");
      }
    });
  }

  // ---------- quiz ----------
  // Choice questions are graded all-or-nothing; open questions score the share of
  // rubric points the learner ticks. An open answer with nothing ticked (and not
  // "None of these") isn't graded yet, so it's left out of the score instead of
  // counting as zero. Objectives averaging >= 80% count as mastered and are ticked
  // on the topic page.
  document.querySelectorAll("[data-quiz]").forEach((form) => {
    const slug = form.dataset.quiz;
    const qs = [...form.querySelectorAll(".question")];
    const results = document.querySelector("[data-results]");
    const unanswered = form.querySelector("[data-unanswered]");
    const copyBtn = results.querySelector("[data-copy]");
    const savedNote = results.querySelector("[data-saved]");
    const copyHelp = results.querySelector("[data-copy-help]");
    let attempt = null;
    const fallback = results.querySelector(".copy-fallback");

    function shuffle() {
      form.querySelectorAll(".opts").forEach((ul) => {
        const items = [...ul.children];
        for (let i = items.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [items[i], items[j]] = [items[j], items[i]];
        }
        items.forEach((li) => ul.appendChild(li));
      });
    }
    const isOpen = (q) => q.dataset.type === "open";
    const answered = (q) => isOpen(q) ? q.querySelector("textarea").value.trim() !== "" : !!q.querySelector(".opts input:checked");
    function countUnanswered() {
      const n = qs.filter((q) => !answered(q)).length;
      unanswered.textContent = n ? t("unanswered", { n }) : t("all_answered");
    }
    // A number from 0 to 1, or null for an open answer the learner hasn't graded yet.
    function score(q) {
      if (isOpen(q)) {
        const pts = [...q.querySelectorAll("[data-point]")];
        const ticked = pts.filter((p) => p.checked).length;
        if (ticked) return ticked / pts.length;
        return q.querySelector("[data-none]").checked || !answered(q) ? 0 : null;
      }
      return [...q.querySelectorAll(".opt")].every((o) => o.querySelector("input").checked === (o.dataset.correct === "1")) ? 1 : 0;
    }
    const status = (s) => s >= 0.8 ? ["solid", "good"] : s >= 0.5 ? ["shaky", "partial"] : ["review", "bad"];
    // Show `key` in the page's language and keep the English text for the export.
    const label = (el, key, vals) => { el.textContent = t(key, vals); el.dataset.en = en(key, vals); };

    const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
    function grade() {
      const scores = qs.map(score);
      const graded = scores.filter((s) => s !== null);
      const pending = scores.length - graded.length;
      qs.forEach((q, i) => {
        const v = q.querySelector(".q-verdict");
        const s = scores[i];
        if (s === null) {
          label(v, "not_graded_hint");
          v.className = "q-verdict pending";
        } else if (isOpen(q)) {
          const pts = q.querySelectorAll("[data-point]");
          label(v, "points_of", { got: Math.round(s * pts.length), n: pts.length });
        } else {
          label(v, s === 1 ? "correct" : "not_quite");
        }
        if (s !== null) v.className = "q-verdict " + status(s)[1];
      });
      const pct = graded.length ? Math.round(mean(graded) * 100) : 0;
      results.querySelector("[data-score]").textContent = graded.length ? pct + "%" : "–";
      results.querySelector("[data-score-label]").textContent = pending
        ? t("so_far", { n: pending })
        : t(pct >= 80 ? "verdict_good" : pct >= 50 ? "verdict_ok" : "verdict_bad");
      const mastered = [];
      results.querySelectorAll("[data-obj]").forEach((row) => {
        const n = row.dataset.obj;
        const tested = scores.filter((_, i) => qs[i].dataset.objective === n);
        const mine = tested.filter((s) => s !== null);
        const st = row.querySelector(".or-status");
        if (!mine.length) {
          label(st, tested.length ? "not_graded" : "not_tested"); st.className = "or-status";
          row.querySelector(".bar span").style.width = "0";
          return;
        }
        const avg = mean(mine);
        const [key, cls] = status(avg);
        label(st, key); st.className = "or-status " + cls;
        row.querySelector(".bar span").style.width = Math.round(avg * 100) + "%";
        row.querySelector(".bar span").className = cls;
        if (avg >= 0.8) mastered.push(Number(n));
      });
      // Only a fully graded attempt becomes the topic's saved score.
      if (pending) return;
      store.set("quiz:" + slug, JSON.stringify({ pct, date: new Date().toISOString().slice(0, 10), mastered }));
      mastered.forEach((n) => store.set(`obj:${slug}:${n - 1}`, "1"));
      refreshScores();
    }

    function exportText() {
      const clean = (el) => (el ? el.dataset.en || el.textContent : "").replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
      const lines = [`Assessment results: ${form.dataset.title} (topic: ${slug}, ${new Date().toISOString().slice(0, 10)})`,
        `Score: ${results.querySelector("[data-score]").textContent}` +
          (qs.some((q) => score(q) === null) ? " (some written answers not self-graded; grade them yourself)" : ""),
        "", "Objectives:"];
      results.querySelectorAll("[data-obj]").forEach((row) =>
        lines.push(`  ${row.dataset.obj}. ${clean(row.querySelector(".or-text"))}: ${clean(row.querySelector(".or-status"))}`));
      qs.forEach((q, i) => {
        lines.push("", `Q${i + 1} [objective ${q.dataset.objective}, ${q.dataset.type}] ${clean(q.querySelector(".q-verdict"))}`,
          `  Question: ${clean(q.querySelector(".q-text"))}`);
        if (isOpen(q)) {
          lines.push(`  My answer: ${q.querySelector("textarea").value.trim() || "(blank)"}`);
          q.querySelectorAll("[data-point], [data-none]").forEach((p) =>
            lines.push(`  [${p.checked ? "x" : " "}] ${clean(p.nextElementSibling)}`));
        } else {
          const opts = [...q.querySelectorAll(".opt")];
          const picked = opts.filter((o) => o.querySelector("input").checked).map((o) => clean(o.querySelector(".opt-text")));
          lines.push(`  I chose: ${picked.join(" | ") || "(nothing)"}`);
          if (score(q) < 1) lines.push(`  Correct: ${opts.filter((o) => o.dataset.correct === "1").map((o) => clean(o.querySelector(".opt-text"))).join(" | ")}`);
        }
      });
      return lines.join("\n");
    }

    // Served by `learnkb-serve`, the results are saved to learner/inbox/ for /assess. Each
    // attempt has one file, re-saved whenever the self-grading ticks change. Anywhere else
    // (file://, a plain static server) the post fails quietly and the copy button remains.
    let saveTimer = null;
    function save() {
      if (!attempt || location.protocol === "file:") return;
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        fetch(PREFIX + "api/results", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic: slug, attempt, text: exportText() }),
        }).then((r) => { if (r.ok) { savedNote.hidden = false; copyHelp.hidden = true; } }, () => {});
      }, 300);
    }

    form.addEventListener("input", countUnanswered);
    form.addEventListener("change", (e) => {
      if (!e.target.matches("[data-point], [data-none]")) return;
      // "None of these" and the points exclude each other.
      const q = e.target.closest(".question");
      if (e.target.checked && e.target.matches("[data-none]")) q.querySelectorAll("[data-point]").forEach((p) => (p.checked = false));
      if (e.target.checked && e.target.matches("[data-point]")) q.querySelector("[data-none]").checked = false;
      grade(); save();
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (form.classList.contains("submitted")) return;
      form.classList.add("submitted");
      form.querySelectorAll(".opts input, textarea").forEach((el) => (el.disabled = true));
      form.querySelectorAll(".opt").forEach((o) => {
        const chosen = o.querySelector("input").checked;
        o.classList.toggle("is-correct", o.dataset.correct === "1");
        o.classList.toggle("is-wrong", chosen && o.dataset.correct !== "1");
        o.classList.toggle("is-chosen", chosen);
      });
      grade();
      attempt = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
      save();
      results.hidden = false;
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    results.querySelector("[data-retake]").addEventListener("click", () => {
      form.reset();
      form.classList.remove("submitted");
      form.querySelectorAll(".opts input, textarea").forEach((el) => (el.disabled = false));
      form.querySelectorAll(".opt").forEach((o) => o.classList.remove("is-correct", "is-wrong", "is-chosen"));
      form.querySelectorAll(".q-verdict").forEach((v) => { v.textContent = ""; delete v.dataset.en; v.className = "q-verdict"; });
      results.hidden = true; fallback.hidden = true;
      attempt = null; savedNote.hidden = true; copyHelp.hidden = false;
      copyBtn.textContent = t("copy_results");
      shuffle(); countUnanswered();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    copyBtn.addEventListener("click", () => {
      const text = exportText();
      const manual = () => {
        fallback.value = text; fallback.hidden = false; fallback.select();
        copyBtn.textContent = t("copy_below");
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
          copyBtn.textContent = t("copied");
          fallback.value = text;
        }, manual);
      } else manual();
    });

    shuffle(); countUnanswered();
  });

  refreshScores();
  refreshProgress();
})();
