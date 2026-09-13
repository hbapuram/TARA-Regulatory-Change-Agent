"""domains/ireland-irp.yaml — the second, non-tax domain pack proving TARA is
domain-agnostic, not a tax engine with an immigration label stuck on it.
Same agents, same pipeline, no code path added for this pack: these tests
exercise it exactly the way test_domain_pack.py, test_compass.py and
test_meridian.py exercise the tax/India/US packs, and add one thing those
don't need to prove — that an obligation with no published statutory
timeframe (OBL-IRP-003) is surfaced honestly as an escalation, not given an
invented deadline.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from tara import pipeline
from tara.core.domain_pack import load_domain_pack

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ireland_irp_pack(linked_ctx):
    return linked_ctx.linked_packs["ireland-irp"]


def test_ireland_irp_confirms_for_a_non_eea_swiss_uk_holder(linked_ctx):
    pack = _ireland_irp_pack(linked_ctx)
    determination = pipeline.determination_for(linked_ctx, "HLD-004", {}, domain_pack=pack)
    assert determination.status == "CONFIRMED"


def test_ireland_irp_exempts_an_eea_swiss_uk_holder(linked_ctx):
    """Same holder record, but scoped by an explicit profile_answers override
    the way SQ-03 (remittance basis) is elsewhere in this codebase — proves
    the scoping question, not the fixture data, drives the EXEMPT outcome.
    """
    pack = load_domain_pack(REPO_ROOT / "domains" / "ireland-irp.yaml")
    holding = dict(linked_ctx.holding("HLD-004"))
    holding["eea_swiss_uk_national"] = True
    from tara.agents import compass

    determination = compass.assess(pack, holding, {}, tenant_id="HLD-004-eea-test")
    assert determination.status == "EXEMPT"
    assert "EEA" in determination.reason or "EEA" in (pack.scoping_questions[0].fail_reason_template or "")


def test_initial_registration_uses_precomputed_one_time_due_date(linked_ctx):
    pack = _ireland_irp_pack(linked_ctx)
    determination, gaps = pipeline.gaps_for(linked_ctx, "HLD-004", {}, as_of=date(2026, 9, 10), domain_pack=pack)
    assert determination.status == "CONFIRMED"
    gap = next(g for g in gaps if g.obligation_id == "OBL-IRP-001")
    # register_register.json stores irp_registration_due_date precomputed as
    # arrival (2018-09-01) + 90 days -- this pack never adds days to a date
    # itself (DateTrigger is year-granularity only, see tara/core/dates.py),
    # so the source-of-truth value is on the register entry, not derived here.
    assert gap.trigger_date == "2018-11-30"


def test_renewal_deadline_is_the_real_expiry_date_not_an_assumed_annual_cycle(linked_ctx):
    """Two things this test guards against regressing to: (1) irp_expiry_date
    is a real fact on the register entry, not "acquisition_date + 1 year" --
    IRP terms vary and ISD guidance never states a fixed duration; (2) the
    84-day figure in ISD guidance is when the renewal window *opens* (the
    earliest you may apply), not a lead time to subtract from the deadline
    -- lead_time_days is 0, so the reported deadline is the actual statutory
    date (the expiry itself), not 84 days before it.
    """
    pack = _ireland_irp_pack(linked_ctx)
    determination, actions = pipeline.actions_for(linked_ctx, "HLD-004", {}, as_of=date(2026, 9, 10), domain_pack=pack)
    assert determination.status == "CONFIRMED"
    action = next(a for a in actions if a.obligation_id == "OBL-IRP-002")
    # registers/holder_register.json HLD-004.irp_expiry_date is 2026-09-15 --
    # a real, explicit fact, not derived from acquisition_date here.
    assert action.deadline == "2026-09-15"


def test_ireland_irp_exempts_an_unrelated_financial_holding(linked_ctx):
    """SQ-IRP-02 (instrument_type gate): without it, this standalone pack is
    a candidate for every holding_id the holder has, gated only by the
    eea_swiss_uk_national holder-level fact -- so it would confirm against
    HLD-001, a Luxembourg offshore fund, attaching IRP renewal/registration
    actions to a financial asset that has nothing to do with immigration.
    """
    pack = _ireland_irp_pack(linked_ctx)
    determination = pipeline.determination_for(linked_ctx, "HLD-001", {}, domain_pack=pack)
    assert determination.status == "EXEMPT"
    assert "instrument" in determination.reason.lower() or "immigration permission" in determination.reason.lower()


def test_change_of_address_has_no_invented_deadline(linked_ctx):
    """The one obligation this pack deliberately ships with no date_trigger
    -- ISD guidance doesn't publish a fixed notification window (see
    data/sources/ireland_irp_v1.txt, Section 1.3), and this pack does not
    make one up. COURSE must escalate it for a human, not silently assign
    it a deadline that doesn't exist in the source.
    """
    pack = _ireland_irp_pack(linked_ctx)
    determination, actions = pipeline.actions_for(linked_ctx, "HLD-004", {}, as_of=date(2026, 9, 10), domain_pack=pack)
    assert determination.status == "CONFIRMED"
    action = next(a for a in actions if a.obligation_id == "OBL-IRP-003")
    assert action.deadline is None
    assert action.escalated is True
    assert action.escalation_reason == "No statutory date to derive a deadline from."
