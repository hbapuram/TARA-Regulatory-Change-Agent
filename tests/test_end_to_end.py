"""The HR2/HR3 acceptance criteria from the architecture doc, run together:

  "an MCP client calls SURVEY and LEGEND and receives a structured, cited
  Chart from a real diff"

  "PLOT returns 2027-03-14 from a 2019-03-14 acquisition, ANCHOR rejects
  the equal-values computation, and ATLAS holds the full chain"
"""
from datetime import date

from tara import pipeline
from tara.agents import course


def test_the_chart_from_a_real_diff(ctx):
    obligations = pipeline.full_obligation_set(ctx)
    by_id = {o.obligation_id: o for o in obligations}
    assert by_id["OBL-002B"].provision == "Section 4.3"
    assert by_id["OBL-002B"].change_type == "amended"
    assert all(o.text for o in obligations)  # every obligation carries its own citation text


def test_plot_returns_2027_03_14_from_a_2019_03_14_acquisition(ctx):
    determination, gaps = pipeline.gaps_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 6))
    assert determination.status == "CONFIRMED"
    deemed_disposal_gap = next(g for g in gaps if g.obligation_id == "OBL-001")
    assert deemed_disposal_gap.trigger_date == "2027-03-14"


def test_anchor_rejects_the_equal_values_computation(ctx):
    action = course.Action(
        action_id="ACT-OBL-002-HLD-001", obligation_id="OBL-002", holding_id="HLD-001",
        owner="Synthetic Holder A", deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    almost_right = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4100.01}
    result = pipeline.verify_action(ctx, action, almost_right, profile_answers={"SQ-03": False}, as_of=date(2026, 9, 6))
    assert result.outcome == "returned"


def test_atlas_holds_the_full_chain(ctx):
    pipeline.actions_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2027, 4, 1))

    # Per-obligation chain: LEGEND decomposed it, PLOT found the gap, COURSE opened the action.
    chain = ctx.atlas.reconstruct("OBL-001")
    steps = [e["step"] for e in chain]
    assert "obligation_decomposed" in steps
    assert "gap_found" in steps
    assert "action_opened" in steps

    # COMPASS's applicability determination is scoped to the holding, not to
    # one obligation, so it's recorded separately under the tenant_id — but
    # it's still in the ledger, and the whole ledger is tamper-evident.
    all_steps = [e["step"] for e in ctx.atlas.all_entries()]
    assert "applicability_determined" in all_steps
    assert ctx.atlas.verify_chain() is True


def test_deliberately_unaffected_holding_is_exempt(ctx):
    determination, actions = pipeline.actions_for(ctx, "HLD-003", {}, as_of=date(2026, 9, 6))
    assert determination.status == "EXEMPT"
    assert actions == []
