from __future__ import annotations

from datetime import date
from pathlib import Path

from tara import pipeline
from tara.agents import course
from tara.agents.compass import Determination
from tara.agents.legend import ObligationRecord
from tara.agents.plot import align
from tara.core.domain_pack import load_domain_pack
from tara.core.interactions import load_interaction_packs

REPO_ROOT = Path(__file__).resolve().parent.parent


def _confirmed(holding_id: str) -> Determination:
    return Determination(holding_id, "CONFIRMED", "test", None, None)


def _record(pack, obligation_id: str) -> ObligationRecord:
    obligation = pack.obligation(obligation_id)
    return ObligationRecord(
        obligation.obligation_id,
        obligation.provision,
        obligation.text,
        obligation.severity,
        obligation.artefact_type,
        obligation.source_id,
        "unchanged",
    )


def test_rate_rule_uses_41_percent_before_2026(ctx):
    holding = dict(ctx.holding("HLD-001"), acquisition_date="2017-03-14")
    gaps = align(
        ctx.domain_pack,
        holding,
        pipeline.full_obligation_set(ctx),
        _confirmed("HLD-001"),
        as_of=date(2025, 4, 1),
    )
    by_id = {gap.obligation_id: gap for gap in gaps}

    assert by_id["OBL-002"].coverage == "absent"
    assert by_id["OBL-002B"].coverage == "not_applicable"


def test_rate_rule_uses_38_percent_from_2026(ctx):
    holding = dict(ctx.holding("HLD-001"), acquisition_date="2018-03-14")
    gaps = align(
        ctx.domain_pack,
        holding,
        pipeline.full_obligation_set(ctx),
        _confirmed("HLD-001"),
        as_of=date(2026, 4, 1),
    )
    by_id = {gap.obligation_id: gap for gap in gaps}

    assert by_id["OBL-002"].coverage == "not_applicable"
    assert by_id["OBL-002B"].coverage == "absent"


def test_course_never_opens_inapplicable_or_indeterminate_obligations(ctx):
    holding = dict(ctx.holding("HLD-001"), acquisition_date="2018-03-14")
    gaps = align(
        ctx.domain_pack,
        holding,
        pipeline.full_obligation_set(ctx),
        _confirmed("HLD-001"),
        as_of=date(2026, 4, 1),
    )
    actions = course.plan(ctx.domain_pack, gaps, owner="Reviewer")

    assert "OBL-002" not in {action.obligation_id for action in actions}
    assert "OBL-002B" in {action.obligation_id for action in actions}


def test_missing_trigger_date_is_indeterminate_without_action(ctx):
    holding = dict(ctx.holding("HLD-001"))
    holding.pop("acquisition_date", None)
    gaps = align(
        ctx.domain_pack,
        holding,
        pipeline.full_obligation_set(ctx),
        _confirmed("HLD-001"),
        as_of=date(2026, 4, 1),
    )

    assert gaps
    assert all(gap.coverage == "indeterminate" for gap in gaps)
    assert course.plan(ctx.domain_pack, gaps, owner="Reviewer") == []


def test_fbar_requires_a_foreign_account_and_threshold_fact():
    pack = load_domain_pack(REPO_ROOT / "domains" / "us.yaml")
    property_holding = {
        "holding_id": "H-1",
        "instrument_type": "residential_property",
        "acquisition_date": "2024-01-01",
        "peak_aggregate_value_usd": 50000,
    }
    gaps = align(
        pack,
        property_holding,
        [_record(pack, "OBL-US-001")],
        _confirmed("H-1"),
        as_of=date(2026, 1, 2),
    )
    assert gaps[0].coverage == "not_applicable"


def test_fbar_missing_threshold_is_indeterminate_without_action():
    pack = load_domain_pack(REPO_ROOT / "domains" / "us.yaml")
    holding = {
        "holding_id": "H-2",
        "instrument_type": "foreign_bank_account",
        "acquisition_date": "2024-01-01",
    }
    gaps = align(
        pack,
        holding,
        [_record(pack, "OBL-US-001")],
        _confirmed("H-2"),
        as_of=date(2026, 1, 2),
    )
    assert gaps[0].coverage == "indeterminate"
    assert course.plan(pack, gaps, owner="Reviewer") == []


def test_corridor_reasonable_period_does_not_invent_a_deadline():
    pack = load_interaction_packs(
        REPO_ROOT / "domains" / "interactions.yaml", base_path=REPO_ROOT
    )["india-ireland-corridor"]
    holding = {
        "holding_id": "H-3",
        "instrument_type": "foreign_bank_account",
        "jurisdiction": "India",
        "acquisition_date": "2019-01-01",
        "tax_residency_since": "2021-07-01",
        "citizenships": ["India"],
        "tax_residencies": ["Ireland"],
    }
    gaps = align(
        pack,
        holding,
        [_record(pack, "OBL-CORR-001")],
        _confirmed("H-3"),
        as_of=date(2022, 1, 1),
    )
    actions = course.plan(pack, gaps, owner="Reviewer")
    assert actions[0].deadline is None
    assert actions[0].escalated is True
    assert actions[0].escalation_reason == "No statutory date to derive a deadline from."
