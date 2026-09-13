from datetime import date

from tara import pipeline
from tara.agents import course
from tara.agents.compass import Determination

# Every test here exercises ANCHOR against HLD-001, which needs SQ-03
# answered to be CONFIRMED — ANCHOR now raises BandOrderError itself for
# anything else (see test_anchor_refuses_a_holding_compass_has_not_confirmed).
CONFIRMED_HLD_001 = {"SQ-03": False}


def _action(obligation_id="OBL-002", holding_id="HLD-001"):
    return course.Action(
        action_id=f"ACT-{obligation_id}-{holding_id}", obligation_id=obligation_id, holding_id=holding_id,
        owner="Synthetic Holder A", deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )


def test_anchor_closes_on_exact_arithmetic(ctx):
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4100.0}
    result = pipeline.verify_action(ctx, _action(), artefact, profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6))
    assert result.outcome == "closed"


def test_anchor_rejects_a_near_but_not_exact_computation(ctx):
    # A model eyeballing 4100 vs 4150 might call this "close enough" — ANCHOR must not.
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4150.0}
    result = pipeline.verify_action(ctx, _action(), artefact, profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6))
    assert result.outcome == "returned"
    assert "not accepted as approximately equal" in result.reason.lower()


def test_anchor_returns_on_missing_required_field(ctx):
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41}
    result = pipeline.verify_action(ctx, _action(), artefact, profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6))
    assert result.outcome == "returned"
    assert "computed_tax" in result.reason


def test_anchor_returns_on_wrong_artefact_type(ctx):
    artefact = {"artefact_type": "filed_return_receipt"}
    result = pipeline.verify_action(ctx, _action(), artefact, profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6))
    assert result.outcome == "returned"
    assert "wrong artefact type" in result.reason.lower()


def test_anchor_rejects_evidence_at_a_superseded_rate(ctx):
    # Internally consistent (4100 = 10000 * 0.41) but OBL-002B is the live
    # obligation and requires the 38% rate — ANCHOR must not close a
    # computation built on the rate Revenue superseded, even though the
    # arithmetic on its own is exact.
    action = _action(obligation_id="OBL-002B", holding_id="HLD-001")
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4100.0}
    result = pipeline.verify_action(ctx, action, artefact, profile_answers=CONFIRMED_HLD_001, as_of=date(2027, 4, 1))
    assert result.outcome == "returned"
    assert "does not match the 38% rate" in result.reason


def test_anchor_refuses_a_holding_compass_has_not_confirmed(ctx):
    # HLD-003 is direct_equity — COMPASS returns EXEMPT for it. ANCHOR must
    # never be reachable to close an obligation against an EXEMPT holding,
    # regardless of what artefact is submitted.
    from tara.agents.plot import BandOrderError

    action = _action(obligation_id="OBL-002B", holding_id="HLD-003")
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.38, "computed_tax": 3800.0}
    try:
        pipeline.verify_action(ctx, action, artefact, as_of=date(2027, 4, 1))
        assert False, "expected BandOrderError"
    except BandOrderError:
        pass


# OBL-005 (a "notify Revenue within 30 days of a jurisdiction/equivalent-
# measures change" obligation) was removed from domains/tax.yaml — its
# citation (a fictitious "Section 4.6") could not be verified against the
# real, currently-published Revenue Tax and Duty Manual Part 27-01A-02, and
# an unverifiable citation has no place in a pack this system presents as
# authoritative. ANCHOR's generic max_days_after_event mechanism it used to
# exercise is real and stays covered here — as a synthetic, explicitly-test-
# only evidence rule injected directly into the fixture's domain pack, so
# the mechanism is proven without the production pack asserting a fact
# nobody has verified.
_SYNTHETIC_NOTICE_RULE = {
    "artefact_type": "notification_confirmation",
    "required_fields": ["notice_date"],
    "max_days_after_event": 30,
    "lead_time_days": 0,
}


