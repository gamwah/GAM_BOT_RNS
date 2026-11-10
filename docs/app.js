"use strict";

/* RNS Screener web app. No build step: static files served by GitHub Pages.
   Reads JSON the screener commits to docs/data/. Settings are edited by committing
   docs/data/settings.json through the GitHub API with a token you paste in once
   (kept only in this browser's localStorage). */

const REPO = { owner: "gamwah", repo: "GAM_BOT_RNS", branch: "master" };
const SETTINGS_PATH = "docs/data/settings.json";
const DEFAULT_KEYWORDS = ["trading", "results", "update", "guidance", "upgrade", "ahead", "statement", "profit", "outlook"];

const CLASS_ORDER = ["STRONGLY_AHEAD", "AHEAD", "MIXED", "BELOW", "IN_LINE", "NO_GUIDANCE"];
const CLASS_LABEL = {
  STRONGLY_AHEAD: "🚀 Strongly ahead", AHEAD: "✅ Ahead", MIXED: "⚖️ Mixed",
  BELOW: "🔻 Below", IN_LINE: "In line", NO_GUIDANCE: "No guidance",
};
const HIGHLIGHT = new Set(["STRONGLY_AHEAD", "AHEAD", "MIXED", "BELOW"]);
const HORIZON_LABEL = { "1d": "Day 1", "5d": "5 days", "1m": "1 month", "3m": "3 months" };
const HORIZON_SHORT = { "1d": "1d", "5d": "5d", "1m": "1m", "3m": "3m" };

const state = {
  tab: "results",
  index: null, indexFailed: false,
  date: null, day: null, dayFailed: false,
  filter: "highlights", query: "",
  settings: null, draft: null, settingsFailed: false, saving: false,
  backtest: null, backtestFailed: false, horizon: "5d", perfClass: "ALL",
};

/* ---------- helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const view = () => $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clone = (o) => JSON.parse(JSON.stringify(o));
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode etc. */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
const TOKEN_KEY = "rns_gh_token";

function fmtDate(d, short = false) {
  const dt = new Date(d + "T12:00:00");
  if (isNaN(dt)) return d;
  const opts = short ? { weekday: "short", day: "numeric", month: "short" } : { weekday: "short", day: "numeric", month: "short", year: "numeric" };
  return dt.toLocaleDateString("en-GB", opts);
}
const fmtTime = (t) => (String(t || "").match(/\d{1,2}:\d{2}\s?[AP]M/i) || [""])[0];
const fmtGBP = (n) => (n == null ? "value n/a" : "£" + Math.round(n).toLocaleString("en-GB"));
const fmtNum = (n) => (n == null ? "?" : Number(n).toLocaleString("en-GB"));
function fmtPct(x, signed = true) {
  if (x == null || isNaN(x)) return "–";
  const v = (x * 100).toFixed(1);
  return (signed && x > 0 ? "+" : "") + v + "%";
}
const signClass = (x) => (x == null ? "nil" : x > 0 ? "pos" : x < 0 ? "neg" : "nil");

async function fetchJSON(path) {
  const res = await fetch("data/" + path, { cache: "no-store" });
  if (!res.ok) throw new Error(path + ": HTTP " + res.status);
  return res.json();
}

let toastTimer;
function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (isErr ? " err" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isErr ? 7000 : 3500);
}

/* ---------- tabs ---------- */
const TABS = ["results", "watchlist", "performance"];

