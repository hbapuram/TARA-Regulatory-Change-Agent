"""MERIDIAN — Multi-jurisdiction Evaluation of Reciprocal Instruments,
Duties & Agreements.  TENANT · computed per customer.

    survey(ctx, holding_id, profile_answers) -> CrossJurisdictionReport

The layer above independent, single-jurisdiction packs. Every domain pack
(``tax.yaml``, ``india.yaml``, ``us.yaml``, ...) is already independently
queryable on its own — that is just running the ordinary tenant pipeline
(COMPASS -> PLOT -> COURSE) against one pack, which every agent already
does. What was missing is the second layer: a holder who carries facts
across more than one of those jurisdictions at once (an Indian citizen who
is also an Irish tax resident) has obligations that belong to neither
country's own guidance alone — they exist only in the intersection. A
*corridor* pack (see ``DomainPack.is_corridor``) is where that intersection
is catalogued; MERIDIAN's job is to notice when a holder's facts make one
apply, and to fold it into one cross-jurisdiction report alongside every
standalone pack.

MERIDIAN adds no new applicability, alignment or scheduling logic of its
own. ``discover()`` below is pure filtering over already-loaded domain
packs and a holder's already-recorded facts; every actual determination
comes from calling ``compass.assess`` / ``plot.align`` / ``course.plan`` —
through ``pipeline``'s existing, band-order-enforcing wiring — once per
candidate pack, exactly as COMPASS, PLOT and COURSE already run for the
single-pack case. This is only possible because those functions already
take ``domain_pack`` as an explicit argument rather than reading it off a
shared global: MERIDIAN can hand them a different pack on each call without
either module changing. Nothing about "which countries" is hard-coded here
either — the candidate set is whatever packs are loaded into
``ctx.linked_packs``, so a fourth country is a fourth YAML file, not a
change to this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from ..core.domain_pack import DomainPack
from .compass import Determination
from .course import Action

if TYPE_CHECKING:
    from ..mcp_server.context import TaraContext


@dataclass(frozen=True)
class JurisdictionResult:
    """One linked pack's outcome for one holding — the same shape a
    single-pack caller already gets from ``pipeline.actions_for``, just
    tagged with which pack it came from so a cross-jurisdiction report can
    tell them apart.
    """
    domain_id: str
    title: str
    is_corridor: bool
    considered: bool          # False if discover() filtered this pack out entirely
    determination: Determination | None
    actions: tuple[Action, ...]
    skipped_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "title": self.title,
            "is_corridor": self.is_corridor,
            "considered": self.considered,
            "determination": self.determination.as_dict() if self.determination else None,
            "actions": [a.action_id for a in self.actions],
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True)
class CrossJurisdictionReport:
    holding_id: str
    results: tuple[JurisdictionResult, ...]

    @property
    def confirmed(self) -> tuple[JurisdictionResult, ...]:
        return tuple(r for r in self.results if r.determination is not None and r.determination.status == "CONFIRMED")

    def as_dict(self) -> dict[str, Any]:
        return {
            "holding_id": self.holding_id,
            "results": [r.as_dict() for r in self.results],
        }


def _corridor_applies(pack: DomainPack, holder: dict[str, Any]) -> tuple[bool, str | None]:
    """The discovery pre-filter: does this holder even carry the two facts
    a corridor pack's metadata names? This is deliberately cheaper and
    coarser than COMPASS's own scoping_questions (which still run
    afterwards, unmodified, for any pack that passes this filter) — it only
    decides whether trying the pack is worth it at all, never CONFIRMED on
    its own.
    """
    if not pack.is_corridor:
        return True, None
    citizenship_needed = pack.corridor.get("citizenship_of")
    residency_needed = pack.corridor.get("tax_residency_of")
    citizenships = holder.get("citizenships") or []
    tax_residencies = holder.get("tax_residencies") or []
    if citizenship_needed and citizenship_needed not in citizenships:
        return False, (
            f"Corridor requires citizenship of {citizenship_needed!r}; "
            f"holder's citizenships are {citizenships!r}."
        )
    if residency_needed and residency_needed not in tax_residencies:
        return False, (
            f"Corridor requires tax residency of {residency_needed!r}; "
            f"holder's tax residencies are {tax_residencies!r}."
        )
    return True, None


def discover(holder: dict[str, Any], candidate_packs: dict[str, DomainPack]) -> list[DomainPack]:
    """Every standalone pack is always a candidate — a holder can always ask
    "what does this jurisdiction require of me", independent of any other
    fact about them, which is the whole point of independent queryability.
    A corridor pack is a candidate only when the holder's own recorded
    facts match what it names in ``corridor``; otherwise trying it would
    just be noise (an EXEMPT from a corridor that could never have applied)
    rather than a real finding.
    """
    return [
        pack for pack in candidate_packs.values()
        if _corridor_applies(pack, holder)[0]
    ]


def survey(
    ctx: "TaraContext",
    holding_id: str,
    profile_answers: dict[str, Any] | None = None,
    as_of: date | None = None,
) -> CrossJurisdictionReport:
    """Runs the ordinary tenant pipeline for one holding against every
    linked pack (``ctx.domain_pack`` plus everything in
    ``ctx.linked_packs``), applying the discovery filter to corridor packs
    first, and merges the results into one report. Skipped corridor packs
    are still listed, with ``considered=False`` and the reason why — so the
    holder can see that a corridor was checked and ruled out, not that it
    was silently never tried.
    """
    from .. import pipeline  # local import: pipeline imports the tenant agents, not this module

    profile_answers = profile_answers or {}
    holder = ctx.register.get("holder", {})

    all_packs: dict[str, DomainPack] = {ctx.domain_pack.domain_id: ctx.domain_pack, **ctx.linked_packs}
    candidates = discover(holder, all_packs)
    candidate_ids = {p.domain_id for p in candidates}

    results: list[JurisdictionResult] = []
    for domain_id, pack in all_packs.items():
        if domain_id not in candidate_ids:
            _, reason = _corridor_applies(pack, holder)
            results.append(JurisdictionResult(
                domain_id=pack.domain_id, title=pack.title, is_corridor=pack.is_corridor,
                considered=False, determination=None, actions=(), skipped_reason=reason,
            ))
            continue

        determination, actions = pipeline.actions_for(
            ctx, holding_id, profile_answers, as_of=as_of, domain_pack=pack,
        )
        results.append(JurisdictionResult(
            domain_id=pack.domain_id, title=pack.title, is_corridor=pack.is_corridor,
            considered=True, determination=determination, actions=tuple(actions), skipped_reason=None,
        ))

        if ctx.atlas is not None:
            ctx.atlas.append(
                agent="MERIDIAN",
                step="jurisdiction_surveyed",
                payload={
                    "holding_id": holding_id,
                    "domain_id": pack.domain_id,
                    "is_corridor": pack.is_corridor,
                    "determination": determination.as_dict(),
                    "action_count": len(actions),
                },
                tenant_id=holding_id,
            )

    return CrossJurisdictionReport(holding_id=holding_id, results=tuple(results))