def test_anchor_enforces_30_day_notification_window(ctx):
    ctx.domain_pack.evidence_rules["OBL-TEST-NOTICE"] = _SYNTHETIC_NOTICE_RULE
    action = _action(obligation_id="OBL-TEST-NOTICE", holding_id="HLD-001")
    confirmed = Determination("HLD-001", "CONFIRMED", "test setup", None, None)
    late = {"artefact_type": "notification_confirmation", "notice_date": "2026-10-20"}
    # No real date_trigger backs this synthetic obligation, so trigger_date
    # is supplied directly — exercising the rule through anchor.verify with
    # an explicit trigger date rather than one derived from a domain pack.
    from tara.agents import anchor
    result = anchor.verify(ctx.domain_pack, action, late, confirmed, trigger_date="2026-09-06", atlas=ctx.atlas)
    assert result.outcome == "returned"
    assert "days after the event" in result.reason

    on_time = {"artefact_type": "notification_confirmation", "notice_date": "2026-09-20"}
    result = anchor.verify(ctx.domain_pack, action, on_time, confirmed, trigger_date="2026-09-06", atlas=ctx.atlas)
    assert result.outcome == "closed"


def test_anchor_returns_rather_than_closes_when_notification_window_cannot_be_checked(ctx):
    # If no trigger_date is available at all (the precondition event never
    # got recorded), ANCHOR must say so explicitly — never close silently.
    ctx.domain_pack.evidence_rules["OBL-TEST-NOTICE"] = _SYNTHETIC_NOTICE_RULE
    action = _action(obligation_id="OBL-TEST-NOTICE", holding_id="HLD-001")
    confirmed = Determination("HLD-001", "CONFIRMED", "test setup", None, None)
    from tara.agents import anchor
    artefact = {"artefact_type": "notification_confirmation", "notice_date": "2099-01-01"}
    result = anchor.verify(ctx.domain_pack, action, artefact, confirmed, trigger_date=None, atlas=ctx.atlas)
    assert result.outcome == "returned"
    assert "cannot verify" in result.reason.lower()


# ── Regression tests for the missing-operand crash (found 2026-09-12) ────────
# An artefact carrying exactly the fields tax.yaml's evidence rule for
# OBL-002B declares as required — rate_applied and computed_tax, no
# deemed_gain — used to raise KeyError inside ANCHOR's own failure-message
# construction, which the MCP server surfaced as an opaque
# "Error executing tool anchor_verify" with no ClosureResult at all. Every
# in-repo caller happened to pass deemed_gain, so nothing caught it until a
# real MCP client submitted only what the pack asked for.

def test_anchor_closes_when_artefact_omits_operands_the_pack_never_required(ctx):
    # OBL-002B's required_fields are [rate_applied, computed_tax]. An artefact
    # supplying exactly those must produce a ClosureResult, not an exception.
    artefact = {"artefact_type": "tax_computation", "rate_applied": 0.38, "computed_tax": 3800.0}
    result = pipeline.verify_action(
        ctx, _action(obligation_id="OBL-002B"), artefact,
        profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6),
    )
    assert result.outcome == "closed"


def test_anchor_still_returns_on_wrong_rate_without_operands(ctx):
    # The expected_rate check is independent of the arithmetic cross-check and
    # must keep firing when the operands are absent.
    artefact = {"artefact_type": "tax_computation", "rate_applied": 0.41, "computed_tax": 4100.0}
    result = pipeline.verify_action(
        ctx, _action(obligation_id="OBL-002B"), artefact,
        profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6),
    )
    assert result.outcome == "returned"
    assert "38%" in result.reason


def test_anchor_still_rejects_inexact_arithmetic_when_operands_are_present(ctx):
    # The fix must not weaken the exactness guarantee: supply the operands and
    # the cross-check still runs, and still refuses an approximate match.
    artefact = {
        "artefact_type": "tax_computation",
        "deemed_gain": 10000.0, "rate_applied": 0.38, "computed_tax": 3800.01,
    }
    result = pipeline.verify_action(
        ctx, _action(obligation_id="OBL-002B"), artefact,
        profile_answers=CONFIRMED_HLD_001, as_of=date(2026, 9, 6),
    )
    assert result.outcome == "returned"
    assert "not accepted as approximately equal" in result.reason.lower()
