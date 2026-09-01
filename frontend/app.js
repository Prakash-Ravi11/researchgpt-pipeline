const state = {
  papers: [],
  clusters: {},
  activeCluster: "all",
  selected: new Set(),
};

const el = (sel) => document.querySelector(sel);

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function scoreLabel(score) {
  if (score === null || score === undefined) return "—";
  return score.toFixed(2);
}

function renderTabs() {
  const tabs = el("#cluster-tabs");
  const entries = Object.entries(state.clusters).sort((a, b) => a[0] - b[0]);

  const allTab = document.createElement("button");
  allTab.className = "tab" + (state.activeCluster === "all" ? " active" : "");
  allTab.textContent = `All records (${state.papers.length})`;
  allTab.onclick = () => { state.activeCluster = "all"; render(); };

  tabs.innerHTML = "";
  tabs.appendChild(allTab);

  for (const [cid, info] of entries) {
    const tab = document.createElement("button");
    tab.className = "tab" + (state.activeCluster === cid ? " active" : "");
    tab.textContent = `${info.label} (${info.paper_count})`;
    tab.title = info.description || "";
    tab.onclick = () => { state.activeCluster = cid; render(); };
    tabs.appendChild(tab);
  }
}

function renderCatalog() {
  const catalog = el("#catalog");
  const visible = state.activeCluster === "all"
    ? state.papers
    : state.papers.filter((p) => String(p.cluster_id) === state.activeCluster);

  if (visible.length === 0) {
    catalog.innerHTML = `<div class="empty-state">No records in this category.</div>`;
    return;
  }

  catalog.innerHTML = "";
  for (const p of visible) {
    const card = document.createElement("article");
    card.className = "card";

    const authorLine = p.authors.length
      ? `${p.authors.slice(0, 2).join(", ")}${p.authors.length > 2 ? " et al." : ""}`
      : "Authors unavailable";

    card.innerHTML = `
      <div class="card__top">
        <span class="card__id">REC · ${p.paper_id.slice(0, 8).toUpperCase()}</span>
        <span class="stamp-score" title="Relevance to query">${scoreLabel(p.relevance_score)}</span>
      </div>
      <h3 class="card__title">${p.title}</h3>
      <div class="card__meta">${authorLine} &middot; ${p.venue || "—"} &middot; ${p.year || "n.d."}</div>
      <p class="card__excerpt">${p.summary || "No summary extracted yet."}</p>
      <div class="card__footer">
        <span class="card__category">${p.category}</span>
        <label class="card__select" onclick="event.stopPropagation()">
          <input type="checkbox" data-id="${p.paper_id}" ${state.selected.has(p.paper_id) ? "checked" : ""}>
          Compare
        </label>
      </div>
      ${!p.has_full_text ? '<div class="no-full-text-flag">abstract-only source</div>' : ""}
    `;

    card.querySelector("input").addEventListener("change", (e) => {
      toggleSelect(p.paper_id, e.target.checked);
    });
    card.addEventListener("click", () => openRecord(p.paper_id));

    catalog.appendChild(card);
  }
}

function toggleSelect(paperId, checked) {
  if (checked) {
    if (state.selected.size >= 2) {
      // Keep selection at max 2 — drop the oldest.
      const first = state.selected.values().next().value;
      state.selected.delete(first);
    }
    state.selected.add(paperId);
  } else {
    state.selected.delete(paperId);
  }
  updateCompareButton();
  renderCatalog();
}

function updateCompareButton() {
  const btn = el("#compare-toggle");
  el("#compare-count").textContent = state.selected.size;
  btn.disabled = state.selected.size !== 2;
}

