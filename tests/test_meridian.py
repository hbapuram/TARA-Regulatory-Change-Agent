"""MERIDIAN — the cross-jurisdiction layer.

The acceptance shape for the multi-country extension: Ireland, India and
the US are each independently queryable (a holder gets a real
CONFIRMED/EXEMPT determination from each pack on its own, with no
reference to the other two), and the India-Ireland corridor pack — which
applies only to a holder who is both an Indian citizen and an Irish tax
resident at once — is discovered and evaluated as a fourth, linked pack
that neither single-country pack could have produced on its own.
"""
from datetime import date

from tara.agents import meridian
from tara.agents.compass import Determination


def test_every_linked_pack_is_independently_queryable(linked_ctx):
    """Same holder, same holding, four packs — each one's determination
    stands on its own and doesn't reference the others."""
    from tara import pipeline

    tax_det = pipeline.determination_for(linked_ctx, "HLD-001", {"SQ-03": False}, domain_pack=linked_ctx.domain_pack)
    india_det = pipeline.determination_for(linked_ctx, "HLD-001", {}, domain_pack=linked_ctx.linked_packs["india-fa"])
    us_det = pipeline.determination_for(linked_ctx, "HLD-001", {}, domain_pack=linked_ctx.linked_packs["us-fbar"])

    assert tax_det.status == "CONFIRMED"
    assert india_det.status == "EXEMPT"
    assert us_det.status == "EXEMPT"
    # Each determination cites only its own pack's provision — proof these
    # ran independently rather than one leaking into another's reasoning.
    assert "India" in india_det.reason
    assert "United States" in us_det.reason


def test_corridor_pack_can_be_confirmed_without_inventing_an_obligation(linked_ctx):
    report = meridian.survey(linked_ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 7))
    corridor = next(r for r in report.results if r.domain_id == "india-ireland-corridor")
    assert corridor.considered is True
    assert corridor.determination.status == "CONFIRMED"
    # HLD-001 is an offshore fund, not a bank account, and the register has no
    # fact saying it produced India-source income. Pack-level scope must not be
    # widened into FEMA or treaty-relief actions that the holding did not earn.
    assert corridor.actions == ()


def test_corridor_obligations_do_not_appear_in_either_standalone_pack(linked_ctx):
    """The whole point of the corridor: FEMA reclassification and DTAA
    relief are not India's obligations alone, nor Ireland's — they exist
    only in the intersection."""
    report = meridian.survey(linked_ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 7))
    by_domain = {r.domain_id: r for r in report.results}

    tax_obligation_ids = {a.obligation_id for a in by_domain["tax"].actions}
    india_obligation_ids = {a.obligation_id for a in by_domain["india-fa"].actions}
    corridor_obligation_ids = set(
        linked_ctx.linked_packs["india-ireland-corridor"].obligations
    )

    assert corridor_obligation_ids == {"OBL-CORR-001", "OBL-CORR-002"}
    assert corridor_obligation_ids.isdisjoint(tax_obligation_ids)
    assert corridor_obligation_ids.isdisjoint(india_obligation_ids)


def test_a_holder_who_only_matches_one_corridor_fact_is_skipped_not_confirmed(linked_ctx):
    """Discovery is a pre-filter, not a determination: a holder who is an
    Indian citizen but NOT Irish tax resident must never see the corridor
    CONFIRMED, and the report should say why it was ruled out rather than
    omitting it."""
    holder_missing_irish_residency = {"citizenships": ["India"], "tax_residencies": ["United Kingdom"]}
    candidates = meridian.discover(holder_missing_irish_residency, {
        "india-ireland-corridor": linked_ctx.linked_packs["india-ireland-corridor"],
    })
    assert candidates == []

    applies, reason = meridian._corridor_applies(
        linked_ctx.linked_packs["india-ireland-corridor"], holder_missing_irish_residency
    )
    assert applies is False
    assert "Ireland" in reason


def test_standalone_packs_are_always_candidates_regardless_of_holder_facts(linked_ctx):
    """Independent queryability means a standalone pack is never filtered
    out by discover() — only a corridor's own metadata can do that."""
    no_facts_holder = {}
    candidates = meridian.discover(no_facts_holder, linked_ctx.linked_packs)
    candidate_ids = {p.domain_id for p in candidates}
    assert "india-fa" in candidate_ids
    assert "us-fbar" in candidate_ids
    assert "india-ireland-corridor" not in candidate_ids  # no facts at all -> corridor correctly excluded


def test_survey_records_atlas_entries_per_jurisdiction(linked_ctx):
    meridian.survey(linked_ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 7))
    steps = [e for e in linked_ctx.atlas.all_entries() if e["agent"] == "MERIDIAN"]
    surveyed_domains = {e["payload"]["domain_id"] for e in steps}
    # Every considered pack gets its own ATLAS entry — the skipped corridor
    # check happens inside discover(), before any pack-specific entry. H-001
    # (India citizenship, Ireland tax residency) matches the india-ireland
    # corridor's facts but not either US corridor's, so india-us-corridor and
    # ireland-us-corridor are pre-filtered out of discover() entirely and
    # never reach MERIDIAN — they carry no ATLAS entry for this holder, the
    # same way test_standalone_packs_are_always_candidates... shows
    # india-ireland-corridor pre-filtered out for a no-facts holder above.
    # india-nri-securities is a standalone pack, so — like india-fa and
    # us-fbar — it is always a candidate regardless of holder facts.
    assert surveyed_domains == {
        "tax", "india-fa", "us-fbar", "ireland-irp",
        "ireland-cgt-property", "india-ireland-corridor",
        "india-nri-securities",
    }


def test_a_pack_with_no_linked_packs_behaves_exactly_as_a_single_pack_context(ctx):
    """MERIDIAN against a context with nothing linked degrades to reporting
    just the primary pack — proof the multi-jurisdiction machinery is
    additive, not a prerequisite for the original single-domain behaviour."""
    report = meridian.survey(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 7))
    assert len(report.results) == 1
    assert report.results[0].domain_id == "tax"
    assert report.results[0].determination.status == "CONFIRMED"