function setTab(tab, { push = true } = {}) {
  if (!TABS.includes(tab)) tab = "results";
  state.tab = tab;
  store.set("rns_tab", tab);
  if (push && location.hash !== "#" + tab) history.replaceState(null, "", "#" + tab);
  document.querySelectorAll(".tab").forEach((b) => {
    if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  render();
  window.scrollTo(0, 0);
}

async function render() {
  const tab = state.tab;
  view().innerHTML = '<p class="empty">Loading…</p>';
  if (tab === "results") await renderResults();
  else if (tab === "watchlist") await renderWatchlist();
  else await renderPerformance();
}

/* ======================================================================
   RESULTS
   ====================================================================== */
async function ensureSettings() {
  if (state.settings || state.settingsFailed) return;
  try {
    state.settings = await fetchJSON("settings.json");
    state.draft = clone(state.settings);
  } catch { state.settingsFailed = true; }
}

async function ensureIndex() {
  if (state.index || state.indexFailed) return;
  try {
    state.index = await fetchJSON("index.json");
    const s = $("#status");
    if (state.index.updated) s.textContent = "Updated " + new Date(state.index.updated).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch { state.indexFailed = true; }
}

async function loadDay(date) {
  state.date = date;
  state.day = null; state.dayFailed = false;
  try { state.day = await fetchJSON("results/" + date + ".json"); } catch { state.dayFailed = true; }
}

async function renderResults() {
  await Promise.all([ensureIndex(), ensureSettings()]);
  const dates = state.index?.dates ?? [];
  if (!dates.length) {
    view().innerHTML = `<div class="empty"><strong>No results saved yet</strong>
      The screener now saves every day's classifications here. They'll appear after its next run.
      To fill in past days, run <code>python backfill.py START END</code> on your PC.</div>`;
    return;
  }
  if (!state.date || !dates.some((d) => d.date === state.date)) await loadDay(dates[0].date);
  else if (!state.day && !state.dayFailed) await loadDay(state.date);

  const idx = dates.findIndex((d) => d.date === state.date);
  const options = dates.map((d) => {
    const c = d.counts || {};
    const bits = [c.STRONGLY_AHEAD && "🚀" + c.STRONGLY_AHEAD, c.AHEAD && "✅" + c.AHEAD, c.MIXED && "⚖️" + c.MIXED, c.BELOW && "🔻" + c.BELOW, c.buys && "👔" + c.buys].filter(Boolean).join(" ");
    return `<option value="${esc(d.date)}" ${d.date === state.date ? "selected" : ""}>${esc(fmtDate(d.date, true))}${bits ? " · " + bits : ""}</option>`;
  }).join("");

  view().innerHTML = `
    <div class="datebar">
      <button class="btn" data-act="older" aria-label="Previous day" ${idx >= dates.length - 1 ? "disabled" : ""}>‹</button>
      <select id="datesel" aria-label="Date">${options}</select>
      <button class="btn" data-act="newer" aria-label="Next day" ${idx <= 0 ? "disabled" : ""}>›</button>
    </div>
    <div id="chips"></div>
    <input class="search" id="q" type="search" placeholder="Search ticker or company" value="${esc(state.query)}" aria-label="Search">
    <div id="list"></div>`;
  renderResultsList();
}

function watchSet() { return new Set((state.settings?.watchlist ?? []).map((t) => t.toUpperCase())); }

function renderResultsList() {
  const list = $("#list"), chips = $("#chips");
  if (!list) return;
  if (state.dayFailed || !state.day) {
    chips.innerHTML = "";
    list.innerHTML = `<p class="empty"><strong>Couldn't load ${esc(state.date)}</strong>Check your connection and try again.</p>`;
    return;
  }
  const day = state.day;
  const watch = watchSet();
  const threshold = state.settings?.min_director_buy_value ?? 0;
  const results = day.results || [];
  const dealings = day.dealings || [];
  const isWatch = (r) => r.watchlist || watch.has(String(r.ticker).toUpperCase());
  const buys = dealings.filter((d) => d.direction === "buy");
  const bigBuys = buys.filter((d) => (d.total_value_gbp || 0) >= threshold);

  const count = (cls) => results.filter((r) => r.classification === cls).length;
  const chipDefs = [
    ["highlights", "Highlights", results.filter((r) => HIGHLIGHT.has(r.classification) || isWatch(r)).length + bigBuys.length],
    ["STRONGLY_AHEAD", "🚀 Strongly ahead", count("STRONGLY_AHEAD")],
    ["AHEAD", "✅ Ahead", count("AHEAD")],
    ["MIXED", "⚖️ Mixed", count("MIXED")],
    ["BELOW", "🔻 Below", count("BELOW")],
    ["watchlist", "⭐ Watchlist", results.filter(isWatch).length],
    ["buys", "👔 Director buys", buys.length],
    ["other", "In line / none", count("IN_LINE") + count("NO_GUIDANCE")],
    ["all", "Everything", results.length + dealings.length],
  ];
  chips.innerHTML = `<div class="chips" role="group" aria-label="Filter">${chipDefs.map(([k, label, n]) =>
    `<button class="chip" data-filter="${k}" aria-pressed="${state.filter === k}">${label}<span class="n">${n}</span></button>`).join("")}</div>`;

  const q = state.query.trim().toLowerCase();
  const matchQ = (x) => !q || [x.ticker, x.company, x.headline].some((s) => String(s || "").toLowerCase().includes(q));
  const f = state.filter;

  let shownResults = results.filter((r) => {
    if (f === "highlights") return HIGHLIGHT.has(r.classification) || isWatch(r);
    if (f === "watchlist") return isWatch(r);
    if (f === "other") return r.classification === "IN_LINE" || r.classification === "NO_GUIDANCE";
    if (f === "all") return true;
    if (f === "buys") return false;
    return r.classification === f;
  }).filter(matchQ).sort((a, b) => CLASS_ORDER.indexOf(a.classification) - CLASS_ORDER.indexOf(b.classification) || a.id.localeCompare(b.id));

  let shownDealings = dealings.filter((d) => {
    if (f === "highlights") return bigBuys.includes(d);
    if (f === "buys") return d.direction === "buy";
    if (f === "all") return true;
    if (f === "watchlist") return watch.has(String(d.ticker).toUpperCase());
    return false;
  }).filter(matchQ).sort((a, b) => (b.total_value_gbp || 0) - (a.total_value_gbp || 0));

  // clusters: 2+ different directors buying the same stock the same day
  const buyersByTicker = {};
  buys.forEach((d) => { (buyersByTicker[d.ticker] ||= new Set()).add(d.director_name); });
  const isCluster = (d) => d.direction === "buy" && buyersByTicker[d.ticker]?.size >= 2;

  if (!shownResults.length && !shownDealings.length) {
    list.innerHTML = `<p class="empty"><strong>Nothing here</strong>${q ? "No matches for that search." : "No announcements in this view for " + esc(fmtDate(state.date)) + "."}</p>`;
    return;
  }

  list.innerHTML = shownResults.map((r) => `
    <article class="card rns">
      <div class="rns-head">
        <span class="ticker">${esc(r.ticker)}</span>
        <span class="company">${esc(r.company)}</span>
        ${isWatch(r) ? '<span class="star" title="On your watchlist">⭐</span>' : ""}
        <span class="when">${esc(fmtTime(r.time))}</span>
      </div>
      <div class="tags"><span class="pill ${esc(r.classification)}">${esc(CLASS_LABEL[r.classification] || r.classification)}</span>
        ${r.guidance_change && r.guidance_change !== "none_stated" ? `<span class="pill ${r.guidance_change === "upgraded" ? "good" : r.guidance_change === "lowered" ? "bad" : "info"}">Guidance ${esc(r.guidance_change)}</span>` : ""}
        ${r.confidence ? `<span class="muted">${esc(r.confidence)} confidence</span>` : ""}</div>
      ${r.key_quote ? `<p class="quote">“${esc(r.key_quote)}”</p>` : ""}
      ${r.summary ? `<p class="summary">${esc(r.summary)}</p>` : ""}
      <div class="tags">${(r.metrics_ahead || []).map((m) => `<span class="pill info">${esc(m)}</span>`).join("")}
        <a class="src" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.headline)} ↗</a></div>
    </article>`).join("") + shownDealings.map((d) => `
    <article class="card rns dealing">
      <div class="rns-head">
        <span class="ticker">${esc(d.ticker)}</span>
        <span class="company">${esc(d.company)}</span>
        ${isCluster(d) ? '<span class="pill good" title="2+ directors buying the same day">⭐ cluster</span>' : ""}
        <span class="when">${esc(fmtTime(d.time))}</span>
      </div>
      <p class="summary">👔 ${esc(d.director_name || "Director")}${d.role ? " (" + esc(d.role) + ")" : ""}
        ${d.direction === "buy" ? "bought" : d.direction === "sell" ? "sold" : "dealt in"}
        <span class="amount">${esc(fmtGBP(d.total_value_gbp))}</span>
        ${d.shares != null ? `<span class="muted">· ${esc(fmtNum(d.shares))} shares${d.price_per_share_gbp != null ? " @ £" + esc(Number(d.price_per_share_gbp).toFixed(2)) : ""}</span>` : ""}</p>
      <div class="tags"><a class="src" href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.headline)} ↗</a></div>
    </article>`).join("");
}

/* ======================================================================
   WATCHLIST & SETTINGS
   ====================================================================== */
const isDirty = () => JSON.stringify(state.draft) !== JSON.stringify(state.settings);

function tagBox(listName, items) {
  return `<div class="tagbox" data-list="${listName}">${items.map((t, i) =>
    `<span class="tag">${esc(t)}<button data-act="remove" data-list="${listName}" data-i="${i}" aria-label="Remove ${esc(t)}">×</button></span>`).join("")}</div>`;
}

function testHeadline(headline, keywords) {
  if (/director[/\s]*pdmr\s+(shareholding|dealing)/i.test(headline)) return { kind: "dealing" };
  const cleaned = (keywords || []).map((k) => k.trim()).filter(Boolean);
  const list = cleaned.length ? cleaned : DEFAULT_KEYWORDS;
  const m = headline.match(new RegExp("\\b(" + list.map(escapeRe).join("|") + ")\\b", "i"));
  return m ? { kind: "results", word: m[1] } : { kind: "drop" };
}

function verdictHTML(headline) {
  if (!headline.trim()) return "";
  const r = testHeadline(headline, state.draft.keywords);
  if (r.kind === "dealing") return '<div class="verdict ok">👔 Picked up as a director dealing.</div>';
  if (r.kind === "results") return `<div class="verdict ok">✅ Would be picked up and sent to Claude (matches “${esc(r.word)}”).</div>`;
  return '<div class="verdict no">✖ Would be dropped: no keyword matches this headline. Add one below if it should be caught.</div>';
}

function connectCard() {
  const token = store.get(TOKEN_KEY);
  if (token) {
    return `<section class="card" id="connect"><h2>GitHub connection</h2>
      <p class="hint">✅ Connected. Saving commits <code>settings.json</code> to <code>${esc(REPO.owner)}/${esc(REPO.repo)}</code>. The token is stored only in this browser.</p>
      <button class="btn small" data-act="disconnect">Disconnect</button></section>`;
  }
  return `<section class="card" id="connect"><h2>Connect GitHub to save changes</h2>
    <p class="hint">Viewing is open to anyone, but saving needs permission to commit to the repo. Create a
      <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">fine-grained token</a>
      limited to <code>${esc(REPO.repo)}</code> with <strong>Contents: Read and write</strong>, then paste it here once. It stays in this browser only.</p>
    <form data-form="token" class="row"><input type="password" name="token" autocomplete="off" placeholder="github_pat_…" aria-label="GitHub token" required>
      <button class="btn primary" type="submit">Connect</button></form></section>`;
}

async function renderWatchlist() {
  await ensureSettings();
  if (state.settingsFailed || !state.draft) {
    view().innerHTML = '<p class="empty"><strong>Couldn\'t load settings</strong>Check your connection and try again.</p>';
    return;
  }
  const d = state.draft;
  view().innerHTML = `
    <section class="card"><h2>Watchlist</h2>
      <p class="hint">Always reported, whatever the classification (even “in line”).</p>
      ${tagBox("watchlist", d.watchlist)}
      <form data-form="add" data-list="watchlist" class="row"><input type="text" name="v" placeholder="Add ticker, e.g. VLX" autocapitalize="characters" autocomplete="off" aria-label="Add ticker">
        <button class="btn" type="submit">Add</button></form>
    </section>

    <section class="card"><h2>Pick-up keywords</h2>
      <p class="hint">An announcement is only sent to Claude if its <em>headline</em> contains one of these words. This is why “AGM Statement” was missed until “statement” was added.</p>
      ${tagBox("keywords", d.keywords)}
      <form data-form="add" data-list="keywords" class="row"><input type="text" name="v" placeholder="Add keyword, e.g. pre-close" autocapitalize="none" autocomplete="off" aria-label="Add keyword">
        <button class="btn" type="submit">Add</button></form>
      <label class="field" for="tester" style="margin-top:14px">Test a headline</label>
      <input type="text" id="tester" placeholder="e.g. AGM Statement" autocomplete="off" value="${esc(state.testHeadline || "")}">
      <div id="verdict">${verdictHTML(state.testHeadline || "")}</div>
    </section>

    <section class="card"><h2>Director buys</h2>
      <label class="field" for="minbuy">Minimum buy value to report (£)</label>
      <input type="number" id="minbuy" min="0" step="1000" inputmode="numeric" value="${esc(d.min_director_buy_value)}">
    </section>

    ${connectCard()}
    <div class="savebar" id="savebar"></div>
    <p class="hint">Changes apply from the screener's next run. The Telegram and X messages follow the same watchlist.</p>`;
  updateSavebar();
}

function updateSavebar() {
  const bar = $("#savebar");
  if (!bar) return;
  const dirty = isDirty();
  bar.innerHTML = `<span class="${dirty ? "" : "muted"}">${state.saving ? "Saving…" : dirty ? "Unsaved changes" : "All changes saved"}</span>
    <span class="row"><button class="btn" data-act="discard" ${dirty && !state.saving ? "" : "disabled"}>Discard</button>
    <button class="btn primary" data-act="save" ${dirty && !state.saving ? "" : "disabled"}>Save</button></span>`;
}

function addTag(listName, raw) {
  const d = state.draft;
  let v = raw.trim();
  if (!v) return null;
  if (listName === "watchlist") {
    v = v.toUpperCase().replace(/\s+/g, "");
    if (!/^[A-Z0-9.\-]{1,10}$/.test(v)) return "Tickers are letters, numbers, “.” or “-” (max 10).";
  } else {
    v = v.toLowerCase().replace(/\s+/g, " ");
    if (v.length > 40) return "Keep keywords under 40 characters.";
  }
  if (d[listName].includes(v)) return "Already in the list.";
  d[listName].push(v);
  return null;
}

async function ghFetch(path, token, opts = {}) {
  const res = await fetch("https://api.github.com/repos/" + REPO.owner + "/" + REPO.repo + path, {
    ...opts,
    headers: { Accept: "application/vnd.github+json", Authorization: "Bearer " + token, "X-GitHub-Api-Version": "2022-11-28", ...(opts.headers || {}) },
  });
  if (res.ok) return res.json();
  const err = new Error("GitHub error " + res.status);
  err.status = res.status;
  throw err;
}

const b64 = (str) => { let bin = ""; new TextEncoder().encode(str).forEach((b) => { bin += String.fromCharCode(b); }); return btoa(bin); };
const unb64 = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, "")), (c) => c.charCodeAt(0)));

