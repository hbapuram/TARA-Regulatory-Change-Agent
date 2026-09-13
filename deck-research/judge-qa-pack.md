# TARA — Judge Q&A and Pitch Key Points

## Core Pitch Key Points (The "Elevator" Summary)
- **The Problem:** Regulatory changes break existing compliance workflows because identifying *who* is affected and *what* they must do is a manual, error-prone translation problem.
- **The Solution:** TARA is a governed change-to-action agent. It detects source changes, scopes them to specific cases, generates a playbook, and mathematically verifies the submitted evidence.
- **The Differentiator:** Deterministic safety. TARA does not use LLMs to calculate tax, guess deadlines, or evaluate thresholds. AI coordinates; deterministic Python decides.
- **The Proof:** The live demo proves the system can reject a mathematically correct but legally superseded 41% calculation, accept the current 38% calculation, and log the trace.
- **The Ask:** One domain reviewer and one design partner for a controlled 90-day pilot.

---

## Anticipated Judge Questions & Safe Answers

### 1. "Is this live-monitoring regulators' websites?"
**Answer:** "No, not yet. Today, TARA uses controlled, versioned source snapshots. Continuous, automated ingestion of live regulator websites introduces unacceptable legal risk without a human-in-the-loop approval step. Building that governed ingestion workflow is our Day 30–60 milestone."

### 2. "Can it hallucinate a tax rate or a deadline?"
**Answer:** "No. The AI models in TARA do not perform calculations or invent dates. The rules are encoded in deterministic YAML packs. If the source says '38%', the deterministic engine enforces 38%. If the source says 'within a reasonable period' instead of a hard date, TARA leaves it undated for manual scheduling rather than hallucinating a deadline."

### 3. "What happens if the user's profile is missing information?"
**Answer:** "TARA fails closed. If a material fact—like a residency threshold or an event date—is missing, the engine evaluates the obligation as `INDETERMINATE`. It explicitly refuses to create an automated action and escalates it for human review. It never guesses."

### 4. "Are you replacing tax advisors?"
**Answer:** "No, we are arming them. Our initial buyers are cross-border advisory and relocation-compliance teams. TARA does the mechanical translation of a rule change into a verified draft. A qualified human professional must still review the trace, approve the action, and actually file it. We are reducing their review time and false-positive rate, not replacing their judgment."

### 5. "How much of this is actually built versus just a mockup?"
**Answer:** "Everything you saw in the demo is running code. We have 9 domain packs loaded, 9 agents coordinating, 10 MCP tools, and 112 automated tests passing on the public repository today. The ATLAS audit trace is generated live by the pipeline. It is a working prototype, though we are clear that it requires production hardening—like tenant isolation and encryption—before handling real client data."

### 6. "Why did you build 9 packs if only one is the 'tested path'?"
**Answer:** "The Maeve path (Irish fund taxation) is our deeply tested golden path to prove the end-to-end evidence check. The other 8 packs—including US FBAR and Indian foreign-asset disclosure—are exploratory. We built them to prove the architecture can handle multi-jurisdictional breadth and cross-border corridors without breaking, but we do not claim they are independently legally validated yet."

### 7. "What is your business model?"
**Answer:** "We are validating a pilot wedge first. The core engine is open-source (MIT), but the governed workflows, proprietary rule packs, and enterprise audit integrations will be paid. Before we finalize per-seat or per-case pricing, we need to measure the actual time saved and error reduction in our first design-partner pilot."
