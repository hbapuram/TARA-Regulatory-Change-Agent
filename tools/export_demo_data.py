"""Runs the full deterministic pipeline and dumps a single JSON snapshot for
the static dashboard (tools/dashboard.html) — no server, no model.

The "OBL-002 superseded by OBL-002B, and HLD-001's prior closure against it
reopens" story below is produced by a real, cold refresh — not seeded.
ALMANAC detects supersession structurally, straight from the domain pack's
own supersedes/superseded_by links, so it fires on the very first refresh
this script ever runs: no fixture "previous version" needs to be faked.
The only thing staged is the *closure* itself — a tenant really did close
OBL-002 at the 41% rate before this script's one refresh call runs, so
there is a real closure on record for ALMANAC to find and reopen.
Everything else runs cold, exactly as `tara demo` does.

Regenerate with:
    python tools/export_demo_data.py > tools/demo_data.json
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tara import pipeline  # noqa: E402
from tara.agents import almanac, course, meridian  # noqa: E402
from tara.mcp_server.context import build_context  # noqa: E402

AS_OF = date(2027, 4, 1)  # past the 2027-03-14 acceptance-criterion trigger

LINKED_DOMAIN_YAMLS = [
    REPO_ROOT / "domains" / "india.yaml",
    REPO_ROOT / "domains" / "us.yaml",
    REPO_ROOT / "domains" / "ireland-irp.yaml",
]
INTERACTIONS_YAML = REPO_ROOT / "domains" / "interactions.yaml"


def build_snapshot() -> dict:
    ctx = build_context(
        atlas_path=REPO_ROOT / "tools" / "_demo_atlas_log.jsonl",
        almanac_version_path=REPO_ROOT / "tools" / "_demo_graph_version.json",
        linked_domain_yamls=LINKED_DOMAIN_YAMLS,
        interactions_yaml=INTERACTIONS_YAML,
    )
    ctx.atlas.path.write_text("")  # start clean each run

    # A tenant had already closed OBL-002 before this script's one (real,
    # cold) refresh call runs — under the 41% rate, which OBL-002's own
    # evidence rule still expects, since it's a genuinely historical
    # closure made when that was the current obligation.
    prior_closure_action = course.Action(
        action_id="ACT-OBL-002-HLD-001", obligation_id="OBL-002", holding_id="HLD-001",
        owner="Synthetic Holder A", deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    prior_artefact = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.41, "computed_tax": 4100.0}
    pipeline.verify_action(ctx, prior_closure_action, prior_artefact, profile_answers={"SQ-03": False}, as_of=AS_OF)

    obligations = pipeline.full_obligation_set(ctx)

    holdings_out = []
    for holding in ctx.register["holdings"]:
        holding_id = holding["holding_id"]
        profile = {"SQ-03": False} if holding_id != "HLD-003" else {}
        determination, actions = pipeline.actions_for(ctx, holding_id, profile, as_of=AS_OF)
        _det2, gaps = pipeline.gaps_for(ctx, holding_id, profile, as_of=AS_OF)
        holdings_out.append({
            "holding": holding,
            "determination": determination.as_dict(),
            "gaps": [g.as_dict() for g in gaps],
            "actions": [a.as_dict() for a in actions],
        })

    # ANCHOR demo, on a separate obligation instance so it doesn't disturb
    # the reopening story above: one exact match (closes), one near-miss.
    demo_action = course.Action(
        action_id="ACT-OBL-002B-HLD-002", obligation_id="OBL-002B", holding_id="HLD-002",
        owner=ctx.owner_name(), deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    good = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.38, "computed_tax": 3800.0}
    bad = {"artefact_type": "tax_computation", "deemed_gain": 10000.0, "rate_applied": 0.38, "computed_tax": 3850.0}
    anchor_demo = {
        "accepted": pipeline.verify_action(ctx, demo_action, good, profile_answers={"SQ-03": False}, as_of=AS_OF).as_dict(),
        "rejected": pipeline.verify_action(ctx, demo_action, bad, profile_answers={"SQ-03": False}, as_of=AS_OF).as_dict(),
    }

    # HLD-004's initial IRP registration (OBL-IRP-001) fell due in 2018 —
    # close it against a submitted artefact, same as the OBL-002/OBL-002B
    # closures above, so the dashboard doesn't show a permanently-overdue
    # 2018 registration sitting next to a holding that's obviously a
    # currently-held, in-good-standing permission. Mirrors direct.py's
    # --direct demo exactly, so both surfaces tell the same story.
    irp_pack = ctx.linked_packs["ireland-irp"]
    irp_registration_action = course.Action(
        action_id="ACT-OBL-IRP-001-HLD-004", obligation_id="OBL-IRP-001", holding_id="HLD-004",
        owner=ctx.owner_name(), deadline=None, required_evidence_type="irp_initial_registration",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    irp_registration_evidence = {
        "artefact_type": "irp_initial_registration",
        "registration_date": "2018-11-20",
        "irp_number": "IRP-0000000",
    }
    irp_anchor_demo = pipeline.verify_action(
        ctx, irp_registration_action, irp_registration_evidence,
        profile_answers={}, as_of=AS_OF, domain_pack=irp_pack,
    ).as_dict()

    refresh_result = almanac.refresh(ctx.domain_pack, ctx.almanac_version_path, as_of=AS_OF, atlas=ctx.atlas)

    atlas_chain_obl_001 = ctx.atlas.reconstruct("OBL-001")
    atlas_chain_obl_002 = ctx.atlas.reconstruct("OBL-002")

    # Every source's own monitoring history — reached/unreached and the
    # sha256 of exactly what was read, each time it was checked — kept
    # separate from any single obligation's chain. This is the direct
    # answer to "where's the record of sources accessed and monitored":
    # AtlasStore.entries_for_source() reads it back independent of what
    # LEGEND/COMPASS/etc. later did with the content.
    source_access_log = {
        source_id: ctx.atlas.entries_for_source(source_id)
        for source_id in ctx.domain_pack.sources
    }

    # MERIDIAN: the same holder (HLD-001's holder is an Indian citizen,
    # Irish tax resident) surveyed across every linked pack — Ireland
    # (the primary pack, already computed above), India and the US
    # standalone, and the India-Ireland corridor. This is what the
    # dashboard's "Cross-Jurisdiction" section renders.
    cross_jurisdiction = meridian.survey(ctx, "HLD-001", {"SQ-03": False}, as_of=AS_OF)

    # Second domain pack, same agents, its own holding: HLD-004 is the
    # immigration-permission entry domains/ireland-irp.yaml was written for.
    # Surveyed separately from HLD-001's financial holdings so ireland-irp's
    # three obligations render legibly on their own terms rather than mixed
    # in with (or, pre-fix, wrongly attached to) an unrelated offshore fund.
    cross_jurisdiction_irp = meridian.survey(ctx, "HLD-004", {}, as_of=AS_OF)

    return {
        "domain": {
            "domain_id": ctx.domain_pack.domain_id,
            "title": ctx.domain_pack.title,
            "sector": ctx.domain_pack.sector,
        },
        "as_of": AS_OF.isoformat(),
        "obligations": [o.as_dict() for o in obligations],
        "holdings": holdings_out,
        "anchor_demo": anchor_demo,
        "almanac": refresh_result.as_dict(),
        "atlas_chain_obl_001": atlas_chain_obl_001,
        "atlas_chain_obl_002": atlas_chain_obl_002,
        "source_access_log": source_access_log,
        "atlas_verified": ctx.atlas.verify_chain(),
        "atlas_total_entries": len(ctx.atlas.all_entries()),
        "cross_jurisdiction": cross_jurisdiction.as_dict(),
        "cross_jurisdiction_irp": cross_jurisdiction_irp.as_dict(),
        "irp_anchor_demo": irp_anchor_demo,
        "linked_domains": [
            {"domain_id": p.domain_id, "title": p.title, "is_corridor": p.is_corridor}
            for p in [ctx.domain_pack, *ctx.linked_packs.values()]
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build_snapshot(), indent=2, sort_keys=True))
