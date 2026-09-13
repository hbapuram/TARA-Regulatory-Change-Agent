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
    note: "Assumed already done, per Priya's own account of her situation: her Indian bank accounts have already been changed to the appropriate non-resident account status, and she has already declared herself a Non-Resident Indian in her Indian tax filings. Uncheck any step below that is not actually done yet."
  }
};

const FALLBACK_PRESETS = [{
  id:"maeve", name:"Maeve", recommended:true, start_stage:3,
  tagline:"Recommended: see one tax-rate change become a clear action plan",
  story:"Maeve holds an offshore fund. The tax rate changes from 41% to 38%, so TARA works out which rate applies, what she needs to do, and whether her calculation is correct.",
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
      : "The evidence checker could not be reached: " + e.message;
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

const STATUS_LABELS = {
  CONFIRMED: "Applies",
  EXEMPT: "Does not apply",
  INDETERMINATE: "More information needed",
  SKIPPED: "Not relevant",
  closed: "Accepted",
  returned: "Needs correction"
};

const DOMAIN_LABELS = {
  tax: "Irish offshore fund tax",
  "ireland-cgt-property": "Irish property sale tax",
  "ireland-irp": "Irish residence permission",
  "india-fa": "Indian foreign asset reporting",
  "india-nri-securities": "Indian investment gains",
  "us-fbar": "US foreign account reporting",
  "india-ireland-corridor": "India and Ireland tax connection",
  "india-us-corridor": "India and US tax connection",
  "ireland-us-corridor": "Ireland and US tax connection"
};

const EVIDENCE_LABELS = {
  deemed_disposal_computation: "Eight-year gain calculation",
  valuation_statement: "Valuation statement",
  tax_computation: "Tax calculation",
  filed_return_receipt: "Filed return and payment receipt",
  cgt_computation: "Capital gains calculation",
  ppr_relief_computation: "Main-home relief calculation",
  cgt_payment_receipt: "Tax payment receipt",
  filed_cgt_return: "Filed capital gains return",
  cg50a_clearance_certificate: "Property tax clearance certificate",
  irp_initial_registration: "Residence registration confirmation",
  irp_renewal: "Residence permission renewal",
  irp_change_of_address_notification: "Address-change confirmation",
  schedule_fa_disclosure: "Foreign assets disclosure",
  schedule_fsi_disclosure: "Foreign income disclosure",
  nri_capital_gains_computation: "Indian investment gain calculation",
  tds_certificate: "Tax deducted at source certificate",
  filed_itr_return: "Filed Indian tax return",
  nro_redesignation_confirmation: "Indian bank account status confirmation",
  form_10f_and_trc: "Form 10F and tax residency certificate",
  form_67_ftc_claim: "Foreign tax credit claim",
  fbar_filing: "US foreign bank account report",
  form_8938_filing: "US foreign asset report",
  form_3520_filing: "US foreign trust or gift report",
  form_8621_filing: "US foreign investment company report",
  form_1116_ftc_claim: "US foreign tax credit claim",
  ftc_substantiation_record: "Foreign tax credit supporting record"
};

const FIELD_LABELS = {
  valuation_date: "Valuation date",
  computed_gain: "Calculated gain",
  deemed_gain: "Deemed gain",
  chargeable_gain: "Chargeable gain",
  annual_exemption_applied: "Annual exemption",
  rate_applied: "Tax rate used",
  computed_tax: "Calculated tax",
  return_date: "Return date",
  tax_paid_amount: "Tax paid",
  reference_number: "Reference number",
  assessment_year: "Assessment year",
  trc_reference: "Tax residency certificate reference",
  redesignation_date: "Account status change date",
  account_type: "Account type"
};

const statusLabel = status => STATUS_LABELS[status] || titleCase(status);
const domainLabel = (id, fallback) => DOMAIN_LABELS[id] || fallback || titleCase(id);
const evidenceLabel = type => EVIDENCE_LABELS[type] || titleCase(type);
const fieldLabel = key => FIELD_LABELS[key] || titleCase(key);
const formatDate = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))
  ? new Intl.DateTimeFormat("en-IE", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value + "T00:00:00Z"))
  : value;

function holdingLabel(id) {
  const fromRun = S.run && S.run.holdings && S.run.holdings[id] && S.run.holdings[id].holding;
  const h = fromRun || S.holdings.find(x => x.holding_id === id);
  return h ? `${titleCase(h.instrument_type)} in ${h.jurisdiction}` : "Case item";
}

function plainReason(reason) {
  return String(reason || "")
    .replace(/Artefact is responsive and evidence rules are satisfied\.?/gi,
      "The required information is present, and the calculation matches the current rule.")
    .replace(/rate_applied 0\.(\d+) does not match the (\d+)% rate required for [^—]+— submitting evidence at a superseded rate does not satisfy the current obligation\.?/gi,
      (_, submitted, required) => `The submitted ${submitted}% rate is out of date. This case requires the current ${required}% rate.`)
    .replace(/computed_tax ([\d.]+) does not equal the expected ([\d.]+)[^.]*/gi,
      (_, submitted, expected) => `The calculated tax is ${submitted}, but the figures in this form produce ${expected}.`)
    .replace(/missing required field:?\s*([a-z_]+)/gi, (_, key) => `Add the required field: ${fieldLabel(key)}.`)
    .replace(/Holder is within scope on every configured scoping question\.?/gi, "The case facts match this rule.")
    .replace(/Trigger date (\d{4}-\d{2}-\d{2}) has passed with no recorded evidence\.?/gi,
      (_, d) => `The relevant date was ${formatDate(d)}, but no supporting evidence is recorded yet.`)
    .replace(/The event date (\d{4}-\d{2}-\d{2}) is after this rule ceased to apply on (\d{4}-\d{2}-\d{2})\.?/gi,
      (_, event, ended) => `This older rule does not apply: the event is ${formatDate(event)}, after it ended on ${formatDate(ended)}.`)
    .replace(/rate_applied/gi, "tax rate")
    .replace(/computed_tax/gi, "calculated tax")
    .replace(/deemed_gain/gi, "deemed gain")
    .replace(/\bOBL(?:-[A-Z0-9]+)+\b/g, "this requirement")
    .replace(/\bINDETERMINATE\b/g, "waiting for information")
    .replace(/\bEXEMPT\b/g, "not applicable")
    .replace(/_/g, " ");
}

