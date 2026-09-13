# TARA: From a changed rule to verified evidence

## See the idea first

```mermaid
flowchart LR
    A[Rule changes] --> B[LLM chooses MCP tools]
    B --> C[TARA finds the changed provision]
    C --> D[TARA checks one synthetic case]
    D --> E{Enough facts?}
    E -- No --> F[Ask; do not guess]
    E -- Yes --> G[Choose the rule version for the event date]
    G --> H[Create an owned, dated action]
    H --> I{Evidence exact?}
    I -- No --> J[Return with a reason]
    I -- Yes --> K[Close and record the trace]
```

**TARA is a regulatory change-to-action prototype.** It connects versioned source text to a case-specific action and a checkable proof trail. It is not legal, tax, immigration, or filing advice.

For the complete visual and technical reference, open [tara-project-guide.html](tara-project-guide.html). For the executable results, open [evaluation-card.md](evaluation-card.md).

## The recommended demonstration

Use the synthetic **Maeve** profile at [tara-demo.onrender.com](https://tara-demo.onrender.com/).

1. The default browser path asks an OpenAI model to discover the available TARA tools, the source, and the prepared case through MCP.
2. Revenue's Section 4.3 rate changes from **41% to 38%** for relevant events on or after **1 January 2026**.
3. Maeve's eight-year event falls in 2026.
4. TARA selects the 38% obligation and rules the historical 41% obligation out for this event.
5. TARA creates the work item and evidence contract.
6. TARA returns the old 41% calculation and accepts the exact 38% calculation.
7. The proof record verifies the linked trace.

> **Why this path matters:** it proves the competition's complete “change to action” loop with one understandable consequence. The other profiles demonstrate breadth and are labelled exploratory.

## The system in plain language

| Agent | Plain-language job |
|---|---|
| SURVEY | Notice exactly what changed in a source. |
| LEGEND | Turn the changed text into small, cited duties. |
| ALMANAC | Keep the rule history and supersession map. |
| COMPASS | Decide whether a rule family is relevant to this case. |
| PLOT | Decide whether each particular duty actually triggers. |
| COURSE | Create the action, owner, date, and requested proof. |
| ANCHOR | Check the proof and return or close it. |
| MERIDIAN | Repeat the same process across countries and corridors. |
| ATLAS | Record every step in a tamper-evident chain. |

## The important safety distinction

A person can be within a **rule family** without triggering every obligation in that family. TARA models that in two stages:

1. COMPASS checks pack-level scope.
2. PLOT checks each obligation's instrument, event, threshold, effective date, trigger date, and prior closure.

PLOT can return `satisfied`, `partial`, `absent`, `not_applicable`, or `indeterminate`. COURSE opens actions only for `partial` or `absent`. A missing material fact never becomes an invented task.

## What is real today

- Nine domain packs: six standalone packs and three cross-border corridors.
- Twelve MCP tools, including domain, source, and prepared-holding discovery.
- A deployed **LLM-first** browser demonstration with a readable MCP trace and deterministic backup.
- A captured-response replay for venue reliability.
- Deterministic source diffs, date calculations, applicability checks, and evidence validation.
- A hash-linked proof record.
- 115 passing automated tests.
- Eight executable acceptance checks in `tools/build_evaluation_card.py`.

## What is not claimed

- Continuous source retrieval and approval.
- Comprehensive legal coverage.
- Independent professional sign-off.
- Production identity, tenancy, encryption, or retention controls.
- Regulator acceptance of an artefact.
- External user traction or a signed design partner.

## Technical path

```text
source snapshots
  → OpenAI orchestrator chooses MCP tool calls
  → MCP discovery returns domains, sources and holdings
  → SURVEY ChangeRecord
  → LEGEND ObligationRecord
  → ALMANAC version graph
  → COMPASS Determination
  → PLOT GapEntry
  → COURSE Action
  → ANCHOR ClosureResult
  → ATLAS hash-linked entries
```

Domain packs are YAML. The default browser path uses an OpenAI model as an MCP client: it selects the tool sequence and explains the result. Consequential calculations remain deterministic Python. The model does not own the legal rates, dates, thresholds, arithmetic, or evidence verdict.

## Run it

```bash
pip install -e '.[dev]'
pip install -r requirements.txt
pip install -r demo/requirements.txt
pytest -q
python tools/build_evaluation_card.py
python -m uvicorn demo.api:app --host 127.0.0.1 --port 8000
```

## Present it

Lead with Maeve and the wrong-but-consistent 41% calculation. First show the simple **AI orchestration · MCP** trace, then show **What changed**, **What applies**, the **Action plan**, the evidence that **Needs correction**, the evidence that is **Accepted**, and the **Proof record**. Explain the safety boundary in plain language: the model chooses tools; TARA verifies dates, calculations, and evidence.

For a slide deck, use a hyperlink or QR code to [https://tara-demo.onrender.com/](https://tara-demo.onrender.com/) and keep two backup screenshots. Do not rely only on an embedded live web view.

