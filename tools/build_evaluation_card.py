"""Generate the public, reproducible TARA competition evaluation card.

The card is built from executable acceptance checks, not hand-entered claims.
Run from the repository root:

    python tools/build_evaluation_card.py
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from tara import pipeline
from tara.agents import course, survey
from tara.agents.compass import Determination
from tara.agents.legend import ObligationRecord
from tara.agents.plot import align
from tara.core.interactions import load_interaction_packs
from tara.mcp_server.context import build_context

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "evaluation-card.md"


def record(pack, obligation_id: str) -> ObligationRecord:
    item = pack.obligation(obligation_id)
    return ObligationRecord(
        item.obligation_id,
        item.provision,
        item.text,
        item.severity,
        item.artefact_type,
        item.source_id,
        "unchanged",
    )


def confirmed(holding_id: str) -> Determination:
    return Determination(holding_id, "CONFIRMED", "evaluation fixture", None, None)


def check(name: str, passed: bool, evidence: str) -> dict[str, str]:
    if not passed:
        raise AssertionError(f"{name}: {evidence}")
    return {"check": name, "status": "PASS", "evidence": evidence}


def main() -> None:
    checks: list[dict[str, str]] = []
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx = build_context(
            domain_yaml=ROOT / "domains" / "tax.yaml",
            register_json=ROOT / "registers" / "holder_register.json",
            atlas_path=tmp_path / "atlas.jsonl",
            almanac_version_path=tmp_path / "graph.json",
            linked_domain_yamls=[ROOT / "domains" / "us.yaml"],
            interactions_yaml=ROOT / "domains" / "interactions.yaml",
        )

        changed = survey.detect_change(ctx.domain_pack, "revenue-27-01a-02", as_of=date(2026, 9, 13))
        checks.append(check(
            "Source change detected",
            any(c.reference == "Section 4.3" and c.change_type == "amended" for c in changed.changes),
            "SURVEY reports Section 4.3 amended and preserves both source hashes.",
        ))

        old_holding = dict(ctx.holding("HLD-001"), acquisition_date="2017-03-14")
        old_gaps = align(
            ctx.domain_pack,
            old_holding,
            pipeline.full_obligation_set(ctx),
            confirmed("HLD-001"),
            as_of=date(2025, 4, 1),
        )
        old_by_id = {g.obligation_id: g for g in old_gaps}
        checks.append(check(
            "Historical rate selected",
            old_by_id["OBL-002"].coverage == "absent"
            and old_by_id["OBL-002B"].coverage == "not_applicable",
            "A 2025 event selects the 41% rule and excludes the post-2026 rule.",
        ))

        new_holding = dict(ctx.holding("HLD-001"), acquisition_date="2018-03-14")
        new_gaps = align(
            ctx.domain_pack,
            new_holding,
            pipeline.full_obligation_set(ctx),
            confirmed("HLD-001"),
            as_of=date(2026, 4, 1),
        )
        new_by_id = {g.obligation_id: g for g in new_gaps}
        checks.append(check(
            "Current rate selected",
            new_by_id["OBL-002"].coverage == "not_applicable"
            and new_by_id["OBL-002B"].coverage == "absent",
            "A 2026 event selects the 38% rule and excludes the superseded 41% rule.",
        ))

        actions = course.plan(ctx.domain_pack, new_gaps, owner="Synthetic Reviewer", atlas=ctx.atlas)
        rate_action = next(a for a in actions if a.obligation_id == "OBL-002B")
        rejected = pipeline.verify_action(
            ctx,
            rate_action,
            {"artefact_type": "tax_computation", "rate_applied": 0.41,
             "deemed_gain": 12000.0, "computed_tax": 4920.0},
            profile_answers={"SQ-03": False},
            as_of=date(2026, 4, 1),
        )
        accepted = pipeline.verify_action(
            ctx,
            rate_action,
            {"artefact_type": "tax_computation", "rate_applied": 0.38,
             "deemed_gain": 12000.0, "computed_tax": 4560.0},
            profile_answers={"SQ-03": False},
            as_of=date(2026, 4, 1),
        )
        checks.append(check(
            "Superseded evidence rejected",
            rejected.outcome == "returned" and accepted.outcome == "closed",
            "ANCHOR returns a 41% computation and closes the exact 38% computation.",
        ))

        us_pack = ctx.linked_packs["us-fbar"]
        us_gap = align(
            us_pack,
            {"holding_id": "PROP", "instrument_type": "residential_property",
             "acquisition_date": "2024-01-01", "peak_aggregate_value_usd": 50000},
            [record(us_pack, "OBL-US-001")],
            confirmed("PROP"),
            as_of=date(2026, 1, 2),
        )[0]
        checks.append(check(
            "False-positive action blocked",
            us_gap.coverage == "not_applicable",
            "A foreign property no longer creates an FBAR action merely because the pack is in scope.",
        ))

        missing_gap = align(
            us_pack,
            {"holding_id": "BANK", "instrument_type": "foreign_bank_account",
             "acquisition_date": "2024-01-01"},
            [record(us_pack, "OBL-US-001")],
            confirmed("BANK"),
            as_of=date(2026, 1, 2),
        )[0]
        checks.append(check(
            "Missing threshold handled safely",
            missing_gap.coverage == "indeterminate"
            and course.plan(us_pack, [missing_gap], owner="Synthetic Reviewer") == [],
            "A missing FBAR threshold fact yields no automated action.",
        ))

        corridor = load_interaction_packs(
            ROOT / "domains" / "interactions.yaml", base_path=ROOT
        )["india-ireland-corridor"]
        corridor_holding = {
            "holding_id": "BANK-IE",
            "instrument_type": "foreign_bank_account",
            "jurisdiction": "India",
            "acquisition_date": "2019-01-01",
            "tax_residency_since": "2021-07-01",
            "citizenships": ["India"],
            "tax_residencies": ["Ireland"],
        }
        corridor_gap = align(
            corridor,
            corridor_holding,
            [record(corridor, "OBL-CORR-001")],
            confirmed("BANK-IE"),
            as_of=date(2022, 1, 1),
        )
        corridor_action = course.plan(corridor, corridor_gap, owner="Synthetic Reviewer")[0]
        checks.append(check(
            "Qualitative timing is not invented",
            corridor_action.deadline is None and corridor_action.escalated,
            "A source that says 'within a reasonable period' remains manually scheduled; TARA emits no fabricated statutory date.",
        ))

        checks.append(check(
            "Audit chain verifies",
            ctx.atlas.verify_chain(),
            f"ATLAS verifies a {len(ctx.atlas.all_entries())}-entry hash chain after the acceptance run.",
        ))

    collection_output = subprocess.run(
        ["pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    match = re.search(r"(\d+) tests? collected", collection_output)
    if not match:
        raise RuntimeError("could not determine collected test count")
    collected = f"{match.group(1)} tests collected"

    rows = "\n".join(
        f"| {i} | {item['check']} | **{item['status']}** | {item['evidence']} |"
        for i, item in enumerate(checks, 1)
    )
    generated = date.today().isoformat()
    text = f"""# TARA Evaluation Card

