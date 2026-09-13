"""COURSE — Compliance Ordering, Urgency, Route and Sequence.  TENANT · computed per customer.

    plan(gap_register) -> action_plan

Converts actionable gaps into dated actions carrying owner, deadline and
required evidence type. Deadlines are derived before, on, or after the
statutory event according to the domain pack rather than assigned arbitrarily,
and actions are sequenced by dependency —
genuinely: a dependent's deadline is clamped to fall after its dependency's,
using a real topological sort of the obligation graph (``depends_on``), not
just a display-order heuristic. An action with no resolvable owner
escalates rather than being created unassigned; so does an action whose
dependency has no resolvable deadline, or whose dependency graph contains a
cycle. COURSE never files or transacts on the holder's behalf.
"""
from __future__ import annotations

import graphlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ..atlas.store import AtlasStore
from ..core.dates import derive_backward_deadline, parse_iso_date
from ..core.domain_pack import DomainPack
from .plot import GapEntry


@dataclass(frozen=True)
class Action:
    action_id: str
    obligation_id: str
    holding_id: str
    owner: str | None
    deadline: str | None
    required_evidence_type: str
    depends_on: tuple[str, ...]
    escalated: bool
    escalation_reason: str | None
    # The citation an orchestrator (or a human) needs to state this action's
    # authority without a separate lookup — e.g. so an LLM client that only
    # calls course_plan (not compass_assess) can still cite domain_id +
    # obligation_id + provision alongside a finding, per the orchestrator's
    # own system-prompt rule that every finding carries its provision.
    # Optional (defaults to None) so every pre-existing Action(...)
    # construction elsewhere in this codebase and in tests keeps working
    # unchanged.
    provision: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "obligation_id": self.obligation_id,
            "holding_id": self.holding_id,
            "owner": self.owner,
            "deadline": self.deadline,
            "required_evidence_type": self.required_evidence_type,
            "depends_on": list(self.depends_on),
            "escalated": self.escalated,
            "escalation_reason": self.escalation_reason,
            "provision": self.provision,
        }


def plan(
    domain_pack: DomainPack,
    gaps: list[GapEntry],
    owner: str | None,
    atlas: AtlasStore | None = None,
) -> list[Action]:
    """Only actionable partial/absent gaps become actions.

    A satisfied, not-applicable, or indeterminate obligation needs no automated
    work item. Each action's own "natural" deadline is derived from its trigger
    date using the evidence rule's ``deadline_direction`` (``before`` by
    default, ``after``, or ``on``); an obligation with no
    trigger date (nothing time-based to derive from) escalates rather than
    being silently skipped. Deadlines are then clamped against the
    dependency graph — a dependent action can never come due before the
    dependency its evidence requires, even if the two obligations' own lead
    times would otherwise put them in the wrong order.
    """
    entries: dict[str, dict[str, Any]] = {}

    for gap in gaps:
        if gap.coverage in {"satisfied", "not_applicable", "indeterminate"}:
            continue

        rule = domain_pack.evidence_rules.get(gap.obligation_id, {})
        obligation = domain_pack.obligation(gap.obligation_id)
        lead_time_days = rule.get("lead_time_days", 0)
        direction = rule.get("deadline_direction", "before")

        escalated = False
        escalation_reason = None
        natural_deadline: date | None = None

        if owner is None:
            escalated = True
            escalation_reason = "No resolvable owner for this holding."
        elif gap.trigger_date is None:
            escalated = True
            escalation_reason = "No statutory date to derive a deadline from."
        else:
            statutory_date = parse_iso_date(gap.trigger_date)
            if direction == "before":
                natural_deadline = derive_backward_deadline(statutory_date, lead_time_days)
            elif direction == "after":
                natural_deadline = statutory_date + timedelta(days=lead_time_days)
            elif direction == "on":
                natural_deadline = statutory_date
            else:
                escalated = True
                escalation_reason = f"Unsupported deadline direction: {direction!r}."

        entries[gap.obligation_id] = {
            "gap": gap,
            "obligation": obligation,
            "escalated": escalated,
            "escalation_reason": escalation_reason,
            "natural_deadline": natural_deadline,
        }

    # Dependency order restricted to this plan: an obligation this action
    # depends on but that isn't in this same plan is already satisfied
    # elsewhere, so it imposes no ordering constraint here.
    ids_in_plan = set(entries)
    graph = {
        obligation_id: {d for d in entry["obligation"].depends_on if d in ids_in_plan}
        for obligation_id, entry in entries.items()
    }

    try:
        order = list(graphlib.TopologicalSorter(graph).static_order())
    except graphlib.CycleError as exc:
        # A cyclic dependency is a domain-pack data error, not a per-tenant
        # one — escalate every action involved rather than crash the run.
        cycle = exc.args[1] if len(exc.args) > 1 else list(entries)
        for obligation_id in entries:
            entries[obligation_id]["escalated"] = True
            entries[obligation_id]["escalation_reason"] = (
                "Dependency cycle detected in the domain pack: "
                + " -> ".join(str(c) for c in cycle) + "."
            )
        order = list(entries)

    effective_deadline: dict[str, date | None] = {}
    for obligation_id in order:
        entry = entries[obligation_id]
        if entry["escalated"]:
            effective_deadline[obligation_id] = None
            continue

        deadline = entry["natural_deadline"]
        blocked = False
        for dep_id in graph[obligation_id]:
            dep_deadline = effective_deadline.get(dep_id)
            if dep_deadline is None:
                blocked = True
                continue
            earliest_after_dep = dep_deadline + timedelta(days=1)
            if deadline is None or earliest_after_dep > deadline:
                deadline = earliest_after_dep

        if blocked:
            entry["escalated"] = True
            entry["escalation_reason"] = (
                entry["escalation_reason"]
                or "Blocked: at least one dependency in this plan has no resolvable deadline."
            )
            effective_deadline[obligation_id] = None
        else:
            effective_deadline[obligation_id] = deadline

    actions: list[Action] = []
    for obligation_id, entry in entries.items():
        gap: GapEntry = entry["gap"]
        deadline_obj = effective_deadline.get(obligation_id)
        action = Action(
            action_id=f"ACT-{gap.obligation_id}-{gap.holding_id}",
            obligation_id=gap.obligation_id,
            holding_id=gap.holding_id,
            owner=owner,
            deadline=deadline_obj.isoformat() if deadline_obj is not None else None,
            required_evidence_type=gap.artefact_type,
            depends_on=entry["obligation"].depends_on,
            escalated=entry["escalated"],
            escalation_reason=entry["escalation_reason"],
            provision=entry["obligation"].provision,
        )
        actions.append(action)

        if atlas is not None:
            atlas.append(
                agent="COURSE",
                step="action_opened",
                obligation_id=gap.obligation_id,
                tenant_id=gap.holding_id,
                payload=action.as_dict(),
            )

    def sort_key(a: Action):
        return (a.escalated, a.deadline or "9999-99-99", a.action_id)

    return sorted(actions, key=sort_key)