async function openRecord(paperId) {
  const p = await fetchJSON(`/api/papers/${paperId}`);
  const content = el("#record-content");

  const authorLine = p.authors.length ? p.authors.join(", ") : "Authors unavailable";
  const link = p.external_link
    ? `<a href="${p.external_link}" target="_blank" rel="noopener">${p.external_link}</a>`
    : "No link on file";
  const pdfOrSourceLink = p.has_full_text
    ? `<a href="/api/papers/${paperId}/pdf" target="_blank" rel="noopener" class="btn btn--ghost">View PDF</a>`
    : (p.external_link
        ? `<a href="${p.external_link}" target="_blank" rel="noopener" class="btn btn--ghost">View source (no local PDF)</a>`
        : `<span class="ledger-row__value">No PDF or source link available.</span>`);

  content.innerHTML = `
    <div class="record-kicker">CATALOG RECORD · ${p.category}</div>
    <h2 class="record-title">${p.title}</h2>
    <div class="record-byline">${authorLine} &middot; ${p.venue || "—"}, ${p.year || "n.d."} &middot; ${link}</div>

    <div class="ledger-row">
      <div class="ledger-row__label">Source</div>
      <div class="ledger-row__value">${pdfOrSourceLink}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Figures</div>
      <div class="ledger-row__value" id="figures-slot">Loading&hellip;</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Problem</div>
      <div class="ledger-row__value">${p.problem_addressed || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Method</div>
      <div class="ledger-row__value">${p.method || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Datasets</div>
      <div class="ledger-row__value">${p.datasets && p.datasets.length ? renderTags(p.datasets) : (p.no_dataset_stated ? '<span class="ledger-row__value">No dataset stated in text (theory/survey paper).</span>' : '<span class="ledger-row__value">None listed.</span>')}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Metrics</div>
      <div class="ledger-row__value">${renderTags(p.metrics)}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Results</div>
      <div class="ledger-row__value">${p.results || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Inferences</div>
      <div class="ledger-row__value">${p.inferences || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Novelty claim</div>
      <div class="ledger-row__value">${p.novelty_claim || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Limitations</div>
      <div class="ledger-row__value">${p.limitations || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Findings</div>
      <div class="ledger-row__value">${p.key_findings || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Summary</div>
      <div class="ledger-row__value">${p.summary || "Not extracted."}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Citations</div>
      <div class="ledger-row__value">${p.citation_count ?? "Unknown"}</div>
    </div>

    ${p.extraction_failed ? '<div class="extraction-warning">Extraction incomplete for this record — fields above may be empty or unreliable.</div>' : ""}

    <div class="ledger-row">
      <div class="ledger-row__label">Compare</div>
      <div class="ledger-row__value">
        <label class="btn btn--ghost" style="cursor:pointer; display:inline-block;">
          Upload a PDF to compare against this
          <input type="file" id="upload-compare-input" accept="application/pdf" style="display:none">
        </label>
        <div id="upload-status" style="font-family:var(--font-mono); font-size:11px; color:var(--ink-soft); margin-top:8px;"></div>
      </div>
    </div>
  `;

  document.getElementById("upload-compare-input").addEventListener("change", (e) => {
    handleUploadCompare(e.target.files[0], paperId);
  });

  el("#record-overlay").classList.remove("hidden");
  loadFigures(paperId);
}

async function loadFigures(paperId) {
  const slot = document.getElementById("figures-slot");
  try {
    const { figures } = await fetchJSON(`/api/papers/${paperId}/figures`);
    if (!figures || figures.length === 0) {
      slot.innerHTML = "No figures extracted (abstract-only source, or none found in the PDF).";
      return;
    }
    slot.innerHTML = `
      <div class="figure-grid">
        ${figures.map((url) => `
          <a href="${url}" target="_blank" rel="noopener" class="figure-thumb">
            <img src="${url}" alt="Figure from paper" loading="lazy">
          </a>
        `).join("")}
      </div>
    `;
  } catch (err) {
    slot.textContent = "Could not load figures.";
    console.error(err);
  }
}

