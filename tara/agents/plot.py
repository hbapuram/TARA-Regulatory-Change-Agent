"""PLOT — Position Ledger of Obligations and Triggers.  TENANT · computed per customer.

    align(obligation_set, register) -> gap_register

Aligns each applicable obligation against the tenant's register — holdings
for an individual. Returns coverage (satisfied, partial, absent), severity,
the matched entry, and the artefact required. Also fires calendar-driven
triggers from dates held in the register: obligations that arrive because
time passed, not because anything was published. Records negative findings
explicitly rather than staying silent on them.

PLOT must never run for a holding before COMPASS has confirmed it — that
band order is enforced by the caller (the MCP server / orchestrator), not
here, but this module will raise if handed anything but a CONFIRMED
determination, so the ordering violation is loud rather than silent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..atlas.store import AtlasStore
from ..core.dates import parse_iso_date, resolve_recurrence
from ..core.domain_pack import DomainPack
from .compass import Determination
from .legend import ObligationRecord


class BandOrderError(RuntimeError):
    """Raised when PLOT is asked to align a holding COMPASS has not confirmed."""


@dataclass(frozen=True)
class GapEntry:
    holding_id: str
    obligation_id: str
    provision: str
    coverage: str          # satisfied | partial | absent | not_applicable | indeterminate
    severity: str
    matched_entry: str
    artefact_type: str
    trigger_date: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "holding_id": self.holding_id,
            "obligation_id": self.obligation_id,
            "provision": self.provision,
            "coverage": self.coverage,
            "severity": self.severity,
            "matched_entry": self.matched_entry,
            "artefact_type": self.artefact_type,
            "trigger_date": self.trigger_date,
            "reason": self.reason,
        }


def _trigger_date_for(domain_pack: DomainPack, obligation_id: str, holding: dict[str, Any], as_of: date) -> tuple[str, bool] | None:
    """Returns (trigger_date, is_due) for the obligation's configured date
    trigger against this holding, or None if no trigger is configured or
    the register lacks the base field.
    """
    for trigger in domain_pack.date_triggers:
        if trigger.obligation_id != obligation_id:
            continue
        base_value = holding.get(trigger.base_field)
        if base_value is None:
            return None
        anchor = parse_iso_date(base_value)
        if trigger.recurring:
            fired, is_due = resolve_recurrence(anchor, trigger.interval_years, as_of)
        else:
            fired, is_due = anchor, anchor <= as_of
        return fired.isoformat(), is_due
    return None


def _has_configured_trigger(domain_pack: DomainPack, obligation_id: str) -> bool:
    """Distinguishes two cases that both leave trigger_date as None: an
    obligation with no date_trigger configured at all (an honest "the
    source publishes no fixed timeframe" fact — see e.g.
    domains/ireland-irp.yaml's change-of-address obligation) versus one
    whose trigger IS configured but whose base_field is absent from this
    particular holding (a register data-completeness gap). The two used to
    produce an identical, ambiguous reason string; align() below uses this
    to tell them apart in the reported reason.
    """
    return any(t.obligation_id == obligation_id for t in domain_pack.date_triggers)


def _condition_matches(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate the deliberately small, deterministic obligation predicate DSL.

    Domain packs may use only explicit comparisons. There is no expression
    evaluation and no model judgement in this path.
    """
    if operator == "equals":
        return actual == expected
    if operator == "in":
        return actual in expected
    if operator == "contains":
        return expected in actual
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    raise ValueError(f"unsupported obligation applicability operator: {operator!r}")


def _obligation_scope(
    domain_pack: DomainPack,
    obligation_id: str,
    holding: dict[str, Any],
    trigger_date: str | None,
) -> tuple[str, str] | None:
    """Return a non-actionable coverage/reason, or None when the duty applies.

    COMPASS determines whether the *pack* is in scope. This second gate checks
    event-, threshold-, instrument-, and effective-date conditions that belong
    to one obligation only. Missing material facts become ``indeterminate``;
    false predicates become ``not_applicable``. Neither state opens an action.
    """
    spec = domain_pack.obligation(obligation_id)

    if spec.effective_from or spec.effective_to:
        if trigger_date is None:
            return (
                "indeterminate",
                "Cannot select the applicable rule version because the obligation's event date is missing.",
            )
        event_date = parse_iso_date(trigger_date)
        if spec.effective_from and event_date < parse_iso_date(spec.effective_from):
            return (
                "not_applicable",
                f"The event date {trigger_date} is before this rule took effect on {spec.effective_from}.",
            )
        if spec.effective_to and event_date > parse_iso_date(spec.effective_to):
            return (
                "not_applicable",
                f"The event date {trigger_date} is after this rule ceased to apply on {spec.effective_to}.",
            )

    for condition in spec.applies_when:
        field = condition["field"]
        operator = condition["operator"]
        expected = condition.get("value")
        if field not in holding or holding[field] is None:
            return (
                "indeterminate",
                f"Cannot determine whether {obligation_id} applies: required fact {field!r} is missing.",
            )
        actual = holding[field]
        try:
            matches = _condition_matches(actual, operator, expected)
        except (TypeError, ValueError) as exc:
            return (
                "indeterminate",
                f"Cannot evaluate {obligation_id}: {field!r} has an incompatible value ({exc}).",
            )
        if not matches:
            return (
                "not_applicable",
                f"{obligation_id} does not apply because {field}={actual!r} does not satisfy {operator} {expected!r}.",
            )
    return None


def _existing_closure(atlas: AtlasStore | None, obligation_id: str, holding_id: str, trigger_date: str | None) -> dict[str, Any] | None:
    if atlas is None:
        return None
    for entry in atlas.reconstruct(obligation_id):
        if entry["step"] != "closure":
            continue
        payload = entry["payload"]
        if payload.get("holding_id") == holding_id and payload.get("trigger_date") == trigger_date and payload.get("outcome") == "closed":
            return payload
    return None


def align(
    domain_pack: DomainPack,
    holding: dict[str, Any],
    obligations: list[ObligationRecord],
    determination: Determination,
    as_of: date | None = None,
    atlas: AtlasStore | None = None,
) -> list[GapEntry]:
    if determination.status != "CONFIRMED":
        raise BandOrderError(
            f"PLOT cannot align holding {holding['holding_id']!r}: "
            f"COMPASS returned {determination.status}, not CONFIRMED"
        )

    as_of = as_of or date.today()
    gaps: list[GapEntry] = []

    for obligation in obligations:
        resolved = _trigger_date_for(domain_pack, obligation.obligation_id, holding, as_of)
        trigger_date, is_due = resolved if resolved is not None else (None, False)
        scoped_out = _obligation_scope(
            domain_pack, obligation.obligation_id, holding, trigger_date
        )
        if scoped_out is not None:
            coverage, reason = scoped_out
            gap = GapEntry(
                holding_id=holding["holding_id"],
                obligation_id=obligation.obligation_id,
                provision=obligation.provision,
                coverage=coverage,
                severity=obligation.severity,
                matched_entry=holding["holding_id"],
                artefact_type=obligation.artefact_type,
                trigger_date=trigger_date,
                reason=reason,
            )
            gaps.append(gap)
            if atlas is not None:
                atlas.append(
                    agent="PLOT",
                    step="obligation_scoped",
                    obligation_id=obligation.obligation_id,
                    tenant_id=holding["holding_id"],
                    payload=gap.as_dict(),
                )
            continue
        closure = _existing_closure(atlas, obligation.obligation_id, holding["holding_id"], trigger_date)

        if closure is not None:
            coverage = "satisfied"
            reason = f"Closed against artefact submitted {closure.get('artefact', {}).get('valuation_date', closure.get('artefact', {}))}."
        elif trigger_date is not None and is_due:
            coverage = "absent"
            reason = f"Trigger date {trigger_date} has passed with no recorded evidence."
        elif trigger_date is not None:
            coverage = "partial"
            reason = f"Applicable; next trigger date {trigger_date} has not yet arrived."
        elif _has_configured_trigger(domain_pack, obligation.obligation_id):
            coverage = "indeterminate"
            reason = (
                "Cannot determine the obligation's event date because the "
                "register entry is missing the configured trigger field; no "
                "automated action is opened."
            )
        else:
            coverage = "absent"
            reason = (
                "Applicable obligation has no statutory timeframe configured "
                "for it — the source publishes none — so no deadline can be "
                "derived; this requires manual scheduling rather than an "
                "invented date."
            )

        gap = GapEntry(
            holding_id=holding["holding_id"],
            obligation_id=obligation.obligation_id,
            provision=obligation.provision,
            coverage=coverage,
            severity=obligation.severity,
            matched_entry=holding["holding_id"],
            artefact_type=obligation.artefact_type,
            trigger_date=trigger_date,
            reason=reason,
        )
        gaps.append(gap)

        if atlas is not None:
            atlas.append(
                agent="PLOT",
                step="gap_found",
                obligation_id=obligation.obligation_id,
                tenant_id=holding["holding_id"],
                payload=gap.as_dict(),
            )

    return gaps