function explainGitHubError(e) {
  if (e.status === 401) return "GitHub rejected the token (expired or mistyped). Disconnect and connect again.";
  if (e.status === 403 || e.status === 404) return "That token can't write to " + REPO.owner + "/" + REPO.repo + ". It needs Contents: Read and write on this repository.";
  if (e.status === 409 || e.status === 422) return "Settings changed elsewhere while you were editing. Reload the page and redo your change.";
  return e.message || "Couldn't reach GitHub. Check your connection.";
}

async function saveSettings() {
  const token = store.get(TOKEN_KEY);
  if (!token) { toast("Connect GitHub first (card below).", true); $("#connect")?.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
  if (!state.draft.watchlist.length) { toast("Keep at least one ticker, or the watchlist does nothing.", true); return; }
  if (!state.draft.keywords.length) { toast("Keep at least one keyword, or nothing gets picked up.", true); return; }
  const min = Number(state.draft.min_director_buy_value);
  if (!Number.isFinite(min) || min < 0) { toast("Minimum buy value must be 0 or more.", true); return; }
  state.draft.min_director_buy_value = min;

  state.saving = true; updateSavebar();
  try {
    const file = await ghFetch("/contents/" + SETTINGS_PATH + "?ref=" + encodeURIComponent(REPO.branch), token);
    let remote = {};
    try { remote = JSON.parse(unb64(file.content)); } catch { /* start fresh */ }
    const next = { ...remote, watchlist: state.draft.watchlist, keywords: state.draft.keywords, min_director_buy_value: min };
    await ghFetch("/contents/" + SETTINGS_PATH, token, {
      method: "PUT",
      body: JSON.stringify({ message: "Update settings from app", content: b64(JSON.stringify(next, null, 2) + "\n"), sha: file.sha, branch: REPO.branch }),
    });
    state.settings = clone(state.draft);
    toast("Saved. Applies from the next screener run.");
  } catch (e) {
    toast(explainGitHubError(e), true);
  } finally {
    state.saving = false; updateSavebar();
  }
}

/* ======================================================================
   PERFORMANCE
   ====================================================================== */
async function renderPerformance() {
  if (!state.backtest && !state.backtestFailed) {
    try { state.backtest = await fetchJSON("backtest.json"); } catch { state.backtestFailed = true; }
  }
  const bt = state.backtest;
  if (!bt || !bt.events?.length) {
    view().innerHTML = `<div class="empty"><strong>No performance data yet</strong>
      ${bt ? "The backtest has run but there are no classified results to measure yet." : "The daily backtest job hasn't produced results yet."}
      Each “ahead” call needs a few days of share-price history before it can be measured, and a month or more for the longer horizons.
      To measure past days straight away, run <code>python backfill.py START END</code> then <code>python backtest.py</code> on your PC.</div>`;
    return;
  }
  const h = state.horizon;
  const measured = bt.events.filter((e) => e.returns).length;
  const rows = CLASS_ORDER.slice(0, 4).map((cls) => ({ cls, s: bt.summary?.[cls]?.[h] || { n: 0 } }));
  const maxAbs = Math.max(0.01, ...rows.filter((r) => r.s.n).map((r) => Math.abs(r.s.median_excess)));

  const evs = bt.events.filter((e) => state.perfClass === "ALL" || e.classification === state.perfClass);

  view().innerHTML = `
    <p class="hint">Benchmark: ${esc(bt.benchmark === "^FTAS" ? "FTSE All-Share" : bt.benchmark || "n/a")} · ${measured} of ${bt.events.length} calls measured · updated ${esc(new Date(bt.generated).toLocaleDateString("en-GB", { day: "numeric", month: "short" }))}</p>
    <div class="seg" role="group" aria-label="Horizon">${bt.horizons.map((k) => `<button data-h="${k}" aria-pressed="${k === h}">${esc(HORIZON_LABEL[k] || k)}</button>`).join("")}</div>

    <section class="card"><h2>Return vs the market · ${esc(HORIZON_LABEL[h] || h)}</h2>
      <table><thead><tr><th>Call</th><th>Calls</th><th>Typical vs market</th><th>Average</th><th>Beat it</th></tr></thead><tbody>
      ${rows.map(({ cls, s }) => `<tr><td><span class="pill ${cls}">${esc(CLASS_LABEL[cls])}</span></td>
        <td>${s.n}${s.n && s.n < 10 ? ' <span class="muted" title="Small sample">*</span>' : ""}</td>
        <td class="${signClass(s.median_excess)}"><strong>${s.n ? fmtPct(s.median_excess) : "–"}</strong></td>
        <td class="${signClass(s.avg_excess)}">${s.n ? fmtPct(s.avg_excess) : "–"}</td>
        <td>${s.n ? Math.round(s.hit_rate * 100) + "%" : "–"}</td></tr>`).join("")}
      </tbody></table>
      <div class="bars" aria-hidden="true">${rows.filter((r) => r.s.n).map(({ cls, s }) => {
        const w = Math.min(50, (Math.abs(s.median_excess) / maxAbs) * 50);
        return `<div class="bar-row"><span>${esc(CLASS_LABEL[cls])}</span>
          <div class="bar-track"><div class="bar ${s.median_excess >= 0 ? "pos" : "neg"}" style="${s.median_excess >= 0 ? "left:50%" : "right:50%"};width:${w}%"></div></div>
          <span class="val ${signClass(s.median_excess)}">${fmtPct(s.median_excess)}</span></div>`;
      }).join("")}</div>
      <p class="hint">“Typical” is the median, which a few extreme movers can't skew; “Average” is the mean. * fewer than 10 calls: a guide, not a result.</p>
    </section>

    <section class="card"><h2>Typical vs market, all horizons</h2>
      <table><thead><tr><th>Call</th>${bt.horizons.map((k) => `<th>${esc(HORIZON_SHORT[k] || k)}</th>`).join("")}</tr></thead><tbody>
      ${CLASS_ORDER.slice(0, 4).map((cls) => `<tr><td><span class="pill ${cls}">${esc(CLASS_LABEL[cls])}</span></td>${bt.horizons.map((k) => {
        const s = bt.summary?.[cls]?.[k];
        return `<td class="${signClass(s?.median_excess)}">${s?.n ? fmtPct(s.median_excess) : "–"}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table>
    </section>

    <section class="card"><h2>Every call</h2>
      <select id="perfclass" aria-label="Filter by call" style="margin-bottom:10px">
        <option value="ALL">All calls</option>
        ${CLASS_ORDER.slice(0, 4).map((c) => `<option value="${c}" ${state.perfClass === c ? "selected" : ""}>${esc(CLASS_LABEL[c])}</option>`).join("")}
      </select>
      <table><thead><tr><th>Stock</th><th>${esc(HORIZON_LABEL[h] || h)}</th><th>vs market</th></tr></thead><tbody>
      ${evs.map((e) => `<tr><td><a href="${esc(e.url)}" target="_blank" rel="noopener"><strong>${esc(e.ticker)}</strong></a>
          <span class="pill ${e.classification}" style="margin-left:6px">${esc((CLASS_LABEL[e.classification] || "").replace(/^\S+\s/, ""))}</span><br>
          <span class="muted">${esc(fmtDate(e.date))}</span></td>
        <td class="${signClass(e.returns?.[h])}">${e.returns ? (e.returns[h] == null ? "pending" : fmtPct(e.returns[h])) : "no price"}</td>
        <td class="${signClass(e.excess?.[h])}">${e.excess && e.excess[h] != null ? fmtPct(e.excess[h]) : "–"}</td></tr>`).join("") || '<tr><td colspan="3" class="muted">No calls in this view.</td></tr>'}
      </tbody></table>
      ${bt.missing?.length ? `<p class="hint">No Yahoo Finance price data for: ${esc(bt.missing.join(", "))}</p>` : ""}
      ${bt.suspect?.length ? `<p class="hint">Left out as likely bad quotes (moves over 500%): ${esc(bt.suspect.join(", "))}</p>` : ""}
    </section>
    <p class="disclaimer">Daily closes only; returns measured from the prior day's close. Small samples and survivorship effects apply. This is research, not investment advice.</p>`;
}

/* ======================================================================
   EVENTS
   ====================================================================== */
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-tab],[data-act],[data-filter],[data-h]");
  if (!t) return;
  if (t.dataset.tab) return setTab(t.dataset.tab);
  if (t.dataset.filter) { state.filter = t.dataset.filter; return renderResultsList(); }
  if (t.dataset.h) { state.horizon = t.dataset.h; return renderPerformance(); }

  const dates = state.index?.dates ?? [];
  const i = dates.findIndex((d) => d.date === state.date);
  switch (t.dataset.act) {
    case "older": if (i < dates.length - 1) { await loadDay(dates[i + 1].date); renderResults(); } break;
    case "newer": if (i > 0) { await loadDay(dates[i - 1].date); renderResults(); } break;
    case "remove": state.draft[t.dataset.list].splice(Number(t.dataset.i), 1); renderWatchlist(); break;
    case "discard": state.draft = clone(state.settings); renderWatchlist(); break;
    case "save": saveSettings(); break;
    case "disconnect": store.del(TOKEN_KEY); renderWatchlist(); toast("Disconnected from GitHub."); break;
  }
});

document.addEventListener("submit", async (ev) => {
  const form = ev.target.closest("form[data-form]");
  if (!form) return;
  ev.preventDefault();
  if (form.dataset.form === "add") {
    const input = form.elements.v;
    const problem = addTag(form.dataset.list, input.value);
    if (problem) { toast(problem, true); return; }
    $("#toast").hidden = true;
    renderWatchlist();
    document.querySelector(`form[data-list="${form.dataset.list}"] input`)?.focus();
  } else if (form.dataset.form === "token") {
    const token = form.elements.token.value.trim();
    if (!token) return;
    try {
      await ghFetch("/contents/" + SETTINGS_PATH + "?ref=" + encodeURIComponent(REPO.branch), token);
      store.set(TOKEN_KEY, token);
      toast("Connected to GitHub.");
      renderWatchlist();
    } catch (e) { toast(explainGitHubError(e), true); }
  }
});

document.addEventListener("input", (ev) => {
  const t = ev.target;
  if (t.id === "q") { state.query = t.value; renderResultsList(); }
  else if (t.id === "tester") { state.testHeadline = t.value; $("#verdict").innerHTML = verdictHTML(t.value); }
  else if (t.id === "minbuy") { state.draft.min_director_buy_value = t.value === "" ? 0 : Number(t.value); updateSavebar(); }
});

document.addEventListener("change", async (ev) => {
  const t = ev.target;
  if (t.id === "datesel") { await loadDay(t.value); renderResults(); }
  else if (t.id === "perfclass") { state.perfClass = t.value; renderPerformance(); }
});

window.addEventListener("hashchange", () => setTab(location.hash.slice(1), { push: false }));
window.addEventListener("beforeunload", (e) => { if (state.draft && state.settings && isDirty()) { e.preventDefault(); e.returnValue = ""; } });

if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* offline support is optional */ });
}

setTab(location.hash.slice(1) || store.get("rns_tab") || "results", { push: false });
