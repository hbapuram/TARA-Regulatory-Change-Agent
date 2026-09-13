"""ANCHOR — Artefact and Notarised Closure of Held Obligation Records.  TENANT · computed per customer.

    verify(action, artefact, determination) -> closure | return

Checks the submitted artefact against the evidence rules for that
obligation — right type, right scope, right date, right approval level, and
(where the obligation was itself amended) the right rate. Closes only where
responsive; returns with a specific outstanding item where not. Every
numeric check is exact: ANCHOR never treats "close enough" as a pass,
because the one place a model is tempted to approximate an arithmetic check
is exactly the place a wrong approval is most expensive.

ANCHOR is the last link in the tenant band, so it enforces band order
itself rather than trusting callers to have run COMPASS first: ``verify()``
raises BandOrderError unless handed a CONFIRMED determination for the same
holding. This mirrors PLOT — the guard lives in the agent that would do the
damage if skipped, not only in the pipeline that is supposed to call it.

Reopens on two triggers: recurrence, where an annual obligation's evidence
decays, and supersession, where ALMANAC reports that the provision a
closure was made against no longer says what it said.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..atlas.store import AtlasStore
from ..core.dates import parse_iso_date
from ..core.domain_pack import DomainPack
from .compass import Determination
from .course import Action
from .plot import BandOrderError


@dataclass(frozen=True)
class ClosureResult:
    action_id: str
    obligation_id: str
    holding_id: str
    outcome: str          # closed | returned
    reason: str
    trigger_date: str | None
    artefact: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "obligation_id": self.obligation_id,
            "holding_id": self.holding_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "trigger_date": self.trigger_date,
            "artefact": self.artefact,
        }


def _missing_fields(required: list[str], artefact: dict[str, Any]) -> list[str]:
    return [f for f in required if artefact.get(f) in (None, "")]


def verify(
    domain_pack: DomainPack,
    action: Action,
    artefact: dict[str, Any],
    determination: Determination,
    trigger_date: str | None = None,
    atlas: AtlasStore | None = None,
) -> ClosureResult:
    if determination.status != "CONFIRMED" or determination.holding_id != action.holding_id:
        raise BandOrderError(
            f"ANCHOR cannot verify {action.obligation_id!r} for holding {action.holding_id!r}: "
            f"COMPASS returned {determination.status!r} for holding {determination.holding_id!r}, "
            f"not a CONFIRMED determination for this holding."
        )

    rule = domain_pack.evidence_rules.get(action.obligation_id)
    if rule is None:
        result = ClosureResult(
            action.action_id, action.obligation_id, action.holding_id,
            "returned", f"No evidence rule configured for {action.obligation_id}.",
            trigger_date, artefact,
        )
    elif artefact.get("artefact_type") != rule["artefact_type"]:
        result = ClosureResult(
            action.action_id, action.obligation_id, action.holding_id,
            "returned",
            f"Wrong artefact type: expected {rule['artefact_type']!r}, got {artefact.get('artefact_type')!r}.",
            trigger_date, artefact,
        )
    else:
        missing = _missing_fields(rule.get("required_fields", []), artefact)
        if missing:
            result = ClosureResult(
                action.action_id, action.obligation_id, action.holding_id,
                "returned", f"Missing required field(s): {', '.join(missing)}.",
                trigger_date, artefact,
            )
        elif rule.get("expected_rate") is not None and not _rate_matches(artefact, rule["expected_rate"]):
            result = ClosureResult(
                action.action_id, action.obligation_id, action.holding_id,
                "returned",
                (
                    f"rate_applied {artefact.get('rate_applied')!r} does not match the "
                    f"{rule['expected_rate']:.0%} rate required for {action.obligation_id} — "
                    f"submitting evidence at a superseded rate does not satisfy the current obligation."
                ),
                trigger_date, artefact,
            )
        elif _arithmetic_checkable(artefact) and not _tax_computation_exact(artefact):
            result = ClosureResult(
                action.action_id, action.obligation_id, action.holding_id,
                "returned",
                (
                    f"computed_tax {artefact.get('computed_tax')} does not exactly equal "
                    f"rate_applied * deemed_gain "
                    f"({_expected_tax(artefact)}). Not accepted as approximately equal."
                ),
                trigger_date, artefact,
            )
        elif rule.get("max_days_after_event") is not None:
            if trigger_date is None:
                result = ClosureResult(
                    action.action_id, action.obligation_id, action.holding_id,
                    "returned",
                    (
                        f"Cannot verify the {rule['max_days_after_event']}-day notification window: "
                        f"no event date is on record for {action.obligation_id} on this holding."
                    ),
                    trigger_date, artefact,
                )
            else:
                notice_date = artefact.get("notice_date")
                event_date = parse_iso_date(trigger_date)
                days_late = (parse_iso_date(notice_date) - event_date).days
                if days_late > rule["max_days_after_event"]:
                    result = ClosureResult(
                        action.action_id, action.obligation_id, action.holding_id,
                        "returned",
                        f"Notified {days_late} days after the event; the limit is {rule['max_days_after_event']} days.",
                        trigger_date, artefact,
                    )
                else:
                    result = ClosureResult(
                        action.action_id, action.obligation_id, action.holding_id,
                        "closed", "Artefact is responsive and evidence rules are satisfied.",
                        trigger_date, artefact,
                    )
        else:
            result = ClosureResult(
                action.action_id, action.obligation_id, action.holding_id,
                "closed", "Artefact is responsive and evidence rules are satisfied.",
                trigger_date, artefact,
            )

    if atlas is not None:
        atlas.append(
            agent="ANCHOR",
            step="closure",
            obligation_id=action.obligation_id,
            tenant_id=action.holding_id,
            payload=result.as_dict(),
        )

    return result


_ARITHMETIC_OPERANDS = ("deemed_gain", "rate_applied", "computed_tax")


def _arithmetic_checkable(artefact: dict[str, Any]) -> bool:
    """Whether the internal-consistency cross-check below can be applied to
    this artefact at all.

    The check is ``computed_tax == deemed_gain * rate_applied``, and it only
    means anything when all three operands are actually present. That is not
    the same question as "did the check pass", and conflating the two caused
    a real defect: ``_tax_computation_exact`` swallows a missing operand and
    returns False, which sent an artefact with no ``deemed_gain`` down the
    failure branch — where building the failure message called
    ``_expected_tax`` unguarded and raised KeyError, surfacing to an MCP
    client as an opaque "Error executing tool anchor_verify" rather than any
    ClosureResult at all.

    That was reachable from the protocol boundary, not just in theory: no
    domain pack lists ``deemed_gain`` in an evidence rule's
    ``required_fields``, so a client that submitted exactly the fields the
    pack asked for (tax.yaml OBL-002B asks for rate_applied and
    computed_tax) crashed the tool. Every in-repo caller happened to pass
    ``deemed_gain`` anyway, which is why the tests never caught it.

    Gating on operand presence fixes both halves: an artefact carrying the
    operands is still checked exactly — an approximate match is still
    rejected, unchanged — and one that does not carry them is simply not
    subject to a cross-check it has no inputs for, having already passed the
    pack's own artefact_type, required_fields and expected_rate rules.

    A pack that wants the cross-check enforced makes it enforceable by
    listing the operands in its own ``required_fields``; that keeps the
    decision in the domain pack, where this architecture puts every other
    domain rule. See the known-limitation note in the health report:
    the operand *names* here are still hard-coded rather than declared in
    YAML, which is the remaining half of this fix.
    """
    return all(field in artefact for field in _ARITHMETIC_OPERANDS)


def _expected_tax(artefact: dict[str, Any]) -> float:
    return round(float(artefact["deemed_gain"]) * float(artefact["rate_applied"]), 2)


def _tax_computation_exact(artefact: dict[str, Any]) -> bool:
    try:
        return round(float(artefact["computed_tax"]), 2) == _expected_tax(artefact)
    except (KeyError, TypeError, ValueError):
        return False


def _rate_matches(artefact: dict[str, Any], expected_rate: float) -> bool:
    """Whether the submitted rate_applied is the rate this specific
    obligation requires — not just internally consistent with its own
    computed_tax. An obligation that was amended (e.g. OBL-002 -> OBL-002B,
    41% -> 38%) has its own expected_rate; a computation that is arithmetically
    exact but built on a superseded rate must not close.
    """
    try:
        return abs(float(artefact["rate_applied"]) - float(expected_rate)) < 1e-9
    except (KeyError, TypeError, ValueError):
        return False


def reopen(
    obligation_id: str,
    holding_id: str,
    reason: str,
    trigger: str,   # "recurrence" | "supersession"
    atlas: AtlasStore | None = None,
) -> dict[str, Any]:
    """Reopens a prior closure. ATLAS retains both the original closure and
    the reopening, so the ledger shows the position was correct when made
    and what changed after — a reopening is never a silent overwrite.
    """
    payload = {
        "obligation_id": obligation_id,
        "holding_id": holding_id,
        "reason": reason,
        "trigger": trigger,
    }
    if atlas is not None:
        atlas.append(
            agent="ANCHOR",
            step="reopened",
            obligation_id=obligation_id,
            tenant_id=holding_id,
            payload=payload,
        )
    return payload
