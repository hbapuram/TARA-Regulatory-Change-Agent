# TARA — Seven-Minute Pitch Script

**Target duration:** 6:30 (leaves 30 seconds buffer)
**Pacing:** Deliberate, authoritative, and outcome-led. Do not rush the demo handoff.

---

## Slide 1: The memorable consequence (0:00 – 0:45)
*(Slide: A rule changed. A correct-looking calculation is now wrong.)*

"Good morning. I want to start with a concrete failure. 

Imagine a regulatory provision changes—say, a tax rate drops from 41% to 38%. The day before the change, a 41% calculation is perfect compliance. The day after, that exact same calculation is a failure. 

Publishing the new rule doesn't fix the problem. Someone has to figure out who is affected, what they need to do, and whether the proof they submit is actually correct under the new rule. 

That is what TARA does. TARA is a governed agent that turns a cited regulatory change into a case-specific action, and then checks the proof used to close it."

---

## Slide 2: The broken handoff (0:45 – 1:30)
*(Slide: Publishing the rule is not the same as operationalising it.)*

"Let’s look at Maeve. Maeve holds an offshore fund with a deemed-disposal event coming up in 2026. 

For a cross-border advisory or relocation team managing hundreds of Maeves, the handoff is broken in three places. First, when the source changes, someone has to notice. Second, someone has to decide if the new version applies to Maeve’s specific event date. And third, when Maeve submits a plausible-looking 41% calculation, someone has to catch that it’s the wrong rate.

Nothing keeps all three aligned automatically. Until now."

---

## Slide 3: The product in one picture (1:30 – 2:15)
*(Slide: From source change to human-reviewed action—with receipts.)*

"TARA fixes this with one governed loop. 

First, it compares controlled source snapshots and decomposes the change into cited obligations. That happens once. 

Then, for each case, it decides whether the obligation applies, creates an owned action with a deadline, and checks the submitted evidence—the required fields, the rate, and the arithmetic. 

Finally, it traces the entire decision in an inspectable ledger. You don't have to trust a black-box model, because the workflow is broken into deterministic steps."

---

## Slide 4: The live proof (2:15 – 2:30)
*(Slide: Watch TARA reject yesterday's correct answer.)*

"Let’s look at the live engine. I’m going to run Maeve’s case through the tested judge path."

*(Transition to Demo 1)*

---

## Slide 5: Demo 1 — Detect and plan (2:30 – 3:15)
*(Slide: Demo 1 — Detect the changed provision and create the playbook.)*

"Here is the source chart. TARA has detected that Revenue’s Section 4.3 changed from 41% to 38%, and it preserved both source hashes. 

It doesn't ask a model to guess the rate. Maeve’s event date deterministically selects the post-2026 version. 

TARA then creates a playbook: a cited action, a deadline, and an explicit evidence contract. It knows exactly what proof it needs to close the work."

---

## Slide 6: Demo 2 — Return and close (3:15 – 4:00)
*(Slide: Demo 2 — Return the old rate, close the exact rate.)*

"Now we submit the evidence. 

First, I’ll submit the old 41% calculation. The arithmetic is correct—€4,920 on a €12,000 gain. But TARA returns it. It explicitly states that 41% does not match the 38% rate required for this specific obligation. 

So I reset to 38% and €4,560. The arithmetic is perfect, the rate matches the current rule, and TARA closes the action."

---

## Slide 7: Demo 3 — The audit trace (4:00 – 4:30)
*(Slide: Demo 3 — Leave an inspectable trace.)*

"And here is the receipt. ATLAS preserves the source diff, the decision, the action, and the evidence result in a hash-linked trace. 

To be clear: TARA has not filed anything with a regulator. A human professional still reviews the action. But that professional is now reviewing a verified, mathematically correct claim, not starting from scratch."

---

## Slide 8: Trust boundaries (4:30 – 5:15)
*(Slide: AI coordinates. Deterministic tools decide. A human remains accountable.)*

"This works because we enforce strict trust boundaries. 

AI coordinates the workflow and explains the results. But deterministic tools own the source diffs, the dates, the thresholds, and the arithmetic. And a human retains the authority to file or rely on the output. 

Crucially, TARA fails closed. If a material fact is missing, the result is 'indeterminate' and no automated action is created. It does not guess."

---

## Slide 9: Pilot wedge (5:15 – 5:45)
*(Slide: Start with one reviewed rule family and one accountable team.)*

"We aren't selling this to every individual taxpayer tomorrow. 

Our wedge is cross-border tax, advisory, and relocation-compliance teams. We are starting with one independently reviewed Irish rule path and synthetic cases. 

The value is measurable: we track median review time, the reduction in false-positive actions, and reviewer confidence."

---

## Slide 10: Roadmap and Ask (5:45 – 6:30)
*(Slide: The next unlock is external proof, not more agent names.)*

"We have proved the core engine. We have 112 automated tests and 8 executable acceptance checks passing today. 

Our next 90 days are about external proof. We will complete an independent professional review of the Maeve path, build a governed source-ingestion workflow, and run one controlled design-partner pilot. 

Our ask today is simple: we are seeking one Irish tax or domain reviewer, and one cross-border advisory team to co-design that pilot. 

Thank you. I invite you to try the live demo at the link on screen."
