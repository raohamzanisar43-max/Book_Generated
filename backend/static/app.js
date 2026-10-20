"use strict";

/* ----------------------------------------------------------------- helpers */
const $ = (sel, root = document) => root.querySelector(sel);

const state = { books: [], current: null, logs: [] };
const WORDS_PER_PAGE = 500; // keep in sync with settings.WORDS_PER_PAGE
let pollTimer = null;

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let detail = data.detail ?? `Request failed (${res.status})`;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg.replace(/^Value error, /, "")).join("; ");
    throw new Error(detail);
  }
  return data;
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function inline(text) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/** Minimal, safe Markdown renderer (input is HTML-escaped first). */
function markdown(src) {
  const lines = escapeHtml(src).split(/\r?\n/);
  const out = [];
  let para = [];
  let list = null;
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`); list = null; } };

  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { flushPara(); flushList(); continue; }
    if ((m = line.match(/^(#{1,6})\s+(.*)/))) {
      flushPara(); flushList();
      const level = Math.min(m[1].length + 1, 4);
      out.push(`<h${level}>${inline(m[2])}</h${level}>`);
    } else if ((m = line.match(/^\s*[-*•]\s+(.*)/)) || (m = line.match(/^\s*\d+[.)]\s+(.*)/))) {
      flushPara();
      const tag = /^\s*\d/.test(line) ? "ol" : "ul";
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push(m[1]);
    } else if ((m = line.match(/^&gt;\s?(.*)/))) {
      flushPara(); flushList();
      out.push(`<blockquote>${inline(m[1])}</blockquote>`);
    } else if (/^(---|\*\*\*|___)$/.test(line.trim())) {
      flushPara(); flushList();
    } else if ((m = line.replace(/\*/g, "").match(/^\s*Chapter\s+\d+\s*[:.\-–—]\s*.+$/i))) {
      flushPara(); flushList();
      out.push(`<h4>${inline(line.replace(/\*\*/g, ""))}</h4>`);
    } else {
      flushList();
      para.push(line.trim());
    }
  }
  flushPara(); flushList();
  return out.join("");
}

function plannedChapters(outline) {
  const found = new Map();
  for (const line of (outline || "").split(/\r?\n/)) {
    const m = line.replace(/\*/g, "").match(/^\s*#*\s*chapter\s+(\d+)\s*[:.\-–—]?\s*(.*)$/i);
    if (m && !found.has(+m[1])) found.set(+m[1], m[2].replace(/[#*]/g, "").trim());
  }
  return [...found.entries()].sort((a, b) => a[0] - b[0]);
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const LABELS = {
  pending: ["Pending", ""],
  generating: ["Generating", "info"],
  review_needed: ["Needs review", "warn"],
  approved: ["Approved", "ok"],
  failed: ["Failed", "bad"],
  in_progress: ["In progress", ""],
  ready: ["Ready to compile", "info"],
  compiled: ["Compiled", "ok"],
  yes: ["On hold", "warn"],
  no: ["Not reviewed", ""],
  no_notes_needed: ["Approved", "ok"],
};
function pill(status) {
  const [label, cls] = LABELS[status] || [status || "—", ""];
  return `<span class="pill ${cls}">${escapeHtml(label)}</span>`;
}

function toast(message, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 3500);
}

async function busy(text, fn) {
  $("#busy-text").textContent = text;
  $("#busy").hidden = false;
  try {
    return await fn();
  } catch (err) {
    toast(err.message, "error");
    throw err;
  } finally {
    $("#busy").hidden = true;
  }
}

/* ------------------------------------------------------------------- data */
async function loadBooks() {
  state.books = await api("/books/");
  renderBookList();
}

async function openBook(id, { pushHash = true } = {}) {
  const [book, logs] = await Promise.all([api(`/books/${id}`), api(`/books/${id}/logs`)]);
  state.current = book;
  state.logs = logs;
  if (pushHash) history.replaceState(null, "", `#${id}`);
  renderBookList();
  renderBook();
}

async function refresh() {
  await loadBooks();
  if (state.current) await openBook(state.current.id, { pushHash: false });
}