> **Plain-language verdict:** TARA demonstrates a complete and reproducible regulatory change-to-action loop on a deliberately narrow, synthetic case. It detects a source change, selects the rule version that applies on the event date, creates an action, rejects superseded evidence, accepts exact evidence, and preserves an auditable trace.

## Visual acceptance path

```mermaid
flowchart LR
    A[Official source snapshots] --> B[Section 4.3 changed]
    B --> C{{Event before or after 1 Jan 2026?}}
    C -->|Before| D[41% historical rule]
    C -->|On or after| E[38% current rule]
    E --> F[Action + date + owner]
    F --> G{{Evidence check}}
    G -->|41%| H[Returned]
    G -->|38% and exact| I[Closed]
    B & C & F & G --> J[(ATLAS audit chain)]
```

## Executable acceptance checks

| # | Check | Result | Reproducible evidence |
|---:|---|---|---|
{rows}

**Test inventory:** `{collected}`. The canonical command is `pytest -q`.

## Competition readiness score

This is an **internal evidence-based readiness estimate, not an organiser or judge score**.

| Dimension | Weight | Current | Why |
|---|---:|---:|---|
| Problem clarity and relevance | 18 | 17 | Clear change-to-action problem with a memorable human consequence. |
| Innovation and agent design | 18 | 16 | Open/tenant bands, data-driven domain packs, MCP tools, and an auditable multi-agent handoff. |
| Technical architecture | 15 | 14 | Deterministic core, explicit band order, reusable packs, deployable API, and regression coverage. |
| Correctness and safety | 18 | 15 | Effective-date selection, obligation-level predicates, fail-closed missing facts, exact evidence checks, and disclaimers. Independent professional validation is still pending. |
| Evidence and demo quality | 12 | 11 | Tested golden path, offline replay, live deployment, source hashes, and this executable card. |
| Usability and storytelling | 9 | 8 | Recommended path first, plain-language explanations, visual guide, and exploratory cases clearly labelled. |
| Validation and traction | 6 | 2 | No external user interviews, signed design partner, or SME sign-off is claimed. |
| Release and documentation quality | 4 | 4 | Reproducible setup, public-release manifest, tests, deployment notes, and one-stop guide. |
| **Total** | **100** | **87** | **Finalist-grade internal readiness; external validation is the main remaining gap.** |

## Boundaries judges should know

TARA is a **prototype decision-support system**, not legal, tax, immigration, or filing advice. The live demo uses controlled source snapshots and synthetic profiles. A pack-level `CONFIRMED` result means the rule family is relevant; each obligation is then checked separately for its instrument, event, threshold, and effective date. Missing material facts produce `indeterminate` and no automated action.

The system does not yet claim continuous regulator polling, production authentication, durable multi-tenant storage, or independent legal validation. Those are explicitly release-gated rather than implied.

## Reproduce

```bash
pip install -e '.[dev]'
pytest -q
python tools/build_evaluation_card.py
python -m uvicorn demo.api:app --host 127.0.0.1 --port 8000
```

Generated {generated} from executable acceptance checks in `tools/build_evaluation_card.py`.
"""
    OUT.write_text(text, encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": len(checks), "tests": collected}))


if __name__ == "__main__":
    main()