function actionTitle(action, info) {
  const type = action.artefact_type || action.required_evidence_type;
  const labels = {
    deemed_disposal_computation: "Calculate the eight-year deemed gain",
    valuation_statement: "Record the fund valuation",
    tax_computation: action.expected_rate != null ? `Calculate tax using the current ${(action.expected_rate * 100).toFixed(0)}% rate` : "Prepare the tax calculation",
    filed_return_receipt: "File the return and keep the payment receipt",
    cgt_computation: "Calculate the property gain",
    ppr_relief_computation: "Check main-home relief",
    cgt_payment_receipt: "Pay the tax and keep the receipt",
    filed_cgt_return: "File the capital gains return",
    cg50a_clearance_certificate: "Obtain property tax clearance",
    irp_initial_registration: "Complete the first residence registration",
    irp_renewal: "Renew the residence permission",
    irp_change_of_address_notification: "Report the address change",
    schedule_fa_disclosure: "Report foreign assets",
    schedule_fsi_disclosure: "Report foreign income",
    nri_capital_gains_computation: "Calculate the Indian investment gain",
    tds_certificate: "Collect the tax-deduction certificate",
    filed_itr_return: "File the Indian tax return",
    nro_redesignation_confirmation: "Confirm the Indian bank account status",
    form_10f_and_trc: "Prepare treaty-relief documents",
    form_67_ftc_claim: "Claim foreign tax credit",
    fbar_filing: "File the US foreign bank account report",
    form_8938_filing: "File the US foreign asset report",
    form_3520_filing: "File the US foreign trust or gift report",
    form_8621_filing: "File the US foreign investment company report",
    form_1116_ftc_claim: "Claim the US foreign tax credit",
    ftc_substantiation_record: "Keep proof for the foreign tax credit"
  };
  return labels[type] || (info && info.obligation ? info.obligation.text : evidenceLabel(type));
}

function plainVariantLabel(label) {
  return String(label || "")
    .replace("Reset to a valid submission", "Restore the correct example")
    .replace(/Leave rate_applied empty/i, "Remove the tax rate")
    .replace(/Leave return_date empty/i, "Remove the return date")
    .replace(/Leave ([a-z_]+) empty/gi, (_, key) => `Remove ${fieldLabel(key).toLowerCase()}`);
}