/* -------------------------------------------------------------- rendering */
function renderBookList() {
  const list = $("#book-list");
  if (!state.books.length) {
    list.innerHTML = `<li class="muted small" style="padding:.5rem">No books yet.</li>`;
    return;
  }
  list.innerHTML = state.books.map((b) => {
    const progress = b.chapters_planned ? `${b.chapters_written}/${b.chapters_planned} chapters` : `${b.chapters_written} chapters`;
    const active = state.current?.id === b.id ? "active" : "";
    return `<li><button class="${active}" data-book="${b.id}">
      <span class="t">${escapeHtml(b.title)}</span>
      <span class="s">${(LABELS[b.book_output_status] || [b.book_output_status])[0]} · ${progress}</span>
    </button></li>`;
  }).join("");
}

function renderBook() {
  const b = state.current;
  $("#empty-state").hidden = true;
  $("#book-view").hidden = false;
  $("#book-title").textContent = b.title;
  const pages = Math.round(b.total_words / WORDS_PER_PAGE);
  $("#book-meta").innerHTML = `<span class="stats">
    <span>Target: <b>${b.chapters_planned ?? b.target_chapters ?? "?"} chapters × ~${b.pages_per_chapter} pages</b></span>
    <span>Written: <b>${b.total_words.toLocaleString()} words (~${pages} pages)</b></span>
    <span>Updated ${fmtDate(b.updated_at)}</span></span>`;
  $("#book-notes").textContent = b.notes_on_outline_before || "—";
  $("#next-action").innerHTML = `<b>Next step:</b> ${escapeHtml(b.next_action)}`;
  renderStepper(b);
  renderOutline(b);
  renderChapters(b);
  renderFinal(b);
  renderActivity();
  schedulePoll();
}

/** While a chapter is being written in the background, refresh every few seconds. */
function schedulePoll() {
  clearTimeout(pollTimer);
  const b = state.current;
  const working = b?.chapters.filter((c) => c.status === "generating").map((c) => c.chapter_number) ?? [];
  if (!working.length) return;
  pollTimer = setTimeout(async () => {
    try {
      await refresh();
    } catch {
      return schedulePoll();
    }
    for (const n of working) {
      const c = state.current?.chapters.find((x) => x.chapter_number === n);
      if (c?.status === "review_needed") toast(`Chapter ${n} is ready for review (${c.word_count.toLocaleString()} words).`, "success");
      if (c?.status === "failed") toast(`Chapter ${n} failed to generate. See the activity log.`, "error");
    }
  }, 3000);
}

function stageState(b) {
  const chaptersDone = b.chapters.length > 0 && b.chapters.every((c) => c.status === "approved") &&
    (!b.chapters_planned || b.chapters.length >= b.chapters_planned);
  return [
    { name: "Outline", hint: LABELS[b.outline_status]?.[0] ?? b.outline_status, done: b.outline_status === "approved" },
    { name: "Chapters", hint: b.chapters_planned ? `${b.chapters.length} of ${b.chapters_planned}` : `${b.chapters.length} written`, done: chaptersDone || b.final_review_notes_status === "no_notes_needed" },
    { name: "Final review", hint: LABELS[b.final_review_notes_status]?.[0] ?? "", done: b.final_review_notes_status === "no_notes_needed" },
    { name: "Compile", hint: b.book_output_status === "compiled" ? "Done" : "Not yet", done: b.book_output_status === "compiled" },
  ];
}

function renderStepper(b) {
  const stages = stageState(b);
  const current = stages.findIndex((s) => !s.done);
  $("#stepper").innerHTML = stages.map((s, i) => `
    <li class="${s.done ? "done" : ""} ${i === current ? "current" : ""}">
      <span class="dot">${s.done ? "✓" : i + 1}</span>
      <span>${s.name}<small>${escapeHtml(s.hint)}</small></span>
    </li>`).join("");
}

function feedbackForm({ id, approveLabel, reviseLabel, placeholder, allowRevise = true, reviseHint = "" }) {
  return `
    <div class="feedback" data-feedback="${id}">
      ${allowRevise ? `<label>Editor notes <span class="muted">(required to request changes)</span>
        <textarea rows="3" placeholder="${escapeHtml(placeholder)}"></textarea></label>` : `<p class="muted small">${escapeHtml(reviseHint)}</p>`}
      <div class="btn-row">
        <button class="btn success" data-decision="no_notes_needed">${approveLabel}</button>
        ${allowRevise ? `<button class="btn" data-decision="yes">${reviseLabel}</button>` : ""}
      </div>
    </div>`;
}

