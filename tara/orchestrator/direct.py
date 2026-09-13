"""The --direct fallback: runs the full pipeline without an MCP client and
without any model call. If the MCP server is broken on demo day, this is
what keeps the run alive — same agents, same pipeline module, just called
in-process instead of over MCP.

This is also the natural place to exercise the whole system end to end
while OPENAI_API_KEY isn't configured yet (Phase 1): everything below is
deterministic Python, so none of it needs the orchestrator model.
"""
from __future__ import annotations

from datetime import date

from pathlib import Path

from .. import pipeline
from ..agents import almanac, course, meridian
from ..mcp_server.context import REPO_ROOT, TaraContext, build_context

BAND = {
    "SURVEY": "OPEN", "LEGEND": "OPEN", "ALMANAC": "OPEN",
    "COMPASS": "TENANT", "PLOT": "TENANT", "COURSE": "TENANT", "ANCHOR": "TENANT",
    "MERIDIAN": "TENANT",
    "ATLAS": "LINEAGE",
}

# Same standalone packs plus the same interactions store the MCP server
# loads by default (see tara/mcp_server/server.py::DEFAULT_LINKED_DOMAIN_YAMLS
# / DEFAULT_INTERACTIONS_YAML) — India, the US, and the India-Ireland
# corridor (synthesized from domains/interactions.yaml), alongside the
# primary Ireland pack. The --direct demo exercises the identical
# multi-jurisdiction context a real MCP client would get.
LINKED_DOMAIN_YAMLS: list[str | Path] = [
    REPO_ROOT / "domains" / "india.yaml",
    REPO_ROOT / "domains" / "us.yaml",
    REPO_ROOT / "domains" / "ireland-irp.yaml",
    REPO_ROOT / "domains" / "india-nri-securities.yaml",
]
INTERACTIONS_YAML: Path = REPO_ROOT / "domains" / "interactions.yaml"


def _line(agent: str, message: str) -> str:
    return f"[{BAND[agent]:7s}] {agent:8s} {message}"


