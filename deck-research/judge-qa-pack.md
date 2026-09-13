# TARA — Judge Q&A and Pitch Key Points

## Core pitch in five lines

- **The problem:** Regulatory changes create a manual translation problem: teams must find the affected people, define the right action, and validate the proof.
- **The solution:** TARA is a governed change-to-action agent. Its LLM discovers and sequences guarded MCP tools; deterministic controls compare source versions, assess cases, create actions, and check evidence.
- **The differentiator:** The LLM is visible and useful, but it does not calculate tax, guess deadlines, or decide evidence outcomes. AI investigates; deterministic Python decides; humans approve real-world action.
- **The proof:** The live demo rejects a mathematically coherent but superseded 41% calculation, accepts the current 38% calculation, and records the result in a tamper-evident proof record.
- **The ask:** One domain reviewer and one cross-border advisory design partner for a controlled pilot.

---

## Anticipated judge questions and safe answers

### 1. “Where is the AI? Isn’t this just rules?”

**Answer:** “The default live path uses an OpenAI model as the orchestration layer. It interprets the request, discovers the allowed domain, source, and case tools through MCP, chooses the tool sequence, and explains the verified result. We show that MCP trace in the browser. We deliberately do not let the model own tax rates, event dates, thresholds, arithmetic, or evidence outcomes—those are deterministic because the cost of a fluent but wrong answer is too high.”

### 2. “Why use MCP rather than a prompt and a database?”

**Answer:** “MCP gives the model a discoverable, governed interface. The model must first obtain canonical IDs and then call narrowly defined tools. The same tools can also be used by a CLI or another AI client. That makes the work inspectable and reusable rather than hiding the decision path inside one large prompt.”

### 3. “Can it hallucinate a tax rate or deadline?”

**Answer:** “The LLM can make a poor orchestration choice, which is why the browser shows its tool trace and the service enforces a required discovery and action-planning sequence for the judged path. It cannot change a rate, calculate a date, or turn a missing fact into a decision: those results come from deterministic code and controlled snapshots. If the source is qualitative rather than fixed, the action remains undated for a human to schedule.”

### 4. “What happens if a user profile is incomplete?”

**Answer:** “TARA fails closed. If a material fact such as a residency threshold or event date is missing, it returns an indeterminate state, creates no automated action, and explicitly asks for human review. It does not guess.”

### 5. “What happens if OpenAI is unavailable during the demo or in use?”

**Answer:** “The UI is explicit: the default is AI/MCP. If the AI call or local MCP subprocess fails, it switches to a labelled deterministic backup that runs the same controlled source, case, and evidence checks. If the host is unavailable, a captured replay remains available. The fallback never pretends to be an AI result.”

### 6. “Are you replacing tax advisers?”

**Answer:** “No. Our first buyer is a cross-border advisory practice; TARA prepares a verified draft and proof record, while a qualified professional remains responsible for reviewing it, approving it, and taking any real-world action. We aim to reduce review time and false-positive work, not replace judgment.”

### 7. “How much is actually built?”

**Answer:** “The live browser demo, the server-side OpenAI orchestration, request-scoped MCP subprocess, deterministic controls, deterministic backup, replay fallback, public repository, and guide are running today. The project has 115 passing automated tests, 12 guarded MCP tools, nine rule packs, and eight executable acceptance checks. It is still a prototype: it has controlled snapshots, prepared synthetic cases, and needs independent domain review and production security before it could handle client data.”

### 8. “Why nine packs if only one case is in the core demo?”

**Answer:** “Maeve is the recommended end-to-end demonstration. The other packs show the reusable structure and cross-border breadth, but we do not claim that each one is independently legally validated. Expansion requires a reviewed pack, source approval, and the same test discipline.”

### 9. “What is your business model?”

**Answer:** “We are testing a focused hypothesis: cross-border advisory practices pay for monitored rule packs and governed workflows. Before we set pricing, we need to measure review-time reduction, false-positive work, and reviewer confidence in a controlled design-partner pilot.”

---

## Live-demo preflight

1. Open `https://tara-demo.onrender.com/` and wait for **AI / MCP READY**.
2. Select **Maeve**.
3. Mention the visible MCP trace before showing the 41% → 38% change.
4. Demonstrate the old-rate rejection and current-rate acceptance.
5. If the AI route degrades, explain and use the labelled deterministic backup; do not hide the change of mode.
6. If the host is unavailable, switch to the captured replay or static screenshots.