function renderOutline(b) {
  $("#outline-status").outerHTML = pill(b.outline_status).replace("<span", '<span id="outline-status"');
  const body = $("#outline-body");
  const latest = b.outlines.at(-1);

  if (!latest) {
    body.innerHTML = `<p class="muted">No outline yet${b.outline_status === "generating" ? " — generation in progress." : ". The last attempt may have failed (check the activity log)."}</p>
      <div class="btn-row"><button class="btn primary" data-action="generate-outline">Generate outline</button></div>`;
    return;
  }

  let html = `<div class="prose outline-box">${markdown(latest.content)}</div>`;
  if (latest.notes_on_outline_after) {
    html += `<p class="small muted" style="margin-top:.75rem">Revised with notes: “${escapeHtml(latest.notes_on_outline_after)}”</p>`;
  }
  if (b.outline_status !== "approved") {
    html += feedbackForm({
      id: "outline",
      approveLabel: "Approve outline",
      reviseLabel: "Request changes",
      placeholder: "e.g. Merge chapters 3 and 4, add a chapter on case studies…",
      allowRevise: b.chapters.length === 0,
      reviseHint: "The outline can no longer be revised because chapters exist.",
    });
  }
  if (b.outlines.length > 1) {
    html += `<details class="versions"><summary>${b.outlines.length - 1} earlier version(s)</summary>${
      b.outlines.slice(0, -1).reverse().map((o, i) => `<div class="version"><p class="small muted">Version ${b.outlines.length - 1 - i} · ${fmtDate(o.created_at)}</p><div class="prose small">${markdown(o.content)}</div></div>`).join("")
    }</details>`;
  }
  body.innerHTML = html;
}

function renderChapters(b) {
  const body = $("#chapters-body");
  const planned = plannedChapters(b.outlines.at(-1)?.content);
  const total = b.chapters_planned || b.chapters.length;
  $("#chapter-progress").textContent = total ? `${b.chapters.length} of ${total} written` : "";

  if (b.outline_status !== "approved") {
    body.innerHTML = `<p class="muted">Approve the outline to start writing chapters.</p>`;
    return;
  }

  const written = new Map(b.chapters.map((c) => [c.chapter_number, c]));
  const rows = [];
  const maxNum = Math.max(b.chapters.length, planned.length ? planned.at(-1)[0] : 0);
  for (let n = 1; n <= maxNum; n++) {
    const c = written.get(n);
    if (c && c.status === "generating") {
      const p = c.progress || { stage: "Queued", done: 0, total: 0 };
      const pct = p.total ? Math.round((p.done / p.total) * 100) : 3;
      rows.push(`<li class="working">
        <span class="num">${n}</span>
        <span class="info"><b>${escapeHtml(c.title)}</b>
          <span class="small muted pulse">${escapeHtml(p.stage)}…</span>
          <span class="mini-progress"><span style="width:${pct}%"></span></span></span>
        ${pill(c.status)}
      </li>`);
    } else if (c && c.status === "failed") {
      rows.push(`<li class="failed">
        <span class="num">${n}</span>
        <span class="info"><b>${escapeHtml(c.title)}</b><span class="small muted">Generation failed. See the activity log, then retry.</span></span>
        <button class="btn small" data-action="generate-chapter">Retry</button>
      </li>`);
    } else if (c) {
      rows.push(`<li data-chapter="${n}">
        <span class="num">${n}</span>
        <span class="info"><b>${escapeHtml(c.title)}</b><span class="small muted">${c.word_count.toLocaleString()} words · ~${Math.round(c.estimated_pages)} pages</span></span>
        ${pill(c.status)}
      </li>`);
    } else {
      const title = planned.find(([num]) => num === n)?.[1] || `Chapter ${n}`;
      rows.push(`<li class="planned"><span class="num">${n}</span><span class="info"><b>${escapeHtml(title)}</b><span class="small muted">Planned</span></span></li>`);
    }
  }

  const last = b.chapters.at(-1);
  const canGenerate = (!last || last.status === "approved") && (!b.chapters_planned || b.chapters.length < b.chapters_planned);
  const pct = total ? Math.round((b.chapters.filter((c) => c.status === "approved").length / total) * 100) : 0;

  body.innerHTML = `
    ${total ? `<div class="progress" title="${pct}% approved"><span style="width:${pct}%"></span></div>` : ""}
    ${rows.length ? `<ul class="chapter-list">${rows.join("")}</ul>` : `<p class="muted">No chapters yet.</p>`}
    <div class="btn-row">
      ${canGenerate ? `<button class="btn primary" data-action="generate-chapter">Generate Chapter ${b.chapters.length + 1}</button>` : ""}
      ${last && last.status === "review_needed" ? `<button class="btn" data-chapter-open="${last.chapter_number}">Review Chapter ${last.chapter_number}</button>` : ""}
    </div>`;
}

