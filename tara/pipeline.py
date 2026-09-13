"""Cross-agent wiring shared by the MCP server and the --direct CLI.

This is the one place that calls agents in sequence, and it is what
enforces band order structurally: COMPASS always runs before PLOT, PLOT
always runs before COURSE, regardless of what a caller (human, script, or
an LLM orchestrator) asks for. An MCP tool or CLI command can only reach a
tenant-band agent by going through here.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .agents import anchor, compass, course, legend, plot, survey
from .agents.compass import Determination
from .agents.course import Action
from .agents.legend import ObligationRecord
from .agents.plot import GapEntry
from .core.domain_pack import DomainPack
from .mcp_server.context import TaraContext


def full_obligation_set(ctx: TaraContext, domain_pack: DomainPack | None = None) -> list[ObligationRecord]:
    """SURVEY + LEGEND across every configured source.

    Historical obligations remain in the set because a later rule does not
    retroactively replace the rule that applied to an earlier event. PLOT
    selects the applicable version from each obligation's effective window
    and the holding's resolved trigger date.

    ``domain_pack`` defaults to ``ctx.domain_pack`` — every existing caller
    is unaffected. MERIDIAN passes a different pack from ``ctx.linked_packs``
    to run this same open-band step against a second or third jurisdiction,
    with no change to SURVEY or LEGEND themselves.
    """
    domain_pack = domain_pack or ctx.domain_pack
    records: list[ObligationRecord] = []
    for source_id in domain_pack.sources:
        change_record = survey.detect_change(domain_pack, source_id, atlas=ctx.atlas)
        records.extend(legend.decompose(domain_pack, change_record, atlas=ctx.atlas))

    return records


def determination_for(
    ctx: TaraContext,
    holding_id: str,
    profile_answers: dict[str, Any],
    domain_pack: DomainPack | None = None,
) -> Determination:
    domain_pack = domain_pack or ctx.domain_pack
    holding = ctx.holding(holding_id)
    return compass.assess(
        domain_pack,
        holding,
        profile_answers,
        tenant_id=holding_id,
        cache=ctx.determination_cache,
        atlas=ctx.atlas,
    )


def gaps_for(
    ctx: TaraContext,
    holding_id: str,
    profile_answers: dict[str, Any],
    as_of: date | None = None,
    domain_pack: DomainPack | None = None,
) -> tuple[Determination, list[GapEntry]]:
    domain_pack = domain_pack or ctx.domain_pack
    determination = determination_for(ctx, holding_id, profile_answers, domain_pack=domain_pack)
    if determination.status != "CONFIRMED":
        return determination, []

    holding = ctx.holding(holding_id)
    obligations = full_obligation_set(ctx, domain_pack=domain_pack)
    gaps = plot.align(domain_pack, holding, obligations, determination, as_of=as_of, atlas=ctx.atlas)
    return determination, gaps


def actions_for(
    ctx: TaraContext,
    holding_id: str,
    profile_answers: dict[str, Any],
    as_of: date | None = None,
    domain_pack: DomainPack | None = None,
) -> tuple[Determination, list[Action]]:
    domain_pack = domain_pack or ctx.domain_pack
    determination, gaps = gaps_for(ctx, holding_id, profile_answers, as_of=as_of, domain_pack=domain_pack)
    if determination.status != "CONFIRMED":
        return determination, []
    actions = course.plan(domain_pack, gaps, owner=ctx.owner_name(), atlas=ctx.atlas)
    return determination, actions


def trigger_date_for_action(
    ctx: TaraContext, action: Action, as_of: date | None = None, domain_pack: DomainPack | None = None
) -> str | None:
    """Recomputes the same trigger date PLOT derived the action's deadline
    from — used by ANCHOR to check evidence timing rules (e.g. the 30-day
    notification window) without re-deriving it differently.
    """
    domain_pack = domain_pack or ctx.domain_pack
    holding = ctx.holding(action.holding_id)
    resolved = plot._trigger_date_for(domain_pack, action.obligation_id, holding, as_of or date.today())
    return resolved[0] if resolved is not None else None


def verify_action(
    ctx: TaraContext,
    action: Action,
    artefact: dict[str, Any],
    profile_answers: dict[str, Any] | None = None,
    as_of: date | None = None,
    domain_pack: DomainPack | None = None,
):
    """Runs COMPASS for this holding before handing anything to ANCHOR — the
    same band-order guarantee gaps_for/actions_for give PLOT/COURSE. ANCHOR
    also checks this determination itself (see anchor.verify), so the guard
    holds even for a caller that reaches ANCHOR by some other path; this
    call is what supplies a real, freshly-computed determination rather than
    an incidental one.
    """
    domain_pack = domain_pack or ctx.domain_pack
    determination = determination_for(ctx, action.holding_id, profile_answers or {}, domain_pack=domain_pack)
    trigger_date = trigger_date_for_action(ctx, action, as_of=as_of, domain_pack=domain_pack)
    return anchor.verify(
        domain_pack, action, artefact, determination, trigger_date=trigger_date, atlas=ctx.atlas
    )