async function handleUploadCompare(file, existingId) {
  if (!file) return;
  const status = document.getElementById("upload-status");
  status.textContent = "Extracting your paper — can take up to a couple minutes on a local model...";

  const form = new FormData();
  form.append("existing_id", existingId);
  form.append("file", file);

  try {
    const res = await fetch("/api/compare-upload", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    const { a, b } = await res.json();
    closeOverlays();
    renderCompareGrid(a, b);
    el("#compare-overlay").classList.remove("hidden");
  } catch (err) {
    status.textContent = `Failed: ${err.message}`;
  }
}

function renderTags(list) {
  if (!list || list.length === 0) return '<span class="ledger-row__value">None listed.</span>';
  return `<div class="tag-list">${list.map((t) => `<span class="tag">${t}</span>`).join("")}</div>`;
}

async function openCompare() {
  const [a, b] = Array.from(state.selected);
  const { a: recordA, b: recordB } = await fetchJSON(`/api/compare?a=${a}&b=${b}`);
  renderCompareGrid(recordA, recordB);
  el("#compare-overlay").classList.remove("hidden");
}

function renderCompareGrid(recordA, recordB) {
  const content = el("#compare-content");

  const rows = [
    ["Venue / Year", (r) => `${r.venue || "—"}${r.year ? ", " + r.year : ""}`],
    ["Relevance score", (r) => r.relevance_score !== null && r.relevance_score !== undefined ? r.relevance_score.toFixed(3) : "n/a"],
    ["Citations", (r) => r.citation_count ?? "Unknown"],
    ["Source link", (r) => r.external_link ? `<a href="${r.external_link}" target="_blank" rel="noopener">link</a>` : "None on file"],
    ["Problem", (r) => r.problem_addressed || "Not extracted."],
    ["Method", (r) => r.method || "Not extracted."],
    ["Datasets", (r) => renderTags(r.datasets)],
    ["Metrics", (r) => renderTags(r.metrics)],
    ["Findings", (r) => r.key_findings || "Not extracted."],
  ];

  content.innerHTML = `
    <div class="record-kicker">SIDE-BY-SIDE COMPARISON</div>
    <div class="compare-grid">
      <div></div>
      <div class="compare-grid__header">${recordA.title}</div>
      <div class="compare-grid__header">${recordB.title}</div>
      ${rows.map(([label, getValue]) => `
        <div class="compare-grid__label">${label}</div>
        <div class="compare-grid__cell">${getValue(recordA)}</div>
        <div class="compare-grid__cell">${getValue(recordB)}</div>
      `).join("")}
    </div>
  `;
}

function render() {
  renderTabs();
  renderCatalog();
}

function closeOverlays() {
  el("#record-overlay").classList.add("hidden");
  el("#compare-overlay").classList.add("hidden");
  el("#novelty-overlay").classList.add("hidden");
  el("#table-overlay").classList.add("hidden");
  el("#analysis-overlay").classList.add("hidden");
}

async function refreshCorpus() {
  const [papers, clusters] = await Promise.all([
    fetchJSON("/api/papers"),
    fetchJSON("/api/clusters"),
  ]);
  state.papers = papers;
  state.clusters = clusters;
  state.activeCluster = "all";
  state.selected.clear();
  updateCompareButton();
  el("#corpus-subtitle").textContent = `${papers.length} records · ${Object.keys(clusters).length} categories`;
  render();
}

async function init() {
  try {
    await refreshCorpus();
  } catch (err) {
    el("#corpus-subtitle").textContent = "Could not load corpus — is the API running?";
    console.error(err);
  }
}

/* ---------- New Search / Upload Corpus control deck ---------- */

const STAGE_ORDER = ["queued", "collecting", "registering", "processing", "extracting_figures", "embedding", "extracting", "synthesizing", "gap_analysis", "done"];

function stageProgressPercent(stage) {
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx === -1) return 5;
  return Math.max(8, Math.round((idx / (STAGE_ORDER.length - 1)) * 100));
}

function setFormsDisabled(disabled) {
  el("#search-submit").disabled = disabled;
  el("#upload-submit").disabled = disabled;
}

function showJobPanel() {
  el("#job-status-panel").classList.remove("hidden");
}

function updateJobPanel(job) {
  const stageEl = el("#job-stage-text");
  const barEl = el("#job-bar-fill");
  const detailEl = el("#job-detail-text");

  stageEl.classList.remove("is-error", "is-done");
  barEl.classList.remove("is-error", "is-done");

  if (job.status === "error") {
    stageEl.textContent = "Failed";
    stageEl.classList.add("is-error");
    barEl.classList.add("is-error");
    barEl.style.width = "100%";
    detailEl.textContent = job.error || "Unknown error — check the uvicorn terminal for the full traceback.";
    return;
  }

  if (job.status === "done") {
    stageEl.textContent = "Done";
    stageEl.classList.add("is-done");
    barEl.classList.add("is-done");
    barEl.style.width = "100%";
    detailEl.textContent = "Catalog updated below.";
    return;
  }

  stageEl.textContent = job.stage || "Running";
  barEl.style.width = `${stageProgressPercent(job.stage)}%`;
  detailEl.textContent = job.progress || "Working...";
}

