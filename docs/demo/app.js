/* TARA live demo — wizard front end.
   Talks to the demo API when one is reachable; otherwise replays captured
   real pipeline output. It never computes a determination, a deadline or a
   closure itself: every verdict on screen came off the Python agents. */
(() => {
"use strict";

// ---------------------------------------------------------------------------
// transport
// ---------------------------------------------------------------------------
const REPLAY = window.TARA_REPLAY || null;
const LS_KEY = "tara.demo.api";

function defaultApi() {
  const q = new URLSearchParams(location.search).get("api");
  if (q) return q.replace(/\/+$/, "");
  try { const s = localStorage.getItem(LS_KEY); if (s) return s; } catch (e) {}
  if (location.protocol === "http:" || location.protocol === "https:") {
    if (!/github\.io$|claude\.ai$|claudeusercontent\.com$/.test(location.hostname)) {
      return location.origin;
    }
  }
  return "";
}

const S = {
  api: defaultApi(),
  mode: "checking",           // checking | live | replay
  leg: 0,
  presetId: null,
  presets: [],
  holder: null,
  holdings: [],
  answers: {},
  run: null,
  busy: false,
  error: null,
  cell: null,                 // {hid, domain_id}
  actionId: null,
  artefact: null,
  closure: null,
  verification: null,          // server-returned ANCHOR trace for the latest submission
  checklist: {},              // action_id -> explicit true/false, overriding PLAYBOOK_ASSUMPTIONS
  asOf: (REPLAY && REPLAY.as_of) || new Date().toISOString().slice(0, 10)
};

// Obligations the demo assumes are already handled for a given profile, per
// the holder's own account of their situation — "even if these are static
// examples, make it accommodating of that". Keyed by obligation_id (an
// obligation recurs across every holding it is confirmed on, so this is not
// keyed by action_id); the Playbook pre-checks any step whose obligation_id
// appears here, with a note explaining why, and the checkbox stays editable.
const PLAYBOOK_ASSUMPTIONS = {
  priya: {
    obligation_ids: ["OBL-CORR-001"],
    note: "Assumed already done, per Priya's own account of her situation: her Indian bank accounts have already been redesignated NRO/NRE, and she has already declared herself a Non-Resident Indian in her Indian tax filings. Uncheck any step below that is not actually done yet."
  }
};

const FALLBACK_PRESETS = [{
  id:"maeve", name:"Maeve", recommended:true, start_stage:3,
  tagline:"Recommended: one rule change, one affected holding, one verified response",
  story:"Tested judge path: Revenue's fund-tax rate changes from 41% to 38%; TARA selects the post-2026 rule, dates the work, rejects the old rate, and records the trace.",
  answers:{"SQ-03":false},
  holder:{holder_id:"H-101",name:"Maeve",citizenships:["Ireland"],tax_residencies:["Ireland"],
    tax_residency_since:"2010-01-01",eea_swiss_uk_national:true,holder_residency:"Irish tax resident"},
  holdings:[{holding_id:"HLD-101",instrument_type:"offshore_fund",jurisdiction:"Luxembourg",
    acquisition_date:"2018-08-15",status:"held",fatca_threshold_met:false,
    form_3520_reportable_event:false,pfic_reportable_event:false,india_source_income:false}]
}];

const INSTRUMENTS = [
  ["offshore_fund","Offshore fund"],
  ["personal_portfolio_investment_undertaking","Personal portfolio investment undertaking"],
  ["foreign_life_assurance_policy","Foreign life assurance policy"],
  ["direct_equity","Direct equity (listed shares)"],
  ["residential_property","Residential property"],
  ["commercial_property","Commercial property"],
  ["land","Land"],
  ["foreign_bank_account","Foreign bank account"],
  ["immigration_permission","Immigration permission (IRP)"]
];
const COUNTRIES = ["Ireland","India","United States","United Kingdom"];
const RESIDENCIES = ["Irish tax resident","Irish ordinarily resident","Non-resident"];

// keys must match demo/capture_replay.py exactly
const jsnum = v => (typeof v === "boolean" ? (v ? "true" : "false") : v === null || v === undefined ? "null" : String(v));
const answersKey = (pid, a) => pid + "::" + Object.keys(a).sort().map(k => k + "=" + jsnum(a[k])).join(";");
const artefactKey = (pid, aid, art) => pid + "::" + aid + "::" + Object.keys(art).sort().map(k => k + "=" + jsnum(art[k])).join(";");

function profileIsPristine() {
  if (!S.presetId) return false;
  const p = S.presets.find(x => x.id === S.presetId);
  if (!p) return false;
  return JSON.stringify([p.holder, p.holdings]) === JSON.stringify([S.holder, S.holdings]);
}

async function api(path, body) {
  const res = await fetch(S.api + path, body
    ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }
    : {});
  if (!res.ok) throw new Error("Engine returned " + res.status + " for " + path);
  return res.json();
}

async function detectEngine() {
  if (S.api) {
    try {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 8000);
      const res = await fetch(S.api + "/api/health", { signal: ctl.signal });
      clearTimeout(t);
      if (res.ok) { S.mode = "live"; return; }
    } catch (e) { /* fall through to replay */ }
  }
  S.mode = REPLAY ? "replay" : "none";
}

async function loadPresets() {
  if (S.mode === "live") {
    try { S.presets = await api("/api/presets"); return; } catch (e) {}
  }
  try {
    const res = await fetch("presets.json");
    if (res.ok) { S.presets = await res.json(); return; }
  } catch (e) { /* file:// and unusual embeds fall back to the tested case */ }
  S.presets = FALLBACK_PRESETS;
}

async function doRun() {
  S.busy = true; S.error = null; render();
  try {
    if (S.mode === "live") {
      S.run = await api("/api/run", {
        holder: S.holder, holdings: S.holdings, answers: S.answers, as_of: S.asOf
      });
    } else {
      if (!profileIsPristine()) throw new Error("CUSTOM");
      const hit = REPLAY && REPLAY.runs[answersKey(S.presetId, S.answers)];
      if (!hit) throw new Error("CUSTOM");
      S.run = Object.assign({}, hit, { open_band: REPLAY.open_band });
      await new Promise(r => setTimeout(r, 280));   // let the stage read as work
    }
  } catch (e) {
    S.error = e.message === "CUSTOM"
      ? "custom"
      : "The engine did not answer: " + e.message;
    S.run = null;
  }
  S.busy = false; render();
}

async function doVerify(artefact) {
  S.busy = true; S.error = null; render();
  const action = (S.run.actions || []).find(a => a.action_id === S.actionId);
  try {
    if (S.mode === "live") {
      const out = await api("/api/verify", {
        holder: S.holder, holdings: S.holdings, answers: S.answers, as_of: S.asOf,
        domain_id: action.domain_id, action_id: action.action_id, artefact
      });
      S.closure = out.closure;
      S.verification = out.atlas || null;
    } else {
      const hit = REPLAY && REPLAY.verifies[artefactKey(S.presetId, S.actionId, artefact)];
      if (!hit) throw new Error("UNCAPTURED");
      await new Promise(r => setTimeout(r, 260));
      S.closure = hit.closure;
      S.verification = hit.atlas || null;
    }
  } catch (e) {
    S.closure = null;
    S.verification = null;
    S.error = e.message === "UNCAPTURED"
      ? "uncaptured"
      : "ANCHOR could not be reached: " + e.message;
  }
  S.busy = false; render();
}