def run_demo(as_of: date | None = None) -> None:
    ctx: TaraContext = build_context(
        linked_domain_yamls=LINKED_DOMAIN_YAMLS, interactions_yaml=INTERACTIONS_YAML
    )
    as_of = as_of or date.today()

    print("=" * 78)
    print(f"TARA — direct pipeline demo ({ctx.domain_pack.title})")
    print("=" * 78)

    # ---- open band: the Chart -------------------------------------------------
    obligations = pipeline.full_obligation_set(ctx)
    print(_line("SURVEY", "diffed configured source(s); see ATLAS for the raw provision diff"))
    print(_line("LEGEND", f"decomposed {len(obligations)} live obligation(s):"))
    for o in obligations:
        print(f"           {o.obligation_id}  {o.provision}  [{o.change_type}]  {o.text[:70]}")

    # ---- tenant band: one holding at a time -----------------------------------
    # SQ-03 (remittance basis) is deliberately absent from the register, so
    # COMPASS is asked for it explicitly here — demonstrating the "ask for
    # missing facts" requirement rather than the system guessing.
    profiles = {
        "HLD-001": {"SQ-03": False},
        "HLD-002": {"SQ-03": False},
        "HLD-003": {},
    }

    for holding in ctx.register["holdings"]:
        holding_id = holding["holding_id"]
        determination, actions = pipeline.actions_for(
            ctx, holding_id, profiles.get(holding_id, {}), as_of=as_of
        )
        print()
        print(f"--- {holding_id} ({holding['instrument_type']}, acquired {holding['acquisition_date']}) ---")
        print(_line("COMPASS", f"{determination.status} — {determination.reason}"))

        if determination.status != "CONFIRMED":
            continue

        for action in actions:
            flag = " [ESCALATED]" if action.escalated else ""
            print(_line("COURSE", f"{action.action_id}  due {action.deadline}  owner={action.owner}{flag}"))

    # ---- ANCHOR: one accepted artefact, one rejected on exact-value grounds ---
    # OBL-002B, not OBL-002 — OBL-002 is superseded (see LEGEND's output
    # above, which already excludes it) and its 41% rate is exactly what
    # ANCHOR must now refuse for this obligation.
    print()
    print("--- ANCHOR: evidence verification ---")
    accepted_action = course.Action(
        action_id="ACT-OBL-002B-HLD-001", obligation_id="OBL-002B", holding_id="HLD-001",
        owner=ctx.owner_name(), deadline=None, required_evidence_type="tax_computation",
        depends_on=(), escalated=False, escalation_reason=None,
    )
    good_artefact = {
        "artefact_type": "tax_computation",
        "deemed_gain": 10000.0,
        "rate_applied": 0.38,
        "computed_tax": 3800.0,
    }
    result = pipeline.verify_action(ctx, accepted_action, good_artefact, profile_answers={"SQ-03": False}, as_of=as_of)
    print(_line("ANCHOR", f"{result.outcome.upper()} — {result.reason}"))

    bad_artefact = {
        "artefact_type": "tax_computation",
        "deemed_gain": 10000.0,
        "rate_applied": 0.38,
        "computed_tax": 3850.0,  # off by 50 — a model eyeballing this might call it "close enough"
    }
    result = pipeline.verify_action(ctx, accepted_action, bad_artefact, profile_answers={"SQ-03": False}, as_of=as_of)
    print(_line("ANCHOR", f"{result.outcome.upper()} — {result.reason}"))

    # ---- MERIDIAN: cross-jurisdiction survey -----------------------------------
    # HLD-001's holder is a synthetic corridor case: an Indian citizen who is
    # Irish tax resident (registers/holder_register.json). MERIDIAN runs the
    # exact same COMPASS/PLOT/COURSE pipeline above against every linked
    # pack — India and the US independently, standalone, plus the
    # India-Ireland corridor, which only applies because both facts are true
    # at once. Nothing here is special-cased for these three countries;
    # add a fourth domains/*.yaml and it appears in this loop for free.
    print()
    print("--- MERIDIAN: cross-jurisdiction survey (HLD-001) ---")
    report = meridian.survey(ctx, "HLD-001", {"SQ-03": False}, as_of=as_of)
    for r in report.results:
        tag = "corridor" if r.is_corridor else "standalone"
        if not r.considered:
            print(_line("MERIDIAN", f"{r.domain_id:24s} ({tag:10s}) skipped — {r.skipped_reason}"))
            continue
        det = r.determination
        print(_line("MERIDIAN", f"{r.domain_id:24s} ({tag:10s}) {det.status:12s} {len(r.actions)} action(s) — {det.reason}"))

    # HLD-004's initial registration (OBL-IRP-001) fell due in 2018 — a real
    # holder of a current 2025-granted permission plainly registered
    # initially at some point, so this closes that historical obligation
    # against a submitted artefact rather than leaving the demo showing it
    # as permanently "overdue since 2018, no evidence" alongside a holding
    # that's obviously in good standing. Same ANCHOR mechanism as the
    # tax.yaml closures above, called against the ireland-irp pack instead.
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
    irp_registration_result = pipeline.verify_action(
        ctx, irp_registration_action, irp_registration_evidence,
        profile_answers={}, as_of=as_of, domain_pack=irp_pack,
    )
    print(_line("ANCHOR", f"{irp_registration_result.outcome.upper()} — {irp_registration_result.reason}"))

    # HLD-004 is the immigration-permission holding domains/ireland-irp.yaml
    # was written for — a second, non-tax domain pack (Public Administration
    # & Immigration, not Finance & Insurance) reusing every existing agent
    # unmodified. Surveying it here, separately from HLD-001's financial
    # holdings, is what makes ireland-irp's three obligations legible on
    # their own terms: initial registration (now closed, above), renewal
    # (a real expiry date on the register entry, not an assumed annual
    # cycle — see the pack's own header), and change-of-address
    # (deliberately no date_trigger — same header, same reasoning as the
    # earlier Form 67 fabrication this engagement already caught once).
    print()
    print("--- MERIDIAN: second domain pack, same agents (HLD-004 — Irish Residence Permit) ---")
    irp_report = meridian.survey(ctx, "HLD-004", {}, as_of=as_of)
    for r in irp_report.results:
        tag = "corridor" if r.is_corridor else "standalone"
        if not r.considered:
            print(_line("MERIDIAN", f"{r.domain_id:24s} ({tag:10s}) skipped — {r.skipped_reason}"))
            continue
        det = r.determination
        print(_line("MERIDIAN", f"{r.domain_id:24s} ({tag:10s}) {det.status:12s} {len(r.actions)} action(s) — {det.reason}"))
        if r.domain_id == "ireland-irp":
            for action in r.actions:
                flag = " [ESCALATED — no statutory date to derive a deadline from]" if action.escalated else ""
                print(_line("COURSE", f"{action.action_id}  due {action.deadline}{flag}"))

    # ---- ALMANAC: refresh cycle -------------------------------------------------
    print()
    print("--- ALMANAC: refresh cycle ---")
    refresh_result = almanac.refresh(ctx.domain_pack, ctx.almanac_version_path, as_of=as_of, atlas=ctx.atlas)
    print(_line("ALMANAC", f"Chart version {refresh_result.version}"))
    for c in refresh_result.coverage:
        print(f"           coverage: {c.source_id}  reached={c.reached}  changed={c.changed}  stale={c.stale}")
    for g in refresh_result.graph_diff:
        print(f"           graph diff: {g.obligation_id}  -> {g.marking}")
    for r in refresh_result.reopened:
        print(f"           reopened: {r['obligation_id']} / {r['holding_id']} — {r['reason']}")

    # ---- ATLAS: reconstruct one chain ------------------------------------------
    print()
    print("--- ATLAS: reconstructed chain for OBL-001 ---")
    chain = ctx.atlas.reconstruct("OBL-001")
    for entry in chain:
        print(f"           #{entry['seq']:03d} {entry['agent']:8s} {entry['step']}")
    print(f"           chain verified: {ctx.atlas.verify_chain()}")


if __name__ == "__main__":
    run_demo()