async function pollJob(jobId) {
  showJobPanel();
  setFormsDisabled(true);
  let transientFailures = 0;

  const poll = async () => {
    let job;
    try {
      job = await fetchJSON(`/api/jobs/${jobId}`);
      transientFailures = 0;
    } catch (err) {
      transientFailures += 1;
      if (err.message.includes("-> 404")) {
        el("#job-detail-text").textContent =
          "This job is no longer available. Please start the search again.";
        setFormsDisabled(false);
        return;
      }
      if (transientFailures < 4) {
        el("#job-detail-text").textContent =
          `Waiting for the server to respond (retry ${transientFailures}/3)...`;
        setTimeout(poll, 4000);
        return;
      }
      el("#job-detail-text").textContent = `Server connection failed: ${err.message}`;
      setFormsDisabled(false);
      return;
    }

    updateJobPanel(job);

    if (job.status === "running") {
      setTimeout(poll, 4000);
      return;
    }

    setFormsDisabled(false);
    if (job.status === "done") {
      try {
        await refreshCorpus();
      } catch (err) {
        el("#job-detail-text").textContent = `Job finished but reloading the catalog failed: ${err.message}`;
      }
    }
  };

  poll();
}

el("#deck-tab-search").addEventListener("click", () => {
  el("#deck-tab-search").classList.add("active");
  el("#deck-tab-upload").classList.remove("active");
  el("#deck-tab-novelty").classList.remove("active");
  el("#search-form").classList.remove("hidden");
  el("#upload-form").classList.add("hidden");
  el("#novelty-form").classList.add("hidden");
});

el("#deck-tab-upload").addEventListener("click", () => {
  el("#deck-tab-upload").classList.add("active");
  el("#deck-tab-search").classList.remove("active");
  el("#deck-tab-novelty").classList.remove("active");
  el("#upload-form").classList.remove("hidden");
  el("#search-form").classList.add("hidden");
  el("#novelty-form").classList.add("hidden");
});

el("#deck-tab-novelty").addEventListener("click", () => {
  el("#deck-tab-novelty").classList.add("active");
  el("#deck-tab-search").classList.remove("active");
  el("#deck-tab-upload").classList.remove("active");
  el("#novelty-form").classList.remove("hidden");
  el("#search-form").classList.add("hidden");
  el("#upload-form").classList.add("hidden");
});

el("#search-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const yearStart = el("#search-year-start").value;
  const yearEnd = el("#search-year-end").value;
  const clusters = el("#search-clusters").value;

  const payload = {
    query: el("#search-query").value.trim(),
    target_corpus_size: parseInt(el("#search-target").value, 10) || 50,
    candidate_pool_size: parseInt(el("#search-pool").value, 10) || 100,
    year_start: yearStart ? parseInt(yearStart, 10) : null,
    year_end: yearEnd ? parseInt(yearEnd, 10) : null,
    num_clusters: clusters ? parseInt(clusters, 10) : null,
  };

  if (!payload.query) return;

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ? JSON.stringify(err.detail) : `Request failed (${res.status})`);
    }
    const { job_id } = await res.json();
    pollJob(job_id);
  } catch (err) {
    showJobPanel();
    updateJobPanel({ status: "error", error: err.message });
  }
});

el("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const files = el("#upload-files").files;
  if (!files || files.length === 0) return;

  const form = new FormData();
  for (const f of files) form.append("files", f);

  try {
    const res = await fetch("/api/upload-corpus", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    const { job_id, file_count, skipped } = await res.json();
    showJobPanel();
    if (skipped && skipped.length) {
      el("#job-detail-text").textContent =
        `${file_count} PDF(s) accepted. Skipped (not PDFs): ${skipped.join(", ")}`;
    }
    pollJob(job_id);
  } catch (err) {
    showJobPanel();
    updateJobPanel({ status: "error", error: err.message });
  }
});