const LEGS = [
  { id: "brief",     label: "Start" },
  { id: "holder",    label: "About the person" },
  { id: "holdings",  label: "What they hold" },
  { id: "chart",     label: "What changed" },
  { id: "survey",    label: "What applies" },
  { id: "interview", label: "Missing information" },
  { id: "actions",   label: "Action plan" },
  { id: "evidence",  label: "Check evidence" },
  { id: "ledger",    label: "Proof record" }
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
    S.mode === "live" ? "live calculation" : S.mode === "replay" ? "backup replay" : S.mode === "checking" ? "connecting" : "offline";
  $("#engineEndpoint").textContent =
    S.mode === "live" ? S.api.replace(/^https?:\/\//, "")
    : S.mode === "replay" ? "recorded " + (REPLAY ? REPLAY.captured_at : "") : "";

  $("#passage").innerHTML = LEGS.map((l, i) => {
    const on = i === S.leg, done = i < S.leg && legEnabled(i);
    return `<li><button class="leg${done ? " done" : ""}" data-leg="${i}" ${on ? 'aria-current="true"' : ""}
      ${legEnabled(i) ? "" : "disabled"} type="button">
      <span class="num"><i>${i + 1}</i></span>${esc(l.label)}</button></li>`;
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
      ? `<div class="note"><b>Live calculation is ready.</b> The results in this walkthrough are being generated now from the prepared case.</div>`
      : S.mode === "replay"
      ? `<div class="warn"><b>The live service is unavailable, so TARA has switched to a prepared backup.</b> The backup contains results captured from the same workflow on ${esc(REPLAY ? REPLAY.captured_at : "")}.</div>`
      : `<div class="warn">The calculation service and its backup are unavailable.</div>`;

  return `<header>
      <span class="eyebrow">A regulatory change-to-action prototype</span>
      <h2>A rule changed. TARA makes the next step clear.</h2>
      <p class="lede">Regulatory updates are difficult to read, compare, and apply to a real person. TARA shows what
      changed, who may be affected, what they should do next, and what evidence a human reviewer should check.</p>
    </header>
    <div class="stack">
      ${engineNote}
      <div class="note compact"><b>Prototype boundary:</b> this uses prepared examples and controlled source snapshots. It supports a qualified reviewer; it does not replace legal, tax, immigration, or filing advice.</div>
      <div class="journey" aria-label="Demo journey">
        <div class="journey-step"><span>1</span><div><b>Understand the change</b><p>See the old rule and the new rule side by side.</p></div></div>
        <div class="journey-step"><span>2</span><div><b>Get a clear action plan</b><p>See what applies to this person and what to do next.</p></div></div>
        <div class="journey-step"><span>3</span><div><b>Check the evidence</b><p>Watch TARA reject the old 41% rate and accept 38%.</p></div></div>
      </div>

      <div>
        <h3 style="font-size:var(--step-1);margin-bottom:4px">Choose a prepared example</h3>
        <p class="hint" style="margin-bottom:12px">Start with Maeve for the shortest, clearest walkthrough. The other cases show broader possibilities.</p>
        <div class="grid3">
          ${S.presets.map(p => `<button class="preset" data-preset="${esc(p.id)}" type="button"
              aria-pressed="${S.presetId === p.id}">
            <span class="nm">${esc(p.name)} ${p.recommended ? `<span class="st st-CONFIRMED">recommended</span>` : ""}</span>
            <span class="tl">${esc(p.tagline)}</span>
            <span class="sy">${esc(p.story)}</span></button>`).join("")}
        </div>
      </div>
      <div class="nav">
        <button class="btn" id="begin" type="button" ${S.presetId ? "" : "disabled"}>Start the walkthrough →</button>
        <a class="btn ghost" href="${esc(guideUrl)}" target="_blank" rel="noopener">Open the full project guide ↗</a>
        <span class="hint">${S.presetId ? ((S.presets.find(p => p.id === S.presetId) || {}).start_stage === 3 ? "You will begin with the rule change, then follow it through to accepted evidence." : "You will begin with the result; the case facts remain available in the navigation.") : "Choose a case to continue."}</span>
      </div>
    </div>`;
}

function stageHolder() {
  const h = S.holder;
  const multi = (name, list, chosen) => `<div class="chips">${list.map(c =>
    `<button class="chip" type="button" data-multi="${name}" data-val="${esc(c)}"
      aria-pressed="${chosen.includes(c)}">${esc(c)}</button>`).join("")}</div>`;

  return `<header>
      <span class="eyebrow">Step 2 of 9 · About the person</span>
      <h2>The facts TARA is allowed to use</h2>
      <p class="lede">Citizenship, tax residence, and dates can change which rules apply. TARA uses the facts shown here and asks when something important is missing; it does not fill gaps with guesses.</p>
    </header>
    <div class="stack">
      <div class="card pad stack">
        <div class="grid2">
          <label class="f"><span>Name</span><input type="text" id="f-name" value="${esc(h.name)}"></label>
          <label class="f"><span>Tax residence began</span><input type="date" id="f-since" value="${esc(h.tax_residency_since || "")}">
            <span class="hint">Used only when a rule depends on when tax residence began.</span></label>
        </div>
        <div class="f"><span>Citizenships</span>${multi("citizenships", COUNTRIES, h.citizenships)}
          <span class="hint">Some rules depend on citizenship as well as where a person pays tax.</span></div>
        <div class="f"><span>Countries of tax residence</span>${multi("tax_residencies", COUNTRIES, h.tax_residencies)}</div>
        <div class="grid2">
          <label class="f"><span>Irish tax-residence status</span>
            <select id="f-res">${RESIDENCIES.map(r => `<option ${h.holder_residency === r ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>
            <span class="hint">Some Irish tax rules use this more detailed status.</span></label>
          <label class="f"><span>European Economic Area, Swiss or UK national</span>
            <select id="f-eea"><option value="true" ${h.eea_swiss_uk_national ? "selected" : ""}>Yes</option>
              <option value="false" ${h.eea_swiss_uk_national ? "" : "selected"}>No</option></select>
            <span class="hint">Used to decide whether Irish residence registration may be relevant.</span></label>
        </div>
      </div>
      <div class="nav"><button class="btn ghost" data-goto="0" type="button">← Back</button>
        <button class="btn" data-goto="2" type="button">See what they hold →</button></div>
    </div>`;
}

function stageHoldings() {
  const rows = S.holdings.map((hd, i) => `
    <div class="card pad stack" data-holding="${i}">
      <div class="row" style="align-items:center;justify-content:space-between">
        <b>${esc(titleCase(hd.instrument_type))} in ${esc(hd.jurisdiction)}</b>
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
        <label class="f"><span>Irish residence registration due</span>
          <input type="date" data-h="${i}" data-k="irp_registration_due_date" value="${esc(hd.irp_registration_due_date || "")}"></label>
        <label class="f"><span>Current residence permission expires</span>
          <input type="date" data-h="${i}" data-k="irp_expiry_date" value="${esc(hd.irp_expiry_date || "")}">
          <span class="hint">A real date off the card, not a derived anniversary.</span></label>` : ""}
      </div>
      ${hd.status === "disposed" ? `<p class="hint">Property-sale tax has fixed payment and return dates. TARA keeps those stated dates with the case instead of guessing an anniversary.</p>` : ""}
      <details class="technical-details"><summary>Technical reference</summary><p><code>${esc(hd.holding_id)}</code></p></details>
    </div>`).join("");

  return `<header>
      <span class="eyebrow">Step 3 of 9 · What they hold</span>
      <h2>The assets and permissions that may be affected</h2>
      <p class="lede">TARA checks each item separately because the type of asset, its country, and the event date can lead to different answers.</p>
    </header>
    <div class="stack">
      ${rows}
      <div class="row"><button class="btn ghost" id="addHolding" type="button">+ Add a holding</button></div>
      <div class="nav"><button class="btn ghost" data-goto="1" type="button">← Back</button>
        <button class="btn" data-goto="3" type="button">See what changed →</button></div>
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

function diffSides(text) {
  const lines = String(text || "").split("\n");
  const before = lines.filter(l => l.startsWith("-") && !l.startsWith("---"))
    .map(l => l.slice(1).trim()).join(" ");
  const after = lines.filter(l => l.startsWith("+") && !l.startsWith("+++"))
    .map(l => l.slice(1).trim()).join(" ");
  return { before, after };
}

function stageChart() {
  if (S.busy) return `<header><span class="eyebrow">Step 4 of 9 · What changed</span><h2>Comparing the old and new source</h2></header>
    ${busyPanel("TARA is checking the source snapshots and identifying the exact change…")}`;
  if (S.error) return `<header><span class="eyebrow">Step 4 of 9 · What changed</span><h2>The source comparison</h2></header>
    <div class="stack">${errorPanel()}<div class="nav">
      <button class="btn ghost" data-goto="2" type="button">← Back</button>
      <button class="btn" id="retry" type="button">Try again</button></div></div>`;
  if (!S.run) return busyPanel("Starting…");

  const ob = S.run.open_band;
  const totalObl = Object.values(ob).reduce((n, p) => n + p.obligations.length, 0);
  const totalSrc = Object.values(ob).reduce((n, p) => n + p.sources.length, 0);
  const changed = Object.values(ob).flatMap(p => p.sources).filter(s => s.changes.length).length;

  const changedCards = Object.entries(ob).flatMap(([id, p]) => p.sources.flatMap(s =>
    (s.changes || []).map(c => {
      const sides = diffSides(c.unified_diff);
      return `<article class="card change-card pad stack">
        <div class="row" style="justify-content:space-between;align-items:center">
          <span class="st st-INDETERMINATE">Rule changed</span>
          <a href="${esc(s.url)}" target="_blank" rel="noopener">Open the published source ↗</a>
        </div>
        <div><p class="context-label">${esc(domainLabel(id, p.title))}</p>
          <h3>${esc(c.heading || c.provision)}</h3>
          <p class="hint">${esc(s.instrument)} · ${esc(c.provision)}</p></div>
        <div class="before-after" aria-label="Before and after rule text">
          <div><span>Before</span><p>${esc(sides.before || "See the exact source comparison below.")}</p></div>
          <div><span>Now</span><p>${esc(sides.after || "See the exact source comparison below.")}</p></div>
        </div>
        <div class="plain-summary"><b>Why this matters for this example</b>
          <p>TARA keeps both versions and uses the case's event date to select the right one. For the recommended Maeve walkthrough, the 2026 event selects the current 38% rule rather than the former 41% rule.</p></div>
        <details class="technical-details"><summary>See exact source text and integrity checks</summary>
          ${diffHtml(c.unified_diff)}
          <dl class="kv" style="margin-top:10px">
            <dt>Internal source reference</dt><dd>${esc(s.source_id)}</dd>
            <dt>Earlier snapshot</dt><dd title="${esc(s.v1_sha256)}">${esc(shortHash(s.v1_sha256))}</dd>
            <dt>Current snapshot</dt><dd title="${esc(s.v2_sha256)}">${esc(shortHash(s.v2_sha256))}</dd>
            <dt>Source check</dt><dd>${s.reached ? "Available" : "Unavailable"} · ${s.stale ? "review window expired" : "inside review window"}</dd>
          </dl>
        </details>
      </article>`;
    }))
  ).join("");

  const coverageRows = Object.entries(ob).map(([id, p]) => {
    const sourceChanges = p.sources.reduce((n, s) => n + (s.changes || []).length, 0);
    return `<li><span>${esc(domainLabel(id, p.title))}</span><b>${sourceChanges ? "Change found" : "No change in stored snapshots"}</b></li>`;
  }).join("");

  const technicalCatalogue = Object.entries(ob).map(([id, p]) => `<details class="technical-details">
    <summary>${esc(domainLabel(id, p.title))} · ${p.obligations.length} versioned requirements</summary>
    <div style="margin-top:8px">${p.obligations.map(o => `<div class="oblig"><div class="head">
      <span class="prov">${esc(o.provision)}</span>
      <span class="st st-${o.change_type === "amended" ? "INDETERMINATE" : "EXEMPT"}">${esc(titleCase(o.change_type))}</span>
    </div><p class="txt">${esc(o.text)}</p><p class="technical-ref">Internal reference: <code>${esc(o.obligation_id)}</code> · evidence type <code>${esc(o.artefact_type)}</code></p></div>`).join("")}</div>
  </details>`).join("");

  return `<header>
      <span class="eyebrow">Step 4 of 9 · What changed</span>
      <h2>TARA found the exact rule change</h2>
      <p class="lede">Instead of asking a person to compare long documents, TARA shows the old wording, the new wording, and why the change matters for this example.</p>
    </header>
    <div class="stack">
      <div class="grid3">
        <div class="tile"><div class="n">${changed}</div><div class="l">source change found</div></div>
        <div class="tile"><div class="n">${Object.keys(ob).length}</div><div class="l">rule areas checked</div></div>
        <div class="tile"><div class="n">${totalSrc}</div><div class="l">source sets compared</div></div>
      </div>
      ${changedCards || `<div class="note"><b>No source change was found in the stored snapshots for this example.</b></div>`}
      <details class="card matrix-details"><summary><b>See all ${Object.keys(ob).length} rule areas checked</b><span>Most did not change, so they are kept out of the main story.</span></summary>
        <ul class="coverage-list">${coverageRows}</ul>
      </details>
      <details class="card matrix-details"><summary><b>Technical catalogue</b><span>${totalObl} versioned requirements, references, and evidence types.</span></summary>
        <div class="technical-catalogue">${technicalCatalogue}</div>
      </details>
      <div class="nav"><button class="btn ghost" data-goto="2" type="button">← Back</button>
        <button class="btn" data-goto="4" type="button">See what applies to ${esc(S.holder.name)} →</button></div>
    </div>`;
}

function stageSurvey() {
  if (!S.run) return busyPanel("TARA is checking the case against each relevant rule area…");
  const hids = Object.keys(S.run.holdings);
  const packs = S.run.packs;
  const allResults = Object.values(S.run.holdings).flatMap(h => h.results);
  const confirmedRows = allResults.filter(r => r.determination && r.determination.status === "CONFIRMED");
  const corridors = corridorSummary();
  const activeCorridors = corridors.filter(r => r.considered && r.determination && r.determination.status === "CONFIRMED");
  const actionableCorridors = activeCorridors.filter(r => r.actions && r.actions.length);
  const unresolved = S.run.pending_questions.length;
  const actionableResults = allResults.filter(r => r.actions && r.actions.length);
  const primaryFinding = actionableCorridors[0] || actionableResults[0];
  const primaryAction = primaryFinding && primaryFinding.actions && primaryFinding.actions.find(a => a.expected_rate != null)
    || primaryFinding && primaryFinding.actions && primaryFinding.actions[0];
  const primaryHeadline = primaryAction && primaryAction.expected_rate != null
    ? `The current ${(primaryAction.expected_rate * 100).toFixed(0)}% rule applies`
    : primaryFinding ? domainLabel(primaryFinding.domain_id, primaryFinding.title) : "No action is needed";
  const primaryCopy = primaryAction && primaryAction.expected_rate != null
    ? `The event falls under the newer rule, so the former 41% rate is not used. TARA created ${primaryFinding.actions.length} clear next step${primaryFinding.actions.length === 1 ? "" : "s"}.`
    : primaryFinding ? `${plainReason(primaryFinding.determination && primaryFinding.determination.reason)} TARA created ${primaryFinding.actions.length} next step${primaryFinding.actions.length === 1 ? "" : "s"}.` : "Every checked rule area was ruled out or needs more information.";

  const head = `<tr><th>Holding</th>${packs.map(p =>
    `<th class="${p.is_corridor ? "corr" : ""}" title="${esc(p.title)}">${esc(domainLabel(p.domain_id, p.title))}</th>`).join("")}</tr>`;

  const body = hids.map(hid => {
    const H = S.run.holdings[hid];
    return `<tr><th scope="row"><span class="kind">${esc(titleCase(H.holding.instrument_type))} · ${esc(H.holding.jurisdiction)}</span></th>
      ${packs.map(p => {
        const r = H.results.find(x => x.domain_id === p.domain_id);
        const st = r.determination ? r.determination.status : "SKIPPED";
        const sel = S.cell && S.cell.hid === hid && S.cell.domain_id === p.domain_id;
        return `<td><button class="cell" type="button" data-cell="${esc(hid)}|${esc(p.domain_id)}" aria-pressed="${!!sel}">
          <span class="st st-${st}">${esc(statusLabel(st))}</span>
          ${r.actions.length ? `<span class="acts">${r.actions.length} next step${r.actions.length > 1 ? "s" : ""}</span>` : ""}
        </button></td>`;
      }).join("")}</tr>`;
  }).join("");

  let detail = `<div class="note">Select any result to see why it applies, does not apply, or needs more information. Technical references stay hidden until you ask for them.</div>`;
  if (S.cell) {
    const H = S.run.holdings[S.cell.hid];
    const r = H.results.find(x => x.domain_id === S.cell.domain_id);
    const det = r.determination;
    detail = `<div class="detail stack" style="gap:10px">
      <div><h4>${esc(holdingLabel(S.cell.hid))}</h4>
        <p class="hint">${esc(domainLabel(r.domain_id, r.title))}</p></div>
      <div class="row" style="gap:8px;align-items:center">
        <span class="st st-${det ? det.status : "SKIPPED"}">${esc(statusLabel(det ? det.status : "SKIPPED"))}</span>
      </div>
      <p class="reason">${esc(plainReason(det ? det.reason : r.skipped_reason))}</p>
      ${r.gaps.length ? `<div><b style="font-size:var(--step--1)">How each requirement was handled</b>
        ${r.gaps.map(g => {
          const info = obligationInfo(r.domain_id, g.obligation_id);
          const action = (r.actions || []).find(a => a.obligation_id === g.obligation_id) || { artefact_type: g.artefact_type };
          const gapStatus = g.coverage === "not_applicable" ? "EXEMPT" : g.coverage === "indeterminate" ? "INDETERMINATE" : "CONFIRMED";
          return `<div class="oblig"><div class="head"><b>${esc(actionTitle(action, info))}</b>
            <span class="st st-${gapStatus}">${esc(statusLabel(gapStatus))}</span>
            ${g.trigger_date ? `<span class="prov">Relevant date: ${esc(formatDate(g.trigger_date))}</span>` : ""}
          </div><p class="txt">${esc(plainReason(g.reason))}</p>
          <details class="technical-details"><summary>Technical reference</summary><p><code>${esc(g.obligation_id)}</code> · ${esc(g.provision)}</p></details></div>`;
        }).join("")}</div>` : ""}
      <details class="technical-details"><summary>Decision references</summary><p>Holding <code>${esc(S.cell.hid)}</code> · rule area <code>${esc(r.domain_id)}</code>${det && det.relied_on ? ` · decision question <code>${esc(det.relied_on)}</code>` : ""}</p></details>
    </div>`;
  }

  const confirmed = confirmedRows.length;
  const cells = hids.length * packs.length;

  return `<header>
      <span class="eyebrow">Step 5 of 9 · What applies</span>
      <h2>Here is what TARA found for ${esc(S.holder.name)}</h2>
      <p class="lede">TARA checked ${hids.length} item${hids.length > 1 ? "s" : ""} against ${packs.length} rule areas using the same case facts. The important result appears first; the full check remains available below.</p>
    </header>
    <div class="stack">
      <div class="scan-hero card pad stack">
        <div class="scan-stats">
          <div><b>${cells}</b><span>rule checks completed</span></div>
          <div><b>${confirmed}</b><span>result${confirmed === 1 ? "" : "s"} that appl${confirmed === 1 ? "ies" : "y"}</span></div>
          <div><b>${S.run.actions.length}</b><span>next steps created</span></div>
          <div><b>${unresolved}</b><span>questions still open</span></div>
        </div>
        ${primaryFinding ? `<div class="finding">
          <span class="st st-CONFIRMED">Applies</span>
          <div><b>${esc(primaryHeadline)}</b><p>${esc(primaryCopy)}</p></div>
          <button class="btn" data-goto="6" type="button">See the action plan →</button>
        </div>` : `<div class="finding muted">
          <span class="st st-EXEMPT">No action needed</span>
          <div><b>No checked rule created a next step.</b><p>Open the detailed results to see the reason for each decision.</p></div>
        </div>`}
        ${unresolved ? `<div class="note"><b>${unresolved} additional fact${unresolved === 1 ? " is" : "s are"} still needed for a separate rule.</b> This does not block the result above. TARA leaves that rule open instead of guessing.</div>` : ""}
      </div>
      <details class="card matrix-details"><summary><b>See all ${cells} rule checks</b><span>Select a result for the plain-language reason.</span></summary>
        <div class="matrix-wrap"><table class="matrix"><thead>${head}</thead><tbody>${body}</tbody></table></div>
      </details>
      ${S.cell ? detail : `<div class="note"><b>Want to inspect another result?</b> Open the full check above and select any cell. TARA explains both positive and negative decisions.</div>`}
      <div class="nav"><button class="btn ghost" data-goto="1" type="button">Review case facts</button>
        ${unresolved ? `<button class="btn ghost" data-goto="5" type="button">Answer the missing question</button>` : ""}
        <button class="btn" data-goto="6" type="button">${primaryFinding ? "See the action plan →" : "Review next steps →"}</button></div>
    </div>`;
}

function stageInterview() {
  if (!S.run) return busyPanel("Waiting…");
  const qs = S.run.pending_questions;
  const answered = Object.keys(S.answers);

  const asked = qs.length ? qs.map(q => `
    <div class="qcard">
      <div class="qh">One answer is needed for ${esc(domainLabel(q.domain_id))}</div>
      <div class="qb">
        <p class="qt">${esc(q.text)}</p>
        <p class="hint">Until this is answered, TARA leaves that rule as <b>more information needed</b>. It does not guess or quietly decide that the rule does not apply.</p>
        <div class="row">
          <button class="btn" data-answer="${esc(q.question_id)}|true" type="button">Yes</button>
          <button class="btn" data-answer="${esc(q.question_id)}|false" type="button">No</button>
        </div>
        <details class="technical-details"><summary>Technical reference</summary><p>Question <code>${esc(q.question_id)}</code> · item <code>${esc(q.holding_id)}</code> · rule area <code>${esc(q.domain_id)}</code></p></details>
      </div>
    </div>`).join("") : `<div class="card pad">
      <b>Nothing to ask.</b>
      <p class="hint" style="margin-top:4px">The prepared case already contains every fact needed for this result. TARA asks a person only when the stored information cannot answer an important question.</p></div>`;

  return `<header>
      <span class="eyebrow">Step 6 of 9 · Missing information</span>
      <h2>${qs.length ? "One fact it will not assume" : "It had everything it needed"}</h2>
      <p class="lede">When an important fact is missing, TARA pauses that part of the result and asks a direct question. A human answer is safer than an invented assumption.</p>
    </header>
    <div class="stack">
      ${S.busy ? busyPanel("Rechecking the case with your answer…") : asked}
      ${answered.length ? `<div class="note"><b>Answer recorded.</b> TARA reran the affected checks from the beginning so the updated result is reproducible.</div>` : ""}
      <div class="nav"><button class="btn ghost" data-goto="4" type="button">← Back to results</button>
        <button class="btn" data-goto="6" type="button">See the action plan →</button></div>
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
  form_10f_and_trc: "Tax-treaty relief may apply — prepare Form 10F and a tax residency certificate",
  form_1116_ftc_claim: "Tax-treaty relief may apply — prepare a US foreign tax credit claim"
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
    <span class="hint">· review this on the next screen</span></div>`;
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
    <span class="cn">${esc(domainLabel(r.domain_id, r.title))}</span>
    <span class="st st-${esc(st)}">${esc(label)}</span>
    <span class="hint">${esc(plainReason(reason))}</span>
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
          <div class="stitle">${esc(actionTitle(a, info))}</div>
          <p class="action-meta"><b>${a.deadline ? `Do this by ${esc(formatDate(a.deadline))}` : "Agree a date with a qualified reviewer"}</b>
            ${appliesTo.length > 1 ? ` · applies to ${esc(appliesTo.map(holdingLabel).join(", "))}` : ""}</p>
          <p class="stxt">Prepare <b>${esc(evidenceLabel(a.artefact_type || a.required_evidence_type).toLowerCase())}</b> so a human reviewer can confirm this step is complete.</p>
          ${info && info.source ? `<p class="hint"><a href="${esc(info.source.url)}" target="_blank" rel="noopener">Read the source for this step ↗</a></p>` : ""}
          ${calcLine(a, domainId)}
          <label class="checkline"><input type="checkbox" data-check="${esc(actionId)}" ${checked ? "checked" : ""}>
            Mark as already completed${assumed ? ` <span class="assumed">(preselected from the prepared case — change if needed)</span>` : ""}</label>
          <details class="technical-details"><summary>Technical and legal reference</summary>
            <p>${esc(info && info.obligation ? info.obligation.text : "")}</p>
            <p>Provision ${esc(a.provision || "not stated")} · requirement <code>${esc(a.obligation_id)}</code> · action <code>${esc(a.action_id)}</code> · evidence type <code>${esc(a.artefact_type || a.required_evidence_type)}</code></p>
          </details>
        </div>
      </div>`;
    }).join("");

    return `<div class="card pad stack playbook-card">
      <div class="phead">
        <div>
          <span class="ptitle">${esc(domainLabel(domainId, pack.title))}</span>
          <span class="hint"> · ${esc(affectedHoldings.map(holdingLabel).join(", "))}</span>
        </div>
        <div class="row" style="gap:6px">
          ${pack.is_corridor ? `<span class="st st-INDETERMINATE">Cross-border</span>` : ""}
          ${[...treatyBadges].map(b => `<span class="chip" style="cursor:default">${esc(b)}</span>`).join("")}
        </div>
      </div>
      ${primarySource ? `<p class="hint">Primary source: <a href="${esc(primarySource.url)}" target="_blank" rel="noopener">${esc(primarySource.instrument)} ↗</a></p>` : ""}
      ${affectedHoldings.length > 1 ? `<p class="note compact"><b>Shown once for clarity.</b> The same requirement affects ${esc(affectedHoldings.map(holdingLabel).join(", "))}; TARA still tracks each item separately.</p>` : ""}
      <div class="steps">${stepsHtml}</div>
    </div>`;
  }).join("");

  const corridors = corridorSummary();
  const corridorPanel = corridors.length ? `<details class="card matrix-details"><summary><b>See cross-border checks</b><span>Why each country combination applies or does not apply.</span></summary>
      <div class="pad">${corridors.map(corridorRow).join("")}</div>
    </details>` : "";

  const assumption = PLAYBOOK_ASSUMPTIONS[S.presetId];

  return `<header>
      <span class="eyebrow">Step 7 of 9 · Action plan</span>
      <h2>${acts.length ? `What ${esc(S.holder.name)} should do next`
        : "Nothing is outstanding"}</h2>
      <p class="lede">${acts.length
        ? `The important information comes first: the task, the date, and the evidence to keep. Legal references and internal IDs are available only when you open the technical details.`
        : `Every checked rule either does not apply or is waiting for more information. Return to the results to see each reason.`}</p>
    </header>
    <div class="stack">
      <div class="grid3">
        <div class="tile"><div class="n">${uniqueObligationCount}</div><div class="l">clear tasks</div></div>
        <div class="tile"><div class="n">${groups.size}</div><div class="l">rule areas involved</div></div>
        <div class="tile"><div class="n">${Object.values(S.checklist).filter(Boolean).length}</div><div class="l">marked complete</div></div>
      </div>
      ${assumption ? `<div class="note"><b>Assumptions this profile makes:</b> ${esc(assumption.note)}</div>` : ""}
      ${corridorPanel}
      ${cards || `<div class="card pad"><b>No open actions.</b><p class="hint" style="margin-top:4px">
        Every rule area either does not apply or is still waiting for an answer.</p></div>`}
      <details class="note"><summary style="cursor:pointer"><b>How action dates are derived</b></summary>
        <p style="margin-top:8px">TARA calculates a date only when the source gives a fixed period. Wording such as “within a reasonable period” stays undated and is sent for human scheduling. If an event date is missing, TARA leaves the result open rather than inventing one.</p>
      </details>
      <div class="nav"><button class="btn ghost" data-goto="4" type="button">← Back to scan</button>
        <button class="btn" data-goto="7" type="button" ${acts.length ? "" : "disabled"}>Check the evidence →</button></div>
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
  if (!acts.length) return `<header><span class="eyebrow">Step 8 of 9 · Check evidence</span>
    <h2>There is no open task to check</h2></header>
    <div class="stack"><div class="card pad">Return to the missing-information step if another answer is needed.</div>
    <div class="nav"><button class="btn ghost" data-goto="6" type="button">← Back</button>
    <button class="btn" data-goto="8" type="button">See the proof record →</button></div></div>`;

  if (!S.actionId) {
    // open on an action ANCHOR can reject on the rate — that check is the
    // point of this stage, and it only exists on some obligations
    const best = acts.find(x => x.expected_rate != null) || acts[0];
    selectAction(best.action_id);
  }
  const a = currentAction();
  const info = obligationInfo(a.domain_id, a.obligation_id);
  const selectedTitle = actionTitle(a, info);

  const fields = Object.keys(S.artefact).filter(k => k !== "artefact_type").map(k => {
    const v = S.artefact[k];
    const isNum = typeof v === "number";
    const isDate = /_date$/.test(k) && /^\d{4}-\d{2}-\d{2}$/.test(String(v));
    const req = (a.required_fields || []).includes(k);
    return `<label class="f"><span>${esc(fieldLabel(k))}${req ? "" : ' <span class="hint">(optional)</span>'}</span>
      <input class="mono" type="${isDate ? "date" : isNum ? "number" : "text"}"
        ${isNum ? 'step="any"' : ""} data-art="${esc(k)}" value="${esc(v)}"></label>`;
  }).join("");

  const variants = Object.entries(a.variants || {}).map(([k, v]) =>
    `<button class="chip" type="button" data-variant="${esc(k)}">${esc(plainVariantLabel(v.label))}</button>`).join("");

  const result = S.closure ? `
    <div class="detail stack" style="gap:8px;border-left-color:${S.closure.outcome === "closed" ? "var(--verdigris)" : "var(--magenta)"}">
      <div class="row" style="align-items:center;gap:10px">
        <span class="st st-${esc(S.closure.outcome)}">${esc(statusLabel(S.closure.outcome))}</span>
        <b>${S.closure.outcome === "closed" ? "This evidence is ready for human review." : "This evidence needs to be corrected."}</b>
      </div>
      <p class="reason">${esc(plainReason(S.closure.reason))}</p>
      ${S.closure.trigger_date ? `<p class="hint">Checked against the relevant date: ${esc(formatDate(S.closure.trigger_date))}.</p>` : ""}
      <details class="technical-details"><summary>Technical reference</summary><p>Requirement <code>${esc(S.closure.obligation_id)}</code></p></details>
    </div>` : "";

  const uncaptured = S.error === "uncaptured" ? `<div class="warn">
    <b>That exact submission was not captured.</b> Replay holds the valid submission and the three specific ways of
    breaking it offered above. Use one of those chips, or connect a live engine to verify anything you like.</div>` : "";

  return `<header>
      <span class="eyebrow">Step 8 of 9 · Check evidence</span>
      <h2>Is the evidence good enough?</h2>
      <p class="lede">TARA checks that the right information is present and that the calculation matches the current rule. Try the old 41% rate first, then restore the correct 38% example.</p>
    </header>
    <div class="stack">
      <label class="f" style="max-width:760px"><span>Which task are you checking?</span>
        <select id="actionPick">${acts.map(x => `<option value="${esc(x.action_id)}" ${x.action_id === S.actionId ? "selected" : ""}>
          ${esc(actionTitle(x, obligationInfo(x.domain_id, x.obligation_id)))} — ${esc(holdingLabel(x.holding_id))}${x.deadline ? ` · due ${esc(formatDate(x.deadline))}` : ""}</option>`).join("")}</select></label>

      <div class="card pad stack">
        <div><p class="context-label">Evidence for</p><h3>${esc(selectedTitle)}</h3>
          <p class="hint">Expected document: ${esc(evidenceLabel(S.artefact.artefact_type))}${a.expected_rate != null ? ` · required rate: ${(a.expected_rate * 100).toFixed(0)}%` : ""}</p></div>
        <div class="grid2">${fields}</div>
        <div>
          <p class="hint" style="margin-bottom:6px">This form starts with a correct example. Use these buttons to test common mistakes:</p>
          <div class="chips">${variants}</div>
        </div>
        <details class="technical-details"><summary>Technical evidence contract</summary>
          <p>Evidence type <code>${esc(S.artefact.artefact_type)}</code> · required fields <code>${esc((a.required_fields || []).join(", ") || "none")}</code> · action <code>${esc(a.action_id)}</code></p>
        </details>
        <div class="row" style="align-items:center;gap:12px">
          <button class="btn" id="submitEvidence" type="button" ${S.busy ? "disabled" : ""}>Check this evidence</button>
          ${S.busy ? `<span class="spin"></span>` : ""}
        </div>
      </div>
      ${uncaptured}
      ${S.error && S.error !== "uncaptured" ? errorPanel() : ""}
      ${result}
      <div class="nav"><button class="btn ghost" data-goto="6" type="button">← Back to action plan</button>
        <button class="btn" data-goto="8" type="button">See the proof record →</button></div>
    </div>`;
}

function stageLedger() {
  if (!S.run) return busyPanel("Waiting…");
  const at = S.run.atlas;
  const verification = S.verification;
  return `<header>
      <span class="eyebrow">Step 9 of 9 · Proof record</span>
      <h2>See how TARA reached this result</h2>
      <p class="lede">Every important step is recorded in order, from reading the source to checking the case and creating the action plan. A tamper check confirms whether that sequence is intact.</p>
    </header>
    <div class="stack">
      <div class="grid3">
        <div class="tile"><div class="n">Complete</div><div class="l">source-to-action record</div></div>
        <div class="tile"><div class="n" style="color:${at.chain_verified ? "var(--verdigris)" : "var(--magenta)"}">${at.chain_verified ? "Passed" : "Failed"}</div><div class="l">tamper check</div></div>
        <div class="tile"><div class="n">${verification && S.closure ? esc(statusLabel(S.closure.outcome)) : "Not run"}</div><div class="l">latest evidence check</div></div>
      </div>
      <div class="card pad proof-story">
        <div><span>1</span><p><b>Source checked</b><br>The rule change and its source fingerprints were recorded.</p></div>
        <div><span>2</span><p><b>Case matched</b><br>The person's facts were checked without filling in missing information.</p></div>
        <div><span>3</span><p><b>Plan created</b><br>Applicable requirements became dated, reviewable tasks.</p></div>
        <div><span>4</span><p><b>Evidence tested</b><br>The submitted calculation was accepted or returned with a reason.</p></div>
      </div>
      ${verification ? `<div class="card pad stack">
        <div class="row" style="align-items:center;gap:10px"><span class="st st-${S.closure && S.closure.outcome === "closed" ? "closed" : "returned"}">${esc(statusLabel(S.closure ? S.closure.outcome : "returned"))}</span>
          <b>Latest evidence check recorded</b>
          <span class="hint">record integrity ${verification.chain_verified ? "passed" : "failed"}</span></div>
        <p class="hint">The evidence check rebuilds the prepared case before reviewing the submission. Its record is shown separately so this prototype does not claim to be a shared production audit system.</p>
      </div>` : ""}
      <details class="card matrix-details"><summary><b>See the technical event log</b><span>Internal role names and references for reviewers.</span></summary>
        <div class="pad stack">
          <p class="technical-ref">${at.entry_count} recorded events · ${at.agents_seen.length} specialist roles · integrity ${at.chain_verified ? "passed" : "failed"}</p>
          <div class="ledger">${at.tail.map(e => `<div><span class="ag">${esc(e.agent)}</span><span class="sp">${esc(titleCase(e.step))}${e.obligation_id ? " · " + esc(e.obligation_id) : ""}${e.tenant_id ? " · " + esc(e.tenant_id) : ""}</span></div>`).join("")}</div>
          ${verification ? `<div class="ledger">${(verification.tail || []).map(e => `<div><span class="ag">${esc(e.agent)}</span><span class="sp">${esc(titleCase(e.step))}${e.obligation_id ? " · " + esc(e.obligation_id) : ""}${e.tenant_id ? " · " + esc(e.tenant_id) : ""}</span></div>`).join("")}</div>` : ""}
          <p class="technical-ref">Internal roles used in this run: ${at.agents_seen.map(x => `<code>${esc(x)}</code>`).join(" ")}</p>
        </div>
      </details>
      <div class="card pad stack">
        <h3 style="font-size:var(--step-1)">The complete prototype journey</h3>
        <p class="lede" style="font-size:var(--step-0)">A changed rule became a clear decision, an action plan, a checked piece of evidence, and an inspectable record. A qualified human remains responsible for approving real-world action.</p>
        <div class="row"><button class="btn" id="again" type="button">Try another example</button>
          <button class="btn ghost" data-goto="4" type="button">Back to results</button></div>
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
      "Live calculation service URL (leave empty to use the prepared backup):\n\n" +
      "Example: https://tara-demo.onrender.com", S.api || "");
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
