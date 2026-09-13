import json
from datetime import date

from tara.agents import almanac
from tara.agents.compass import Determination
from tara.agents.course import Action

CONFIRMED_HLD_001 = Determination("HLD-001", "CONFIRMED", "test setup", None, None)


def test_first_refresh_seeds_the_graph_at_version_1(ctx):
    result = almanac.refresh(ctx.domain_pack, ctx.almanac_version_path, as_of=date(2026, 9, 6), atlas=ctx.atlas)
    assert result.version == 1
    markings = {g.obligation_id: g.marking for g in result.graph_diff}
    assert markings["OBL-002B"] == "added"
    # OBL-002 is superseded_by OBL-002B — a structural fact ALMANAC checks
    # fresh against the current pack, so it's marked "superseded" (not
    # simply absent) even on the very first refresh there has ever been,
    # with no prior version needing to have existed.
    assert markings["OBL-002"] == "superseded"
    assert all(c.reached for c in result.coverage)
    assert result.reopened == []  # no prior closure exists yet to reopen


def test_refresh_marks_supersession_and_reopens_a_closure(ctx):
    # Simulate: the last recorded refresh happened before OBL-002B existed —
    # the live graph then was the pre-change one, with the old OBL-002 in it.
    stale_graph = {
        "version": 1,
        "obligations": {
            oid: "stale-hash" for oid in ("OBL-001", "OBL-002", "OBL-003", "OBL-004")
        },
    }
    ctx.almanac_version_path.write_text(json.dumps(stale_graph))

    # And a tenant had already closed OBL-002 against the old 41% rate.
    from tara.agents import anchor
    action = Action(
        action_id="ACT-OBL-002-HLD-001", obligation_id="OBL-002", holding_id="HLD-001",
        owner="Synthetic Holder A", deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4100.0}
    closure = anchor.verify(ctx.domain_pack, action, artefact, CONFIRMED_HLD_001, trigger_date="2027-03-14", atlas=ctx.atlas)
    assert closure.outcome == "closed"

    result = almanac.refresh(ctx.domain_pack, ctx.almanac_version_path, as_of=date(2026, 9, 6), atlas=ctx.atlas)

    assert result.version == 2
    markings = {g.obligation_id: g.marking for g in result.graph_diff}
    assert markings["OBL-002"] == "superseded"
    assert markings["OBL-002B"] == "added"
    # The stale fixture graph used a placeholder hash for every obligation,
    # so real obligations compare unequal to it and show as "amended" —
    # this is a fixture artefact, not a real content change.
    assert markings["OBL-001"] == "amended"


def test_refresh_reopens_the_superseded_closure(ctx):
    stale_graph = {
        "version": 1,
        "obligations": {oid: "stale-hash" for oid in ("OBL-001", "OBL-002", "OBL-003", "OBL-004")},
    }
    ctx.almanac_version_path.write_text(json.dumps(stale_graph))

    from tara.agents import anchor
    action = Action(
        action_id="ACT-OBL-002-HLD-001", obligation_id="OBL-002", holding_id="HLD-001",
        owner="Synthetic Holder A", deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4100.0}
    anchor.verify(ctx.domain_pack, action, artefact, CONFIRMED_HLD_001, trigger_date="2027-03-14", atlas=ctx.atlas)

    result = almanac.refresh(ctx.domain_pack, ctx.almanac_version_path, as_of=date(2026, 9, 6), atlas=ctx.atlas)

    assert len(result.reopened) == 1
    assert result.reopened[0]["obligation_id"] == "OBL-002"
    assert result.reopened[0]["holding_id"] == "HLD-001"

    chain = ctx.atlas.reconstruct("OBL-002")
    steps = [e["step"] for e in chain]
    assert steps == ["closure", "reopened"]