// ---------------------------------------------------------------------------
// tiny DOM helpers
// ---------------------------------------------------------------------------
const esc = s => String(s === null || s === undefined ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const $ = sel => document.querySelector(sel);
const money = (n, currency) => {
  if (typeof n !== "number") return esc(n);
  return currency === "INR" ? "₹" + n.toLocaleString("en-IN") : "€" + n.toLocaleString("en-IE");
};
const titleCase = s => String(s || "").replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
const shortHash = h => h ? h.slice(0, 10) + "…" + h.slice(-6) : "—";
const dayDiff = (a, b) => Math.round((new Date(a) - new Date(b)) / 86400000);

const LEGS = [
  { id: "brief",     label: "Choose case" },
  { id: "holder",    label: "Case facts" },
  { id: "holdings",  label: "Assets" },
  { id: "chart",     label: "Source chart" },
  { id: "survey",    label: "Parallel scan" },
  { id: "interview", label: "One question" },
  { id: "actions",   label: "Playbook" },
  { id: "evidence",  label: "Check proof" },
  { id: "ledger",    label: "Audit trail" }
];

function legEnabled(i) {
  if (i === 0) return true;
  if (i === 1 || i === 2) return !!S.holder;
  if (i === 3) return !!(S.holder && S.holdings.length);
  return !!S.run;
}

function go(i) {
  S.leg = i;
  window.scrollTo({ top: 0, behavior: "smooth" });
  render();
  // The pitch route is case → parallel scan, but the technical source chart
  // remains available. Either route starts the exact same real pipeline run.
  if (i >= 3 && !S.run && !S.busy) doRun();
}

// ---------------------------------------------------------------------------
// chrome
// ---------------------------------------------------------------------------
function renderChrome() {
  const e = $("#engine");
  e.className = "engine " + (S.mode === "live" ? "live" : S.mode === "replay" ? "replay" : "");
  $("#engineLabel").textContent =
    S.mode === "live" ? "live engine" : S.mode === "replay" ? "captured replay" : S.mode === "checking" ? "checking" : "no engine";
  $("#engineEndpoint").textContent =
    S.mode === "live" ? S.api.replace(/^https?:\/\//, "")
    : S.mode === "replay" ? "recorded " + (REPLAY ? REPLAY.captured_at : "") : "";

  $("#passage").innerHTML = LEGS.map((l, i) => {
    const on = i === S.leg, done = i < S.leg && legEnabled(i);
    return `<li><button class="leg${done ? " done" : ""}" data-leg="${i}" ${on ? 'aria-current="true"' : ""}
      ${legEnabled(i) ? "" : "disabled"} type="button">
      <span class="num"><i>${i}</i></span>${esc(l.label)}</button></li>`;
  }).join("");
}

// ---------------------------------------------------------------------------
// stages
// ---------------------------------------------------------------------------
function bandsSvg() {
  const open = ["SURVEY|reads the source", "LEGEND|cites each duty", "ALMANAC|versions the graph"];
  const tenant = ["COMPASS|does it apply?", "PLOT|what is missing?", "COURSE|what to do, by when", "ANCHOR|does the proof hold?"];
  return `<svg class="bands" viewBox="0 0 880 264" role="img"
      aria-label="Nine agents in three bands: SURVEY, LEGEND and ALMANAC in the open band computed once; COMPASS, PLOT, COURSE and ANCHOR in the tenant band computed per holder, repeated once per jurisdiction by MERIDIAN; ATLAS recording every step.">
    <defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0 1 L7 4 L0 7 z" fill="var(--ink-3)"/></marker></defs>

    <text x="20" y="18" font-family="var(--sans)" font-size="10.5" letter-spacing="1.6"
          fill="var(--shoal-ink)" font-weight="600">OPEN BAND · COMPUTED ONCE · IDENTICAL FOR EVERY HOLDER</text>
    <rect x="8" y="26" width="620" height="62" rx="7" fill="var(--shoal)"
          stroke="color-mix(in srgb, var(--shoal-ink) 30%, transparent)"/>
    ${open.map((sp, i) => {
      const [n, d] = sp.split("|"), x = 24 + i * 196;
      return `<rect x="${x}" y="36" width="178" height="42" rx="5" fill="var(--paper)" stroke="var(--rule)"/>
        <text x="${x + 13}" y="54" font-family="var(--mono)" font-size="12" fill="var(--ink)" font-weight="500">${n}</text>
        <text x="${x + 13}" y="69" font-family="var(--sans)" font-size="10.5" fill="var(--ink-3)">${d}</text>`;
    }).join("")}
    <path d="M320 92 L320 118" stroke="var(--ink-3)" stroke-width="1.2" marker-end="url(#ar)"/>
    <text x="332" y="110" font-family="var(--sans)" font-size="10.5" fill="var(--ink-3)">the Chart: cited obligations, versioned</text>

    <text x="20" y="140" font-family="var(--sans)" font-size="10.5" letter-spacing="1.6"
          fill="var(--ink-3)" font-weight="600">TENANT BAND · COMPUTED FOR ONE HOLDER</text>
    ${tenant.map((sp, i) => {
      const [n, d] = sp.split("|"), x = 24 + i * 212;
      return `<rect x="${x}" y="150" width="194" height="42" rx="5" fill="var(--paper)" stroke="var(--rule)"/>
        <text x="${x + 13}" y="168" font-family="var(--mono)" font-size="12" fill="var(--ink)" font-weight="500">${n}</text>
        <text x="${x + 13}" y="183" font-family="var(--sans)" font-size="10.5" fill="var(--ink-3)">${d}</text>
        ${i < 3 ? `<path d="M${x + 196} 171 L${x + 210} 171" stroke="var(--ink-3)" stroke-width="1.2" marker-end="url(#ar)"/>` : ""}`;
    }).join("")}
    <path d="M24 202 L24 210 L858 210 L858 202" fill="none" stroke="var(--magenta)" stroke-width="1.2"/>
    <text x="441" y="226" text-anchor="middle" font-family="var(--sans)" font-size="11" fill="var(--magenta)">
      <tspan font-family="var(--mono)" font-weight="500">MERIDIAN</tspan> repeats that whole row once per loaded pack, then merges the results</text>

    <rect x="8" y="236" width="864" height="26" rx="6" fill="var(--paper)" stroke="var(--magenta)" stroke-dasharray="4 3"/>
    <text x="24" y="253" font-family="var(--mono)" font-size="11.5" fill="var(--magenta)" font-weight="500">ATLAS</text>
    <text x="80" y="253" font-family="var(--sans)" font-size="10.5" fill="var(--ink-2)">hash-chained append-only ledger — every agent above writes here, and the chain is verified at the end</text>
  </svg>`;
}

function stageBrief() {
  const guideUrl = (S.api || "https://tara-demo.onrender.com") + "/guide";
  const engineNote =
    S.mode === "live"
      ? `<div class="note">The live engine answered. Every result you are about to see is computed on demand by the real agents at <code>${esc(S.api)}</code>.</div>`
      : S.mode === "replay"
      ? `<div class="warn"><b>No live engine reachable, so this is running on captured output.</b> Every figure is still real — it was produced by the same pipeline on ${esc(REPLAY ? REPLAY.captured_at : "")} and recorded verbatim. Point the page at a deployed engine with the <b>Engine…</b> button to run profiles of your own.</div>`
      : `<div class="warn">No engine and no captured data loaded.</div>`;

  return `<header>
      <span class="eyebrow">Challenge 23 · Regulatory Change-to-Action Agent</span>
      <h2>Watch one rule change become one verified action</h2>
      <p class="lede">Start with the tested judge path: Revenue's 41% → 38% fund-tax change. Then use the
      exploratory cases to inspect multi-country and multi-domain breadth without confusing breadth with validation.</p>
    </header>
    <div class="stack">
      ${engineNote}
      <div class="note compact"><b>Prototype scope:</b> controlled source snapshots and synthetic cases only. This is not legal, tax, immigration, or filing advice; a qualified human must review any real-world action.</div>
      <div class="journey" aria-label="Demo journey">
        <div class="journey-step"><span>1</span><div><b>See what changed</b><p>A provision diff and both source hashes.</p></div></div>
        <div class="journey-step"><span>2</span><div><b>See why it applies</b><p>Rule version, case facts, and the explicit decision.</p></div></div>
        <div class="journey-step"><span>3</span><div><b>Test the proof</b><p>38% closes; the superseded 41% is returned.</p></div></div>
      </div>

      <div>
        <h3 style="font-size:var(--step-1);margin-bottom:4px">Choose a case to scan</h3>
        <p class="hint" style="margin-bottom:12px">Each profile uses prepared stored facts and captured pipeline output. You can review or edit the case data after the scan.</p>
        <div class="grid3">
          ${S.presets.map(p => `<button class="preset" data-preset="${esc(p.id)}" type="button"
              aria-pressed="${S.presetId === p.id}">
            <span class="nm">${esc(p.name)} ${p.recommended ? `<span class="st st-CONFIRMED">recommended</span>` : ""}</span>
            <span class="tl">${esc(p.tagline)}</span>
            <span class="sy">${esc(p.story)}</span></button>`).join("")}
        </div>
      </div>
      <div class="nav">
        <button class="btn" id="begin" type="button" ${S.presetId ? "" : "disabled"}>Run the case scan →</button>
        <a class="btn ghost" href="${esc(guideUrl)}" target="_blank" rel="noopener">Read the full guide ↗</a>
        <span class="hint">${S.presetId ? ((S.presets.find(p => p.id === S.presetId) || {}).start_stage === 3 ? "Starts with the source change, then follows it to verified evidence." : "Starts with the multi-jurisdiction result; case facts remain available in the rail.") : "Choose a case to run."}</span>
      </div>
    </div>`;
}

function stageHolder() {
  const h = S.holder;
  const multi = (name, list, chosen) => `<div class="chips">${list.map(c =>
    `<button class="chip" type="button" data-multi="${name}" data-val="${esc(c)}"
      aria-pressed="${chosen.includes(c)}">${esc(c)}</button>`).join("")}</div>`;

  return `<header>
      <span class="eyebrow">Stage 1 · your register, holder level</span>
      <h2>Who the obligations would belong to</h2>
      <p class="lede">TARA never guesses these. Citizenship and tax residency are what decide whether a whole
      jurisdiction is even in the conversation — a corridor pack is only tried when both of its facts are present.</p>
    </header>
    <div class="stack">
      <div class="card pad stack">
        <div class="grid2">
          <label class="f"><span>Name</span><input type="text" id="f-name" value="${esc(h.name)}"></label>
          <label class="f"><span>Tax residency began</span><input type="date" id="f-since" value="${esc(h.tax_residency_since || "")}">
            <span class="hint">Drives the corridor's one-off FEMA deadline.</span></label>
        </div>
        <div class="f"><span>Citizenships</span>${multi("citizenships", COUNTRIES, h.citizenships)}
          <span class="hint">US citizenship is what puts FBAR/FATCA in scope; Indian citizenship opens the India–Ireland corridor.</span></div>
        <div class="f"><span>Tax residencies</span>${multi("tax_residencies", COUNTRIES, h.tax_residencies)}</div>
        <div class="grid2">
          <label class="f"><span>Residency status used by the Irish packs</span>
            <select id="f-res">${RESIDENCIES.map(r => `<option ${h.holder_residency === r ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>
            <span class="hint">"Ordinarily resident" is the branch that keeps an emigrant in scope.</span></label>
          <label class="f"><span>EEA, Swiss or UK national</span>
            <select id="f-eea"><option value="true" ${h.eea_swiss_uk_national ? "selected" : ""}>Yes</option>
              <option value="false" ${h.eea_swiss_uk_national ? "" : "selected"}>No</option></select>
            <span class="hint">"No" is what makes Irish immigration registration apply at all.</span></label>
        </div>
      </div>
      <div class="nav"><button class="btn ghost" data-goto="0" type="button">← Back</button>
        <button class="btn" data-goto="2" type="button">Holdings →</button></div>
    </div>`;
}

function stageHoldings() {
  const rows = S.holdings.map((hd, i) => `
    <div class="card pad stack" data-holding="${i}">
      <div class="row" style="align-items:center;justify-content:space-between">
        <b class="mono">${esc(hd.holding_id)}</b>
        ${S.holdings.length > 1 ? `<button class="tbtn" data-del="${i}" type="button">Remove</button>` : ""}
      </div>
      <div class="grid2">
        <label class="f"><span>What it is</span>
          <select data-h="${i}" data-k="instrument_type">${INSTRUMENTS.map(([v, l]) =>
            `<option value="${v}" ${hd.instrument_type === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
        <label class="f"><span>Where it is</span>
          <select data-h="${i}" data-k="jurisdiction">${COUNTRIES.map(c =>
            `<option ${hd.jurisdiction === c ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
        <label class="f"><span>Acquired</span>
          <input type="date" data-h="${i}" data-k="acquisition_date" value="${esc(hd.acquisition_date)}"></label>
        <label class="f"><span>Still held?</span>
          <select data-h="${i}" data-k="status">
            <option value="held" ${hd.status === "held" ? "selected" : ""}>Held</option>
            <option value="disposed" ${hd.status === "disposed" ? "selected" : ""}>Disposed</option></select></label>
        ${hd.status === "disposed" ? `
        <label class="f"><span>Disposed on</span>
          <input type="date" data-h="${i}" data-k="disposal_date" value="${esc(hd.disposal_date || "")}"></label>
        <label class="f"><span>Consideration (€)</span>
          <input type="number" data-h="${i}" data-k="disposal_consideration" value="${esc(hd.disposal_consideration || "")}"></label>` : ""}
        ${hd.instrument_type === "immigration_permission" ? `
        <label class="f"><span>IRP registration due</span>
          <input type="date" data-h="${i}" data-k="irp_registration_due_date" value="${esc(hd.irp_registration_due_date || "")}"></label>
        <label class="f"><span>Current IRP expires</span>
          <input type="date" data-h="${i}" data-k="irp_expiry_date" value="${esc(hd.irp_expiry_date || "")}">
          <span class="hint">A real date off the card, not a derived anniversary.</span></label>` : ""}
      </div>
      ${hd.status === "disposed" ? `<p class="hint">The two statutory CGT dates (payment 15 December, return 31 October
        the following year) are filled in from Revenue's own calendar when this reaches the engine — they are stated
        dates, not anniversaries, so TARA's date engine cannot derive them and the register has to carry them.</p>` : ""}
    </div>`).join("");

  return `<header>
      <span class="eyebrow">Stage 2 · your register, holding level</span>
      <h2>What you hold, and where</h2>
      <p class="lede">One row per asset or permission. Instrument type is doing more work than it looks:
      it is the scoping question that correctly drops an Indian shareholding out of Ireland's offshore-fund pack —
      while leaving the corridor free to reach it anyway.</p>
    </header>
    <div class="stack">
      ${rows}
      <div class="row"><button class="btn ghost" id="addHolding" type="button">+ Add a holding</button></div>
      <div class="nav"><button class="btn ghost" data-goto="1" type="button">← Back</button>
        <button class="btn" data-goto="3" type="button">Run the open band →</button></div>
    </div>`;
}

function busyPanel(msg) {
  return `<div class="card pad row" style="align-items:center;gap:10px">
    <span class="spin"></span><span>${esc(msg)}</span></div>`;
}

function errorPanel() {
  if (S.error === "custom") {
    return `<div class="warn"><b>This profile has been edited, and no live engine is reachable.</b>
      Captured replay only covers the four prepared profiles in their original state. Either press <b>Restart</b> and run one as-is,
      or point the page at a deployed engine with <b>Engine…</b> to run anything you like.</div>`;
  }
  return `<div class="warn">${esc(S.error)}</div>`;
}

function diffHtml(text) {
  return `<div class="diff">${String(text).split("\n").map(l => {
    const cls = l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@") ? "at" : "";
    return `<div class="${cls}">${esc(l)}</div>`;
  }).join("")}</div>`;
}

function stageChart() {
  if (S.busy) return `<header><span class="eyebrow">Stage 3 · open band</span><h2>Reading the sources</h2></header>
    ${busyPanel("SURVEY is hashing each source text, LEGEND is decomposing it into cited obligations, ALMANAC is versioning the graph…")}`;
  if (S.error) return `<header><span class="eyebrow">Stage 3 · open band</span><h2>The Chart</h2></header>
    <div class="stack">${errorPanel()}<div class="nav">
      <button class="btn ghost" data-goto="2" type="button">← Back</button>
      <button class="btn" id="retry" type="button">Try again</button></div></div>`;
  if (!S.run) return busyPanel("Starting…");

  const ob = S.run.open_band;
  const totalObl = Object.values(ob).reduce((n, p) => n + p.obligations.length, 0);
  const totalSrc = Object.values(ob).reduce((n, p) => n + p.sources.length, 0);
  const changed = Object.values(ob).flatMap(p => p.sources).filter(s => s.changes.length).length;

  const packs = Object.entries(ob).map(([id, p]) => `
    <div class="card openband pad stack">
      <div>
        <div class="row" style="justify-content:space-between;align-items:baseline">
          <b class="mono">${esc(id)}</b>
          ${p.is_corridor ? `<span class="st st-INDETERMINATE">corridor</span>` : ""}
        </div>
        <p class="hint" style="margin-top:2px">${esc(p.title)}</p>
      </div>
      ${p.sources.map(s => `
        <div class="card pad stack" style="gap:8px">
          <b style="font-size:var(--step--1)">${esc(s.instrument)}</b>
          <dl class="kv">
            <dt>source</dt><dd>${esc(s.source_id)}</dd>
            <dt>reached</dt><dd>${s.reached ? "yes" : "no"} · ${s.stale ? "stale" : "within verification window"}</dd>
            <dt>v1 sha256</dt><dd title="${esc(s.v1_sha256)}">${esc(shortHash(s.v1_sha256))}</dd>
            <dt>v2 sha256</dt><dd title="${esc(s.v2_sha256)}">${esc(shortHash(s.v2_sha256))}</dd>
          </dl>
          ${s.changes.length
            ? s.changes.map(c => `<div><span class="st st-INDETERMINATE">${esc(c.change_type)}</span>
                <b style="font-size:var(--step--1);margin-left:6px">${esc(c.provision)} — ${esc(c.heading)}</b>
                ${diffHtml(c.unified_diff)}</div>`).join("")
            : `<p class="hint">Both snapshots hash identically — nothing in this source changed, and LEGEND re-derives the same obligations.</p>`}
        </div>`).join("")}
      <details><summary class="hint" style="cursor:pointer">${p.obligations.length} obligations catalogued from this source, including historical versions</summary>
        <div style="margin-top:8px">${p.obligations.map(o => `
          <div class="oblig"><div class="head">
            <span class="id">${esc(o.obligation_id)}</span>
            <span class="prov">${esc(o.provision)}</span>
            <span class="st st-${o.change_type === "amended" ? "INDETERMINATE" : "EXEMPT"}">${esc(o.change_type)}</span>
            <span class="prov">${esc(o.severity)} · evidence: ${esc(o.artefact_type)}</span>
          </div><p class="txt">${esc(o.text)}</p></div>`).join("")}</div>
      </details>
    </div>`).join("");

  return `<header>
      <span class="eyebrow">Stage 3 · open band · SURVEY → LEGEND → ALMANAC</span>
      <h2>The Chart, before anyone's name is on it</h2>
      <p class="lede">This is computed once and is identical for every holder — which is exactly why it can be free.
      Nothing below knows who you are yet.</p>
    </header>
    <div class="stack">
      <div class="grid3">
        <div class="tile"><div class="n">${Object.keys(ob).length}</div><div class="l">domain packs</div></div>
        <div class="tile"><div class="n">${totalSrc}</div><div class="l">sources hashed</div></div>
        <div class="tile"><div class="n">${totalObl}</div><div class="l">cited obligations</div></div>
        <div class="tile"><div class="n">${changed}</div><div class="l">sources changed since v1</div></div>
      </div>
      <div class="note">Where a source did change, SURVEY reports the provision-level diff and its two SHA-256 digests, and
      LEGEND marks the new obligation <b>amended</b> while ALMANAC marks the one it replaces superseded. That is the
      mechanical version of "change to action": nothing downstream has to be told the rate moved.</div>
      ${packs}
      <div class="nav"><button class="btn ghost" data-goto="2" type="button">← Back</button>
        <button class="btn" data-goto="4" type="button">Now make it about you →</button></div>
    </div>`;
}

function stageSurvey() {
  if (!S.run) return busyPanel("MERIDIAN is checking every country pack and every eligible cross-border corridor in parallel…");
  const hids = Object.keys(S.run.holdings);
  const packs = S.run.packs;
  const allResults = Object.values(S.run.holdings).flatMap(h => h.results);
  const confirmedRows = allResults.filter(r => r.determination && r.determination.status === "CONFIRMED");
  const corridors = corridorSummary();
  const activeCorridors = corridors.filter(r => r.considered && r.determination && r.determination.status === "CONFIRMED");
  const actionableCorridors = activeCorridors.filter(r => r.actions && r.actions.length);
  const unresolved = S.run.pending_questions.length;
  const primaryFinding = actionableCorridors[0];

  const head = `<tr><th>Holding</th>${packs.map(p =>
    `<th class="${p.is_corridor ? "corr" : ""}" title="${esc(p.title)}">${esc(p.domain_id)}${p.is_corridor ? " ◇" : ""}</th>`).join("")}</tr>`;

  const body = hids.map(hid => {
    const H = S.run.holdings[hid];
    return `<tr><th scope="row"><span class="hid">${esc(hid)}</span>
      <span class="kind">${esc(titleCase(H.holding.instrument_type))} · ${esc(H.holding.jurisdiction)}</span></th>
      ${packs.map(p => {
        const r = H.results.find(x => x.domain_id === p.domain_id);
        const st = r.determination ? r.determination.status : "SKIPPED";
        const sel = S.cell && S.cell.hid === hid && S.cell.domain_id === p.domain_id;
        return `<td><button class="cell" type="button" data-cell="${esc(hid)}|${esc(p.domain_id)}" aria-pressed="${!!sel}">
          <span class="st st-${st}">${st}</span>
          ${r.actions.length ? `<span class="acts">${r.actions.length} action${r.actions.length > 1 ? "s" : ""}</span>` : ""}
        </button></td>`;
      }).join("")}</tr>`;
  }).join("");

  let detail = `<div class="note">Click any cell to read the exact reason the agents gave. A dashed
    <b>skipped</b> means the corridor was checked against your facts and ruled out before it was run at all —
    not silently ignored.</div>`;
  if (S.cell) {
    const H = S.run.holdings[S.cell.hid];
    const r = H.results.find(x => x.domain_id === S.cell.domain_id);
    const det = r.determination;
    detail = `<div class="detail stack" style="gap:10px">
      <div><h4>${esc(S.cell.hid)} × ${esc(r.domain_id)}</h4>
        <p class="hint">${esc(r.title)}</p></div>
      <div class="row" style="gap:8px;align-items:center">
        <span class="st st-${det ? det.status : "SKIPPED"}">${det ? det.status : "SKIPPED"}</span>
        ${det && det.relied_on ? `<span class="hint">turned on <code>${esc(det.relied_on)}</code></span>` : ""}
      </div>
      <p class="reason">${esc(det ? det.reason : r.skipped_reason)}</p>
      ${r.gaps.length ? `<div><b style="font-size:var(--step--1)">What PLOT decided for each obligation</b>
        ${r.gaps.map(g => `<div class="oblig"><div class="head">
          <span class="id">${esc(g.obligation_id)}</span><span class="prov">${esc(g.provision)}</span>
          <span class="st st-${g.coverage === "not_applicable" ? "EXEMPT" : "INDETERMINATE"}">${esc(g.coverage)}</span>
          ${g.trigger_date ? `<span class="prov">triggered ${esc(g.trigger_date)}</span>` : ""}
        </div><p class="txt">${esc(g.reason)}</p></div>`).join("")}</div>` : ""}
    </div>`;
  }

  const confirmed = confirmedRows.length;
  const cells = hids.length * packs.length;

  return `<header>
      <span class="eyebrow">Stage 4 · MERIDIAN · one tenant pass per jurisdiction</span>
      <h2>The result of a parallel scan</h2>
      <p class="lede">${hids.length} asset${hids.length > 1 ? "s" : ""} × ${packs.length} packs = ${cells} cited determinations.
      TARA checks the individual country packs and every eligible cross-border corridor against the same case facts.</p>
    </header>
    <div class="stack">
      <div class="scan-hero card pad stack">
        <div class="scan-stats">
          <div><b>${cells}</b><span>checks completed</span></div>
          <div><b>${corridors.length}</b><span>corridors tested</span></div>
          <div><b>${actionableCorridors.length}</b><span>cross-border finding${actionableCorridors.length === 1 ? "" : "s"}</span></div>
          <div><b>${S.run.actions.length}</b><span>pipeline actions opened</span></div>
        </div>
        ${primaryFinding ? `<div class="finding">
          <span class="st st-CONFIRMED">Cross-border finding</span>
          <div><b>${esc(primaryFinding.title)}</b>
            <p>${esc(primaryFinding.determination.reason)} This is the rule family a single-country check would not surface on its own.</p></div>
          <button class="btn" data-goto="6" type="button">Open the Playbook →</button>
        </div>` : `<div class="finding muted">
          <span class="st st-EXEMPT">No corridor triggered</span>
          <div><b>The scan still ruled every corridor in or out explicitly.</b>
            <p>Open the detailed scan to see the source-backed reasons for each result.</p></div>
        </div>`}
        ${unresolved ? `<div class="note"><b>${unresolved} additional fact${unresolved === 1 ? " is" : "s are"} still needed for a separate rule.</b> It does not block the cross-border finding above; COMPASS will not guess where the register is incomplete.</div>` : ""}
      </div>
      <details class="card matrix-details"><summary><b>See the full ${cells}-cell scan</b><span>Each result is clickable for the agent's reasoning.</span></summary>
        <div class="matrix-wrap"><table class="matrix"><thead>${head}</thead><tbody>${body}</tbody></table></div>
      </details>
      ${S.cell ? detail : `<div class="note"><b>Want the audit trail behind a result?</b> Open the full scan, then select any cell to read the exact reason. A dashed <b>skipped</b> means a corridor was considered and ruled out before a full run — not silently ignored.</div>`}
      <div class="nav"><button class="btn ghost" data-goto="1" type="button">Review case facts</button>
        ${unresolved ? `<button class="btn ghost" data-goto="5" type="button">Answer COMPASS's question</button>` : ""}
        <button class="btn" data-goto="6" type="button">${primaryFinding ? "Open the Playbook →" : "Review actions →"}</button></div>
    </div>`;
}

function stageInterview() {
  if (!S.run) return busyPanel("Waiting…");
  const qs = S.run.pending_questions;
  const answered = Object.keys(S.answers);

  const asked = qs.length ? qs.map(q => `
    <div class="qcard">
      <div class="qh">${esc(q.domain_id)} needs one fact your register does not hold</div>
      <div class="qb">
        <p class="qt">${esc(q.text)}</p>
        <p class="hint">Asked by COMPASS as <code>${esc(q.question_id)}</code> on ${esc(q.holding_id)}.
          Until it is answered that pack stays <b>INDETERMINATE</b> — it will not guess, and it will not
          quietly return EXEMPT.</p>
        <div class="row">
          <button class="btn" data-answer="${esc(q.question_id)}|true" type="button">Yes</button>
          <button class="btn" data-answer="${esc(q.question_id)}|false" type="button">No</button>
        </div>
      </div>
    </div>`).join("") : `<div class="card pad">
      <b>Nothing to ask.</b>
      <p class="hint" style="margin-top:4px">COMPASS answered every scoping question for this profile straight off
      the register. An interview only happens where a pack asks something a register genuinely cannot hold —
      like whether a property was your only or main residence.</p></div>`;

  return `<header>
      <span class="eyebrow">Stage 5 · COMPASS · the interview</span>
      <h2>${qs.length ? "One fact it will not assume" : "It had everything it needed"}</h2>
      <p class="lede">A scoping question with a <code>register_field</code> is answered from your data. One without
      has to be asked. That distinction is declared in the domain pack's YAML, not decided by a model.</p>
    </header>
    <div class="stack">
      ${S.busy ? busyPanel("Re-running the tenant band with your answer…") : asked}
      ${answered.length ? `<div class="note">Answered so far: ${answered.map(k =>
        `<code>${esc(k)} = ${esc(String(S.answers[k]))}</code>`).join(", ")}. Each answer re-runs COMPASS, PLOT and
        COURSE from scratch — nothing is patched in place.</div>` : ""}
      <div class="nav"><button class="btn ghost" data-goto="4" type="button">← Back to the survey</button>
        <button class="btn" data-goto="6" type="button">See what is owed →</button></div>
    </div>`;
}

// ---------------------------------------------------------------------------
// the Playbook: obligation -> source link -> numbered steps -> checklist
// ---------------------------------------------------------------------------

// Every field the Playbook renders — the citation, the source URL, the step
// text, the deadline, the suggested figures — is read straight off S.run.
// Nothing here computes a determination, a rate or a deadline; it only
// groups and orders what PLOT/COURSE/LEGEND already produced, exactly the
// way stageSurvey and stageChart already do.
function obligationInfo(domainId, obligationId) {
  const pack = S.run.open_band[domainId];
  if (!pack) return null;
  const obligation = (pack.obligations || []).find(o => o.obligation_id === obligationId) || null;
  const source = obligation ? (pack.sources || []).find(s => s.source_id === obligation.source_id) : null;
  return { pack, obligation, source };
}

// A dependency-respecting order within one obligation regime: an action that
// another depends on is always numbered before it, even if the flat,
// globally-deadline-sorted S.run.actions list happened to interleave them.
function topoSteps(actions) {
  const byId = new Map(actions.map(a => [a.obligation_id, a]));
  const seen = new Set(), out = [];
  function visit(a) {
    if (seen.has(a.obligation_id)) return;
    seen.add(a.obligation_id);
    (a.depends_on || []).forEach(dep => { const d = byId.get(dep); if (d) visit(d); });
    out.push(a);
  }
  actions.forEach(visit);
  return out;
}

// Treaty-relief obligations get a callout badge in the card header — this is
// the "flag whether DTAA rules apply" the corridor packs exist to answer.
const TREATY_ARTEFACTS = {
  form_10f_and_trc: "Treaty relief applies — DTAA Form 10F + Tax Residency Certificate",
  form_1116_ftc_claim: "Treaty relief applies — US Foreign Tax Credit, IRS Form 1116"
};

// The one-line "small calculation" the Irish case asked for by name: whatever
// figure PLOT/ANCHOR's suggested submission already carries for this step,
// shown before the holder ever reaches the Evidence stage to submit it.
function calcLine(a, domainId) {
  const sa = a.suggested_artefact || {};
  if (sa.computed_tax == null) return "";
  const currency = domainId === "india-nri-securities" ? "INR" : undefined;
  const bits = [];
  if (sa.chargeable_gain != null) bits.push(`gain ${money(sa.chargeable_gain, currency)}`);
  if (sa.annual_exemption_applied != null) bits.push(`− exemption ${money(sa.annual_exemption_applied, currency)}`);
  if (sa.rate_applied != null) bits.push(`× ${(sa.rate_applied * 100).toFixed(1)}%`);
  if (sa.gain_type) bits.push(esc(titleCase(sa.gain_type)) + " gain");
  return `<div class="calc">Estimated: ${money(sa.computed_tax, currency)}${bits.length ? " — " + bits.join(" ") : ""}
    <span class="hint">· refine and submit this on the Evidence stage</span></div>`;
}

// One row per cross-border corridor pack this holder was checked against —
// "you have to flag what applies, what doesn't apply" — covering every pair
// of the three countries this build loads (India-Ireland, India-US,
// Ireland-US), whichever holding first carries the determination.
function corridorSummary() {
  const seen = new Map();
  Object.values(S.run.holdings).forEach(h => {
    h.results.forEach(r => { if (r.is_corridor && !seen.has(r.domain_id)) seen.set(r.domain_id, r); });
  });
  return [...seen.values()];
}

function corridorRow(r) {
  const st = r.considered ? (r.determination ? r.determination.status : "INDETERMINATE") : "SKIPPED";
  const reason = r.considered ? (r.determination ? r.determination.reason : "") : r.skipped_reason;
  const label = st === "CONFIRMED" && r.actions && r.actions.length ? "action triggered"
    : st === "CONFIRMED" ? "in scope; no action"
    : st === "EXEMPT" ? "does not apply"
    : st === "SKIPPED" ? "not applicable" : "needs an answer";
  return `<div class="crow">
    <span class="cn">${esc(r.title)}</span>
    <span class="st st-${esc(st)}">${esc(label)}</span>
    <span class="hint">${esc(reason)}</span>
  </div>`;
}

function stageActions() {
  if (!S.run) return busyPanel("Waiting…");
  const acts = S.run.actions;

  // A legal duty can be triggered by several holdings. The pitch view shows
  // that duty once, names every affected holding, and preserves the individual
  // actions for ANCHOR. This stops one corridor rule from becoming three
  // visually identical cards before a judge gets to the actual finding.
  const groups = new Map();
  acts.forEach(a => {
    if (!groups.has(a.domain_id)) groups.set(a.domain_id, []);
    groups.get(a.domain_id).push(a);
  });
  const uniqueObligationCount = new Set(acts.map(a => a.domain_id + "|" + a.obligation_id)).size;

  const cards = [...groups.entries()].map(([domainId, groupActs]) => {
    const pack = S.run.open_band[domainId] || {};
    const byObligation = new Map();
    groupActs.forEach(a => {
      if (!byObligation.has(a.obligation_id)) byObligation.set(a.obligation_id, a);
    });
    const ordered = topoSteps([...byObligation.values()]);
    const affectedHoldings = [...new Set(groupActs.map(a => a.holding_id))];
    const treatyBadges = new Set();
    let primarySource = null;

    const stepsHtml = ordered.map((a, i) => {
      const info = obligationInfo(domainId, a.obligation_id);
      if (info && info.source && !primarySource) primarySource = info.source;
      if (info && info.obligation && TREATY_ARTEFACTS[info.obligation.artefact_type]) {
        treatyBadges.add(TREATY_ARTEFACTS[info.obligation.artefact_type]);
      }
      const actionId = a.action_id;
      const checked = isChecked(actionId, a.obligation_id);
      const assumed = !Object.prototype.hasOwnProperty.call(S.checklist, actionId)
        && assumedObligationIds().includes(a.obligation_id);
      const appliesTo = [...new Set(groupActs.filter(x => x.obligation_id === a.obligation_id).map(x => x.holding_id))];
      return `<div class="step${checked ? " done" : ""}">
        <span class="stepnum">${i + 1}</span>
        <div>
          <div class="stitle">${esc(a.obligation_id)}${a.provision ? " · " + esc(a.provision) : ""}</div>
          <p class="action-meta">Engine-supplied action date: <code>${esc(a.deadline || "no date published")}</code>
            ${a.deadline ? ` · derived ${esc(a.deadline_direction || "before")} the configured event` : ""}
            ${appliesTo.length > 1 ? ` · applies to <code>${esc(appliesTo.join(", "))}</code>` : ""}</p>
          <p class="stxt">${esc(info && info.obligation ? info.obligation.text : "")}</p>
          <p class="hint">Evidence required: <code>${esc(a.artefact_type || a.required_evidence_type)}</code>
            ${info && info.source ? ` · <a href="${esc(info.source.url)}" target="_blank" rel="noopener">Read the source →</a>` : ""}</p>
          ${calcLine(a, domainId)}
          <label class="checkline"><input type="checkbox" data-check="${esc(actionId)}" ${checked ? "checked" : ""}>
            Already in place${assumed ? ` <span class="assumed">(assumed from her profile — uncheck if not yet done)</span>` : ""}</label>
        </div>
      </div>`;
    }).join("");

    return `<div class="card pad stack playbook-card">
      <div class="phead">
        <div>
          <span class="ptitle">${esc(pack.title || domainId)}</span>
          <span class="hint"> · ${esc(affectedHoldings.join(", "))}</span>
        </div>
        <div class="row" style="gap:6px">
          ${pack.is_corridor ? `<span class="st st-INDETERMINATE">corridor</span>` : ""}
          ${[...treatyBadges].map(b => `<span class="chip" style="cursor:default">${esc(b)}</span>`).join("")}
        </div>
      </div>
      ${primarySource ? `<p class="hint">Obligation: <a href="${esc(primarySource.url)}" target="_blank" rel="noopener">${esc(primarySource.instrument)} →</a></p>` : ""}
      ${affectedHoldings.length > 1 ? `<p class="note compact"><b>Consolidated for the walkthrough.</b> The same legal duty was triggered for ${esc(affectedHoldings.join(", "))}; each underlying action remains individually available in the evidence check.</p>` : ""}
      <div class="steps">${stepsHtml}</div>
    </div>`;
  }).join("");

  const corridors = corridorSummary();
  const corridorPanel = corridors.length ? `<div class="card pad">
      <b style="font-size:var(--step--1)">Cross-border corridors checked</b>
      <p class="hint" style="margin:2px 0 4px">Every pair this build loads — India-Ireland, India-US, Ireland-US —
      checked against this holder's own citizenships and tax residencies, whether or not it ends up applying.</p>
      ${corridors.map(corridorRow).join("")}
    </div>` : "";

  const assumption = PLAYBOOK_ASSUMPTIONS[S.presetId];

  return `<header>
      <span class="eyebrow">Stage 6 · PLOT → COURSE · the playbook</span>
      <h2>${acts.length ? `A concrete plan, not a compliance verdict`
        : "Nothing is outstanding"}</h2>
      <p class="lede">${acts.length
        ? `Each card below is a source-backed obligation the case is confirmed in scope for: the citation, the steps
           in order, a concrete action date, and a checklist for what is already in place. Nothing here is computed
           by this page — every figure, date and citation came from the agents in the earlier stages.`
        : `Every pack ruled this holder out, and each said why with a citation — which is a real answer, not a
           failure to find one. Go back to stage 4 to read the reasons, or to stage 5 to answer COMPASS differently.`}</p>
    </header>
    <div class="stack">
      <div class="grid3">
        <div class="tile"><div class="n">${uniqueObligationCount}</div><div class="l">source obligations</div></div>
        <div class="tile"><div class="n">${groups.size}</div><div class="l">Playbooks to work through</div></div>
        <div class="tile"><div class="n">${acts.length}</div><div class="l">underlying actions tracked</div></div>
      </div>
      ${assumption ? `<div class="note"><b>Assumptions this profile makes:</b> ${esc(assumption.note)}</div>` : ""}
      ${corridorPanel}
      ${cards || `<div class="card pad"><b>No open actions.</b><p class="hint" style="margin-top:4px">
        Every pack either ruled this holder out with a citation, or is still waiting on an answer at stage 5.</p></div>`}
      <details class="note"><summary style="cursor:pointer"><b>How action dates are derived</b></summary>
        <p style="margin-top:8px">Each evidence rule declares whether its action date falls <b>before</b>, <b>on</b>, or
        <b>after</b> the configured event only when the source supplies a fixed period. Qualitative timing such as
        “within a reasonable period” stays undated and is escalated for manual scheduling. A missing event date produces
        an indeterminate result, not an invented deadline.</p>
      </details>
      <div class="nav"><button class="btn ghost" data-goto="4" type="button">← Back to scan</button>
        <button class="btn" data-goto="7" type="button" ${acts.length ? "" : "disabled"}>Submit evidence →</button></div>
    </div>`;
}

function currentAction() {
  return (S.run && S.run.actions || []).find(a => a.action_id === S.actionId) || null;
}

function selectAction(id) {
  S.actionId = id;
  S.closure = null;
  S.verification = null;
  S.error = null;
  const a = currentAction();
  S.artefact = a ? JSON.parse(JSON.stringify(a.suggested_artefact)) : null;
}

function stageEvidence() {
  if (!S.run) return busyPanel("Waiting…");
  const acts = S.run.actions;
  if (!acts.length) return `<header><span class="eyebrow">Stage 7 · ANCHOR</span>
    <h2>Nothing outstanding to evidence</h2></header>
    <div class="stack"><div class="card pad">Go back to stage 5 and answer COMPASS's question to open some actions.</div>
    <div class="nav"><button class="btn ghost" data-goto="6" type="button">← Back</button>
    <button class="btn" data-goto="8" type="button">The ledger →</button></div></div>`;

  if (!S.actionId) {
    // open on an action ANCHOR can reject on the rate — that check is the
    // point of this stage, and it only exists on some obligations
    const best = acts.find(x => x.expected_rate != null) || acts[0];
    selectAction(best.action_id);
  }
  const a = currentAction();

  const fields = Object.keys(S.artefact).filter(k => k !== "artefact_type").map(k => {
    const v = S.artefact[k];
    const isNum = typeof v === "number";
    const isDate = /_date$/.test(k) && /^\d{4}-\d{2}-\d{2}$/.test(String(v));
    const req = (a.required_fields || []).includes(k);
    return `<label class="f"><span>${esc(k)}${req ? "" : ' <span class="hint">(extra)</span>'}</span>
      <input class="mono" type="${isDate ? "date" : isNum ? "number" : "text"}"
        ${isNum ? 'step="any"' : ""} data-art="${esc(k)}" value="${esc(v)}"></label>`;
  }).join("");

  const variants = Object.entries(a.variants || {}).map(([k, v]) =>
    `<button class="chip" type="button" data-variant="${esc(k)}">${esc(v.label)}</button>`).join("");

  const result = S.closure ? `
    <div class="detail stack" style="gap:8px;border-left-color:${S.closure.outcome === "closed" ? "var(--verdigris)" : "var(--magenta)"}">
      <div class="row" style="align-items:center;gap:10px">
        <span class="st st-${esc(S.closure.outcome)}">${S.closure.outcome === "closed" ? "closed" : "returned"}</span>
        <b>${esc(S.closure.obligation_id)}</b>
      </div>
      <p class="reason">${esc(S.closure.reason)}</p>
      ${S.closure.trigger_date ? `<p class="hint">Checked against trigger date ${esc(S.closure.trigger_date)}.</p>` : ""}
    </div>` : "";

  const uncaptured = S.error === "uncaptured" ? `<div class="warn">
    <b>That exact submission was not captured.</b> Replay holds the valid submission and the three specific ways of
    breaking it offered above. Use one of those chips, or connect a live engine to verify anything you like.</div>` : "";

  return `<header>
      <span class="eyebrow">Stage 7 · ANCHOR · the part that says no</span>
      <h2>Submit the proof and see whether it holds</h2>
      <p class="lede">ANCHOR checks the artefact type, every required field, the rate the current provision demands,
      and — where the operands are present — that the arithmetic is <i>exactly</i> right. Approximately correct is
      not correct.</p>
    </header>
    <div class="stack">
      <label class="f" style="max-width:640px"><span>Which action are you closing?</span>
        <select id="actionPick">${acts.map(x => `<option value="${esc(x.action_id)}" ${x.action_id === S.actionId ? "selected" : ""}>
          ${esc(x.obligation_id)} — ${esc(x.holding_id || "case")} · ${esc(x.domain_id)} · due ${esc(x.deadline || "n/a")}</option>`).join("")}</select></label>

      <div class="card pad stack">
        <dl class="kv"><dt>artefact_type</dt><dd>${esc(S.artefact.artefact_type)}</dd>
          <dt>required</dt><dd>${esc((a.required_fields || []).join(", ") || "—")}</dd>
          ${a.expected_rate != null ? `<dt>rate demanded</dt><dd>${(a.expected_rate * 100).toFixed(0)}%</dd>` : ""}</dl>
        <div class="grid2">${fields}</div>
        <div>
          <p class="hint" style="margin-bottom:6px">Prefilled with a submission that satisfies the rule. Try breaking it:</p>
          <div class="chips">${variants}</div>
        </div>
        <div class="row" style="align-items:center;gap:12px">
          <button class="btn" id="submitEvidence" type="button" ${S.busy ? "disabled" : ""}>Submit to ANCHOR</button>
          ${S.busy ? `<span class="spin"></span>` : ""}
        </div>
      </div>
      ${uncaptured}
      ${S.error && S.error !== "uncaptured" ? errorPanel() : ""}
      ${result}
      <div class="nav"><button class="btn ghost" data-goto="6" type="button">← Back</button>
        <button class="btn" data-goto="8" type="button">The ledger →</button></div>
    </div>`;
}

function stageLedger() {
  if (!S.run) return busyPanel("Waiting…");
  const at = S.run.atlas;
  const verification = S.verification;
  return `<header>
      <span class="eyebrow">Stage 8 · ATLAS · append-only, hash-chained</span>
      <h2>Trace this demo run</h2>
      <p class="lede">The pipeline records the source-to-action steps in a hash-linked order. The latest ANCHOR check is shown separately below so the demo does not pretend two server-side runs are one durable production ledger.</p>
    </header>
    <div class="stack">
      <div class="grid3">
        <div class="tile"><div class="n">${at.entry_count}</div><div class="l">pipeline entries this run</div></div>
        <div class="tile"><div class="n" style="color:${at.chain_verified ? "var(--verdigris)" : "var(--magenta)"}">${at.chain_verified ? "verified" : "broken"}</div><div class="l">chain integrity</div></div>
        <div class="tile"><div class="n">${at.agents_seen.length}</div><div class="l">agents that wrote</div></div>
      </div>
      <div><p class="hint" style="margin-bottom:6px">Last ${at.tail.length} entries, newest at the bottom:</p>
        <div class="ledger">${at.tail.map(e => `<div>
          <span class="ag">${esc(e.agent)}</span>
          <span class="sp">${esc(e.step)}${e.obligation_id ? " · " + esc(e.obligation_id) : ""}${e.tenant_id ? " · " + esc(e.tenant_id) : ""}</span>
        </div>`).join("")}</div></div>
      <div class="note">Agents that wrote during this run: ${at.agents_seen.map(x => `<code>${esc(x)}</code>`).join(" ")}.
        The open band appears here as well as the tenant band — TARA records what it read, not only what it decided.</div>
      ${verification ? `<div class="card pad stack">
        <div class="row" style="align-items:center;gap:10px"><span class="st st-${S.closure && S.closure.outcome === "closed" ? "closed" : "returned"}">latest ANCHOR check</span>
          <b>${verification.entries_added || 0} evidence event${verification.entries_added === 1 ? "" : "s"} returned</b>
          <span class="hint">server trace ${verification.chain_verified ? "verified" : "not verified"}</span></div>
        <div class="ledger">${(verification.tail || []).map(e => `<div>
          <span class="ag">${esc(e.agent)}</span>
          <span class="sp">${esc(e.step)}${e.obligation_id ? " · " + esc(e.obligation_id) : ""}${e.tenant_id ? " · " + esc(e.tenant_id) : ""}</span>
        </div>`).join("")}</div>
        <p class="hint">The verification API rebuilds the case server-side before checking the submission. Its trace is kept separate from the original scan rather than merged into a claim of durable, shared audit storage.</p>
      </div>` : ""}
      <div class="card pad stack">
        <h3 style="font-size:var(--step-1)">That is the whole loop</h3>
        <p class="lede" style="font-size:var(--step-0)">Source text → cited obligation → does it apply to you → what is
        missing → what to do and by when → is your proof good enough → an inspectable trace of the sequence. Adding an
        approved regime begins with a YAML pack and source snapshots; it also requires domain review and regression
        tests before it belongs in a real workflow.</p>
        <div class="row"><button class="btn" id="again" type="button">Run someone else</button>
          <button class="btn ghost" data-goto="4" type="button">Back to the survey</button></div>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// render + events
// ---------------------------------------------------------------------------
const STAGES = [stageBrief, stageHolder, stageHoldings, stageChart, stageSurvey,
                stageInterview, stageActions, stageEvidence, stageLedger];

function render() {
  renderChrome();
  $("#stage").innerHTML = STAGES[S.leg]();
}

function applyPreset(id) {
  const p = S.presets.find(x => x.id === id);
  if (!p) return;
  S.presetId = id;
  S.holder = JSON.parse(JSON.stringify(p.holder));
  S.holdings = JSON.parse(JSON.stringify(p.holdings));
  S.answers = JSON.parse(JSON.stringify(p.answers || {}));
  S.run = null; S.cell = null; S.actionId = null;
  S.closure = null; S.verification = null; S.artefact = null; S.error = null; S.checklist = {};
}

function assumedObligationIds() {
  const a = PLAYBOOK_ASSUMPTIONS[S.presetId];
  return a ? a.obligation_ids : [];
}

function isChecked(actionId, obligationId) {
  if (Object.prototype.hasOwnProperty.call(S.checklist, actionId)) return S.checklist[actionId];
  return assumedObligationIds().includes(obligationId);
}

document.addEventListener("click", async ev => {
  const t = ev.target.closest("[data-leg],[data-goto],[data-preset],[data-multi],[data-del],[data-cell],[data-answer],[data-variant],button");
  if (!t) return;

  if (t.dataset.leg !== undefined) { if (legEnabled(+t.dataset.leg)) go(+t.dataset.leg); return; }
  if (t.dataset.goto !== undefined) { go(+t.dataset.goto); return; }
  if (t.dataset.preset) { applyPreset(t.dataset.preset); render(); return; }
  if (t.id === "begin") {
    const p = S.presets.find(x => x.id === S.presetId);
    go(p && p.start_stage === 3 ? 3 : 4);
    return;
  }
  if (t.id === "retry") { S.run = null; doRun(); return; }
  if (t.id === "again") { S.presetId = null; S.run = null; S.verification = null; go(0); return; }
  if (t.id === "btnRestart") { S.presetId = null; S.holder = null; S.holdings = []; S.run = null;
    S.answers = {}; S.closure = null; S.verification = null; S.actionId = null; go(0); return; }

  if (t.id === "btnEngine") {
    const url = prompt(
      "Engine URL for the live TARA API (leave empty to force captured replay):\n\n" +
      "e.g. https://tara-demo.onrender.com", S.api || "");
    if (url === null) return;
    S.api = url.trim().replace(/\/+$/, "");
    try { localStorage.setItem(LS_KEY, S.api); } catch (e) {}
    S.mode = "checking"; render();
    await detectEngine(); await loadPresets();
    S.run = null; S.verification = null; render();
    return;
  }

  if (t.dataset.multi) {
    const k = t.dataset.multi, v = t.dataset.val, list = S.holder[k];
    const i = list.indexOf(v);
    if (i >= 0) list.splice(i, 1); else list.push(v);
    S.run = null; render(); return;
  }
  if (t.dataset.del !== undefined) { S.holdings.splice(+t.dataset.del, 1); S.run = null; render(); return; }
  if (t.id === "addHolding") {
    const n = S.holdings.length + 1;
    S.holdings.push({ holding_id: "HLD-" + String(900 + n), instrument_type: "offshore_fund",
      jurisdiction: "Ireland", acquisition_date: "2018-01-01", status: "held" });
    S.run = null; render(); return;
  }
  if (t.dataset.cell) {
    const [hid, domain_id] = t.dataset.cell.split("|");
    S.cell = (S.cell && S.cell.hid === hid && S.cell.domain_id === domain_id) ? null : { hid, domain_id };
    render(); return;
  }
  if (t.dataset.answer) {
    const [qid, val] = t.dataset.answer.split("|");
    S.answers[qid] = val === "true";
    S.cell = null; S.actionId = null; S.closure = null; S.verification = null;
    await doRun();
    return;
  }
  if (t.dataset.variant) {
    const v = (currentAction().variants || {})[t.dataset.variant];
    if (v) S.artefact = JSON.parse(JSON.stringify(v.artefact));
    S.closure = null; S.verification = null; S.error = null; render(); return;
  }
  if (t.id === "submitEvidence") { await doVerify(S.artefact); return; }
});

document.addEventListener("change", ev => {
  const t = ev.target;
  if (t.dataset.check !== undefined) { S.checklist[t.dataset.check] = t.checked; render(); return; }
  if (t.id === "actionPick") { selectAction(t.value); render(); return; }
  if (t.dataset.art !== undefined) {
    const k = t.dataset.art;
    S.artefact[k] = t.type === "number" ? (t.value === "" ? "" : Number(t.value)) : t.value;
    S.closure = null; S.verification = null; S.error = null; return;
  }
  if (t.dataset.h !== undefined) {
    const h = S.holdings[+t.dataset.h], k = t.dataset.k;
    h[k] = t.type === "number" ? (t.value === "" ? null : Number(t.value)) : t.value;
    S.run = null;
    if (k === "status" || k === "instrument_type") render();
    return;
  }
  if (t.id === "f-name") { S.holder.name = t.value; S.run = null; return; }
  if (t.id === "f-since") { S.holder.tax_residency_since = t.value; S.run = null; return; }
  if (t.id === "f-res") { S.holder.holder_residency = t.value; S.run = null; return; }
  if (t.id === "f-eea") { S.holder.eea_swiss_uk_national = t.value === "true"; S.run = null; return; }
});

document.addEventListener("keydown", ev => {
  if (ev.target.matches("input,select,textarea")) return;
  if (ev.key === "ArrowRight" && legEnabled(S.leg + 1) && S.leg < STAGES.length - 1) go(S.leg + 1);
  if (ev.key === "ArrowLeft" && S.leg > 0) go(S.leg - 1);
});

(async function boot() {
  render();
  await detectEngine();
  await loadPresets();
  render();
})();
})();