el("#novelty-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const file = el("#novelty-file").files[0];
  if (!file) return;

  const submitBtn = el("#novelty-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Checking against corpus (can take a couple minutes)...";

  const form = new FormData();
  form.append("file", file);

  try {
    const res = await fetch("/api/novelty-check", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    const result = await res.json();
    renderNoveltyResult(result);
    el("#novelty-overlay").classList.remove("hidden");
  } catch (err) {
    alert(`Novelty check failed: ${err.message}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Check against full corpus";
  }
});

function renderNoveltyResult(result) {
  const content = el("#novelty-content");

  const verdictClass = result.novelty_verdict === "likely novel" ? "is-done"
    : result.novelty_verdict === "substantially overlapping" ? "is-error" : "";

  const gapText = result.fits_identified_gap === true
    ? "Yes — this (category, dataset) combination was not found anywhere in the current corpus."
    : result.fits_identified_gap === false
      ? "No — this combination already exists elsewhere in the corpus."
      : "Not determined (nearest category has no gap data yet).";

  content.innerHTML = `
    <div class="record-kicker">NOVELTY CHECK · FULL CORPUS</div>
    <h2 class="record-title">${result.uploaded_title}</h2>

    <div class="ledger-row">
      <div class="ledger-row__label">Verdict</div>
      <div class="ledger-row__value">
        <span class="job-status__stage ${verdictClass}" style="display:inline-block;">${result.novelty_verdict}</span>
      </div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Overlap</div>
      <div class="ledger-row__value">${result.overlap_summary || "—"}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Distinguishing</div>
      <div class="ledger-row__value">${result.distinguishing_factors || "—"}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Fits a gap?</div>
      <div class="ledger-row__value">${gapText}</div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Most similar</div>
      <div class="ledger-row__value">
        <div class="tag-list">
          ${result.similar_papers.map((p) =>
            `<span class="tag" title="${p.category}">${p.title} (${p.similarity.toFixed(2)})</span>`
          ).join("")}
        </div>
      </div>
    </div>
    <div class="ledger-row">
      <div class="ledger-row__label">Your summary</div>
      <div class="ledger-row__value">${result.uploaded_summary || "—"}</div>
    </div>
  `;
}

el("#record-close").addEventListener("click", closeOverlays);
el("#compare-close").addEventListener("click", closeOverlays);
el("#novelty-close").addEventListener("click", closeOverlays);
el("#record-overlay").addEventListener("click", (e) => { if (e.target.id === "record-overlay") closeOverlays(); });
el("#compare-overlay").addEventListener("click", (e) => { if (e.target.id === "compare-overlay") closeOverlays(); });
el("#novelty-overlay").addEventListener("click", (e) => { if (e.target.id === "novelty-overlay") closeOverlays(); });

/* ---------- Cumulative full-corpus table ---------- */

const TABLE_COLUMNS = [
  { key: "paper_id", label: "ID", mono: true, format: (v) => v.slice(0, 8).toUpperCase() },
  { key: "title", label: "Title" },
  { key: "authors", label: "Authors", format: (v) => (v || []).join(", ") },
  { key: "year", label: "Year", mono: true },
  { key: "venue", label: "Venue" },
  { key: "category", label: "Category" },
  { key: "relevance_score", label: "Relevance", mono: true, format: (v) => (v == null ? "—" : v.toFixed(3)) },
  { key: "citation_count", label: "Citations", mono: true, format: (v) => v ?? "—" },
  { key: "has_full_text", label: "Full text?", mono: true, format: (v) => (v ? "Yes" : "No") },
  { key: "problem_addressed", label: "Problem" },
  { key: "method", label: "Method" },
  { key: "datasets", label: "Datasets", format: (v) => (v || []).join("; ") || "None listed" },
  { key: "metrics", label: "Metrics", format: (v) => (v || []).join("; ") || "None listed" },
  { key: "results", label: "Results" },
  { key: "inferences", label: "Inferences" },
  { key: "novelty_claim", label: "Novelty claim" },
  { key: "limitations", label: "Limitations" },
  { key: "key_findings", label: "Findings" },
  { key: "summary", label: "Summary" },
];

let _fullCorpusCache = null;

async function openCorpusTable() {
  const table = el("#corpus-table");
  table.innerHTML = "<tr><td>Loading full corpus...</td></tr>";
  el("#table-overlay").classList.remove("hidden");

  try {
    const papers = await fetchJSON("/api/papers/full");
    _fullCorpusCache = papers;
    renderCorpusTable(papers);
  } catch (err) {
    table.innerHTML = `<tr><td>Could not load corpus table: ${err.message}</td></tr>`;
  }
}

function renderCorpusTable(papers) {
  const table = el("#corpus-table");

  const headerRow = TABLE_COLUMNS.map((c) => `<th>${c.label}</th>`).join("");
  const bodyRows = papers.map((p) => {
    const cells = TABLE_COLUMNS.map((c) => {
      const raw = p[c.key];
      const value = c.format ? c.format(raw) : (raw ?? "—");
      const cls = c.mono ? ' class="mono-cell"' : "";
      return `<td${cls}>${value}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");

  table.innerHTML = `<thead><tr>${headerRow}</tr></thead><tbody>${bodyRows}</tbody>`;
}

function downloadCorpusCSV() {
  if (!_fullCorpusCache) return;

  const escapeCsv = (val) => {
    const s = String(val ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };

  const headers = TABLE_COLUMNS.map((c) => c.label);
  const rows = _fullCorpusCache.map((p) =>
    TABLE_COLUMNS.map((c) => {
      const raw = p[c.key];
      return escapeCsv(c.format ? c.format(raw) : (raw ?? ""));
    }).join(",")
  );

  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "researchgpt_corpus.csv";
  a.click();
  URL.revokeObjectURL(url);
}

el("#corpus-table-toggle").addEventListener("click", openCorpusTable);
el("#table-close").addEventListener("click", closeOverlays);
el("#table-overlay").addEventListener("click", (e) => { if (e.target.id === "table-overlay") closeOverlays(); });
el("#table-export-csv").addEventListener("click", downloadCorpusCSV);

/* ---------- Corpus analysis (synthesis + gap matrix) ---------- */

async function fetchJSONOrNull(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function openCorpusAnalysis() {
  const content = el("#analysis-content");
  content.innerHTML = "<p>Loading corpus analysis&hellip;</p>";
  el("#analysis-overlay").classList.remove("hidden");

  const [synthesis, gaps] = await Promise.all([
    fetchJSONOrNull("/api/synthesis"),
    fetchJSONOrNull("/api/gaps"),
  ]);

  if (!synthesis && !gaps) {
    content.innerHTML = `
      <div class="analysis-empty-note">
        No corpus analysis on file yet for the current corpus. This is generated automatically as
        part of a search or upload run (the final two stages) — run a new search/upload, or if you
        collected this corpus before Stage 5/6 existed, run:<br><br>
        <code>python -m src.synthesis.corpus_synthesis --config configs/config.yaml</code><br>
        <code>python -m src.synthesis.gap_analysis --config configs/config.yaml</code>
      </div>
    `;
    return;
  }

  content.innerHTML = renderSynthesisSection(synthesis) + renderGapSection(gaps);
}

function renderSynthesisSection(synthesis) {
  if (!synthesis) {
    return `<div class="analysis-section-title">Collective Synthesis</div>
            <div class="analysis-empty-note">Not available for this corpus yet.</div>`;
  }

  const overall = synthesis.overall || {};
  const overallFailedNote = overall._synthesis_failed
    ? `<div class="analysis-empty-note">The LLM call for this section failed (timeout or unparseable output) —
       this is a processing failure, not "no shared findings." Try re-running:
       <code>python -m src.synthesis.corpus_synthesis --config configs/config.yaml</code></div>`
    : "";
  const overallExamplePapers = (overall.example_papers && overall.example_papers.length)
    ? `<div class="ledger-row">
         <div class="ledger-row__label">Spot-check against</div>
         <div class="ledger-row__value">
           <div class="tag-list">${overall.example_papers.map((t) => `<span class="tag">${t}</span>`).join("")}</div>
         </div>
       </div>`
    : "";
  const overallRows = [
    ["Shared problem landscape", overall.shared_problem_landscape],
    ["Common methods / trends", overall.common_methods_trends],
    ["Dominant datasets / metrics", overall.dominant_datasets_metrics],
    ["Convergence or conflicts", overall.convergence_or_conflicts],
  ].map(([label, value]) => `
    <div class="ledger-row">
      <div class="ledger-row__label">${label}</div>
      <div class="ledger-row__value">${value || "—"}</div>
    </div>
  `).join("") + overallExamplePapers;

  const perCategory = Object.entries(synthesis.per_category || {}).map(([category, info]) => {
    const examplePapers = (info.example_papers && info.example_papers.length)
      ? `<div class="ledger-row">
           <div class="ledger-row__label">Spot-check against</div>
           <div class="ledger-row__value">
             <div class="tag-list">${info.example_papers.map((t) => `<span class="tag">${t}</span>`).join("")}</div>
           </div>
         </div>`
      : "";
    return `
    <div class="category-block">
      <div class="category-block__header">${category}</div>
      <div class="category-block__body">
        ${info._synthesis_failed
          ? '<div class="analysis-empty-note">LLM call failed for this category — not "no shared findings," a processing failure. Re-run synthesis to retry.</div>'
          : `
        <div class="ledger-row">
          <div class="ledger-row__label">Problem</div>
          <div class="ledger-row__value">${info.shared_problem_landscape || "—"}</div>
        </div>
        <div class="ledger-row">
          <div class="ledger-row__label">Methods</div>
          <div class="ledger-row__value">${info.common_methods_trends || "—"}</div>
        </div>
        <div class="ledger-row">
          <div class="ledger-row__label">Datasets/Metrics</div>
          <div class="ledger-row__value">${info.dominant_datasets_metrics || "—"}</div>
        </div>
        ${examplePapers}
      `}
      </div>
    </div>
  `;
  }).join("");

  return `
    <div class="analysis-section-title">Collective Synthesis — Overall (${synthesis.paper_count || "?"} papers)</div>
    ${overallFailedNote || overallRows}
    <div class="analysis-section-title">Per Category</div>
    ${perCategory || '<div class="analysis-empty-note">No per-category breakdown available.</div>'}
  `;
}

function renderGapSection(gaps) {
  if (!gaps) {
    return `<div class="analysis-section-title">Gap Matrix</div>
            <div class="analysis-empty-note">Not available for this corpus yet.</div>`;
  }

  const { categories, datasets, matrix, candidate_gaps } = gaps;

  if (!datasets || datasets.length === 0) {
    return `<div class="analysis-section-title">Gap Matrix</div>
            <div class="analysis-empty-note">No dataset data available to build a gap matrix from.</div>`;
  }

  const headerCells = datasets.map((d) => `<th>${d}</th>`).join("");
  const bodyRows = categories.map((cat) => {
    const cells = datasets.map((d) => {
      const count = matrix[cat]?.[d] ?? 0;
      const cls = count === 0 ? ' class="count-zero"' : "";
      return `<td${cls}>${count}</td>`;
    }).join("");
    return `<tr><th>${cat}</th>${cells}</tr>`;
  }).join("");

  const gapTags = (candidate_gaps || []).map((g) =>
    `<span class="gap-tag">${g.category} × ${g.dataset}</span>`
  ).join("");

  return `
    <div class="analysis-section-title">Gap Matrix — Category × Dataset (paper counts)</div>
    <div class="table-scroll-wrap" style="max-height:320px;">
      <table class="corpus-table gap-matrix-table">
        <thead><tr><th>Category</th>${headerCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
    <div class="analysis-section-title">Candidate Gaps (${(candidate_gaps || []).length} empty combinations)</div>
    ${candidate_gaps && candidate_gaps.length
      ? `<div class="gap-tag-list">${gapTags}</div>`
      : '<div class="analysis-empty-note">No gaps found — every category/dataset combination is represented.</div>'}
  `;
}

el("#analysis-toggle").addEventListener("click", openCorpusAnalysis);
el("#analysis-close").addEventListener("click", closeOverlays);
el("#analysis-overlay").addEventListener("click", (e) => { if (e.target.id === "analysis-overlay") closeOverlays(); });
el("#compare-toggle").addEventListener("click", openCompare);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeOverlays(); });

init();