function renderFinal(b) {
  $("#final-status").outerHTML = pill(b.book_output_status).replace("<span", '<span id="final-status"');
  const body = $("#final-body");
  const allApproved = b.chapters.length > 0 && b.chapters.every((c) => c.status === "approved");

  if (!allApproved) {
    body.innerHTML = `<p class="muted">Available once every chapter is approved.</p>`;
    return;
  }
  if (b.book_output_status === "compiled") {
    body.innerHTML = `<p>Your manuscript is compiled and ready.</p>
      <div class="btn-row">
        <a class="btn primary" href="/books/${b.id}/download">Download .docx</a>
        <button class="btn" data-action="compile">Recompile</button>
      </div>`;
    return;
  }
  if (b.final_review_notes_status === "no_notes_needed") {
    body.innerHTML = `<p>Final review approved. Compile the manuscript into a formatted Word document.</p>
      <div class="btn-row"><button class="btn primary" data-action="compile">Compile book</button></div>`;
    return;
  }
  const remaining = b.chapters_planned && b.chapters.length < b.chapters_planned
    ? `<p class="small muted">Note: ${b.chapters_planned - b.chapters.length} planned chapter(s) not written yet. You can still finish early.</p>` : "";
  body.innerHTML = `<p>Read through the manuscript, then sign off or put it on hold with notes.</p>${remaining}` +
    feedbackForm({ id: "final", approveLabel: "Approve final review", reviseLabel: "Put on hold", placeholder: "What still needs attention before publishing?" });
}

function renderActivity() {
  const items = [...state.logs].reverse();
  $("#activity").innerHTML = items.length
    ? items.map((l) => `<li class="${l.level}">${escapeHtml(l.message)}<time>${fmtDate(l.created_at)}</time></li>`).join("")
    : `<li class="muted">No activity yet.</li>`;
}

/* ---------------------------------------------------------------- chapters */
async function openChapter(num) {
  const b = state.current;
  const c = await api(`/books/${b.id}/chapters/${num}`);
  if (c.status === "generating" || c.status === "failed") return;
  const isLast = num === b.chapters.length;
  $("#chapter-kicker").innerHTML = `Chapter ${c.chapter_number} · ${c.word_count.toLocaleString()} words · ~${Math.round(c.estimated_pages)} pages · ${pill(c.status)}`;
  $("#chapter-title").textContent = c.title;
  $("#chapter-summary").textContent = c.summary || "—";
  $("#chapter-content").innerHTML = markdown(c.content);
  $("#chapter-actions").innerHTML = c.status === "approved"
    ? (c.chapter_notes ? `<p class="small muted">Last revised with notes: “${escapeHtml(c.chapter_notes)}”</p>` : "")
    : feedbackForm({
        id: `chapter:${num}`,
        approveLabel: "Approve chapter",
        reviseLabel: "Regenerate with notes",
        placeholder: "e.g. Add a concrete example, shorten the introduction…",
        allowRevise: isLast,
        reviseHint: "Only the latest chapter can be regenerated.",
      });
  $("#chapter-dialog").showModal();
  $("#chapter-dialog").scrollTop = 0;
}

/* ----------------------------------------------------------------- actions */
async function submitFeedback(target, decision, notes) {
  const b = state.current;
  if (decision === "yes" && !notes.trim()) {
    toast("Please write some notes first.", "error");
    return;
  }
  let path, text;
  if (target === "outline") {
    path = `/books/${b.id}/outline-feedback`;
    text = decision === "yes" ? "Revising the outline…" : "Approving outline…";
  } else if (target === "final") {
    path = `/books/${b.id}/final-review`;
    text = "Saving final review…";
  } else {
    const num = target.split(":")[1];
    path = `/books/${b.id}/chapters/${num}/feedback`;
    text = decision === "yes" ? `Rewriting Chapter ${num}…` : `Approving Chapter ${num}…`;
  }
  const res = await busy(text, () => api(path, { method: "POST", body: { status: decision, notes } }));
  toast(res.message, "success");
  if (target.startsWith("chapter:")) $("#chapter-dialog").close();
  await refresh();
}

const actions = {
  "new-book": () => { $("#new-book-form").reset(); updateLengthHint(); $("#new-book-dialog").showModal(); },
  "generate-outline": async () => {
    await busy("Generating the outline…", () => api(`/books/${state.current.id}/outline/generate`, { method: "POST" }));
    toast("Outline generated.", "success");
    await refresh();
  },
  "generate-chapter": async () => {
    const ch = await busy("Starting…", () => api(`/books/${state.current.id}/chapters/generate`, { method: "POST" }));
    toast(`Writing Chapter ${ch.chapter_number} (~${state.current.pages_per_chapter} pages). This takes a few minutes; you can keep working.`);
    await refresh();
  },
  compile: async () => {
    const res = await busy("Compiling the manuscript…", () => api(`/books/${state.current.id}/compile`, { method: "POST" }));
    toast(`Compiled ${res.file_name}`, "success");
    await refresh();
  },
};

document.addEventListener("click", async (e) => {
  const t = e.target;
  try {
    const bookBtn = t.closest("[data-book]");
    if (bookBtn) return await openBook(bookBtn.dataset.book);

    const action = t.closest("[data-action]");
    if (action) return await actions[action.dataset.action]();

    const decision = t.closest("[data-decision]");
    if (decision) {
      const box = decision.closest("[data-feedback]");
      const notes = box.querySelector("textarea")?.value ?? "";
      return await submitFeedback(box.dataset.feedback, decision.dataset.decision, notes);
    }

    const chapterRow = t.closest("[data-chapter]") || t.closest("[data-chapter-open]");
    if (chapterRow) return await openChapter(+(chapterRow.dataset.chapter || chapterRow.dataset.chapterOpen));

    if (t.closest("[data-close]")) t.closest("dialog").close();
  } catch (err) {
    console.error(err);
  }
});

$("#new-book-btn").addEventListener("click", actions["new-book"]);

function updateLengthHint() {
  const f = $("#new-book-form");
  const chapters = +f.chapters.value || 0;
  const pages = +f.pages.value || 0;
  const words = chapters * pages * WORDS_PER_PAGE;
  $("#length-hint").textContent =
    `≈ ${(chapters * pages).toLocaleString()} pages · ${words.toLocaleString()} words in total. ` +
    `Each chapter is written section by section and takes a few minutes.`;
}
$("#new-book-form").addEventListener("input", updateLengthHint);

$("#new-book-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  $("#new-book-dialog").close();
  try {
    const book = await busy("Creating book and generating the outline…", () =>
      api("/books/", { method: "POST", body: {
        title: form.get("title"),
        notes_on_outline_before: form.get("notes"),
        target_chapters: +form.get("chapters"),
        pages_per_chapter: +form.get("pages"),
      } }));
    toast("Outline ready for review.", "success");
    await loadBooks();
    await openBook(book.id);
  } catch {
    await loadBooks(); // the book may exist even if outline generation failed
  }
});

let deleteArmed = null;
$("#delete-book").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  if (deleteArmed !== state.current.id) {
    deleteArmed = state.current.id;
    btn.textContent = "Click again to delete";
    setTimeout(() => { deleteArmed = null; btn.textContent = "Delete"; }, 3000);
    return;
  }
  deleteArmed = null;
  btn.textContent = "Delete";
  await busy("Deleting…", () => api(`/books/${state.current.id}`, { method: "DELETE" }));
  toast("Book deleted.");
  state.current = null;
  history.replaceState(null, "", location.pathname);
  $("#book-view").hidden = true;
  $("#empty-state").hidden = false;
  await loadBooks();
});

async function checkHealth() {
  const el = $("#health");
  try {
    const h = await api("/health");
    const provider = h.llm_provider === "none" ? "no LLM configured" : `LLM: ${h.llm_provider}`;
    el.className = `pill ${h.status === "ok" ? (h.llm_provider === "none" ? "warn" : "ok") : "bad"}`;
    el.textContent = h.status === "ok" ? `● Online · ${provider}` : "● Database unavailable";
  } catch {
    el.className = "pill bad";
    el.textContent = "● API offline";
  }
}

(async function init() {
  checkHealth();
  try {
    await loadBooks();
    const id = location.hash.slice(1);
    if (id && state.books.some((b) => b.id === id)) await openBook(id, { pushHash: false });
  } catch (err) {
    toast(err.message, "error");
  }
})();
