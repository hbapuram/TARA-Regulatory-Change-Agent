"""COMPASS — Boundary Evaluation and Relevance.  TENANT · computed per customer.

    assess(obligation_set, profile) -> determination

Runs the applicability interview using the instrument's own scoping
provisions. Answers come from the tenant profile where held; where a fact
is absent it asks rather than inferring. Returns CONFIRMED, EXEMPT or
INDETERMINATE with the provision relied on. Determinations are cached, so
identical scoping is never re-litigated.

Nothing about the tax domain is hard-coded here. Every question is walked
generically off ``domain_pack.scoping_questions`` — each question declares
its own pass condition (``expect``), its own outcome on failure
(``on_fail``) and its own citation (``provision``). A new domain pack
(a different regulation, a different sector) needs only its own list of
scoping questions shaped this way; this module does not change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..atlas.store import AtlasStore
from ..core.domain_pack import DomainPack, ScopingQuestion


@dataclass(frozen=True)
class Determination:
    holding_id: str
    status: str                     # CONFIRMED | EXEMPT | INDETERMINATE
    reason: str
    relied_on: str | None           # question_id the determination turned on
    missing_question: str | None    # question_id COMPASS needs answered

    def as_dict(self) -> dict[str, Any]:
        return {
            "holding_id": self.holding_id,
            "status": self.status,
            "reason": self.reason,
            "relied_on": self.relied_on,
            "missing_question": self.missing_question,
        }


class DeterminationCache:
    """Keyed on (tenant_id, holding_id, sorted answer tuple). Identical
    scoping for the same holding never gets re-litigated, so the system gets
    cheaper per tenant the longer it runs.
    """

    def __init__(self):
        self._cache: dict[tuple, Determination] = {}

    @staticmethod
    def _key(tenant_id: str, holding_id: str, answers: dict[str, Any]) -> tuple:
        # An answer's value is usually a scalar, but a list-valued register
        # field (e.g. citizenships: ["India"]) is a normal answer too — make
        # it hashable the same generic way regardless of which field it is.
        normalized = tuple(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in sorted(answers.items())
        )
        return (tenant_id, holding_id, normalized)

    def get(self, tenant_id: str, holding_id: str, answers: dict[str, Any]) -> Determination | None:
        return self._cache.get(self._key(tenant_id, holding_id, answers))

    def put(self, tenant_id: str, holding_id: str, answers: dict[str, Any], determination: Determination) -> None:
        self._cache[self._key(tenant_id, holding_id, answers)] = determination


def _gather_answers(domain_pack: DomainPack, holding: dict[str, Any], profile_answers: dict[str, Any]) -> dict[str, Any]:
    """Resolves each scoping question to an answer, preferring the register
    where the question says the register holds it, and falling back to
    explicit profile answers otherwise.
    """
    answers: dict[str, Any] = {}
    for q in domain_pack.scoping_questions:
        if q.answerable_from_register and q.register_field:
            if q.register_field in holding:
                answers[q.question_id] = holding[q.register_field]
                continue
        # not in the register (or the register doesn't hold it) — needs an explicit answer
        if q.question_id in profile_answers:
            answers[q.question_id] = profile_answers[q.question_id]
    return answers


def _matches(expect: dict[str, Any], value: Any) -> bool:
    if "in" in expect:
        return value in expect["in"]
    if "not_in" in expect:
        return value not in expect["not_in"]
    if "equals" in expect:
        return value == expect["equals"]
    if "contains" in expect:
        # value is itself list-valued (e.g. citizenships: ["India"]) and must
        # contain the single required item — the mirror image of "in", for
        # register fields that hold more than one fact at once.
        try:
            return expect["contains"] in value
        except TypeError:
            return False
    if "not_contains" in expect:
        # The negation of "contains", for a scoping question that turns on a
        # list-valued fact's *absence* (e.g. "is the holder NOT a tax
        # resident of India" — the NRI securities pack's mirror image of the
        # Schedule FA pack's own ROR gate). A missing or non-list value
        # counts as not containing anything, which is the correct pass here.
        try:
            return expect["not_contains"] not in value
        except TypeError:
            return True
    raise ValueError(f"scoping question 'expect' clause not understood: {expect!r}")


def _evaluate(domain_pack: DomainPack, holding_id: str) -> "_Evaluator":
    return _Evaluator(domain_pack, holding_id)


class _Evaluator:
    """Walks ``domain_pack.scoping_questions`` in order, in the exact shape
    every scoping question declares itself: is an answer on file at all
    (else INDETERMINATE, asking for it); if so, does it satisfy the
    question's own ``expect`` clause (else the question's own ``on_fail``
    status, with its own citation and reason). Falling through every
    question with no failure is CONFIRMED.
    """

    def __init__(self, domain_pack: DomainPack, holding_id: str):
        self.domain_pack = domain_pack
        self.holding_id = holding_id

    def run(self, answers: dict[str, Any]) -> Determination:
        relied_on: str | None = None
        for q in self.domain_pack.scoping_questions:
            if q.question_id not in answers:
                return Determination(
                    self.holding_id, "INDETERMINATE",
                    f"{q.text} is not on file and is not held in the register.",
                    None, q.question_id,
                )
            value = answers[q.question_id]
            if q.expect is not None and not _matches(q.expect, value):
                reason = (
                    q.fail_reason_template.format(value=value, provision=q.provision or q.question_id)
                    if q.fail_reason_template
                    else f"{q.text} — answer {value!r} does not satisfy scope."
                )
                return Determination(self.holding_id, q.on_fail, reason, q.question_id, None)
            relied_on = q.question_id
        return Determination(
            self.holding_id, "CONFIRMED",
            "Holder is within scope on every configured scoping question.",
            relied_on, None,
        )


def assess(
    domain_pack: DomainPack,
    holding: dict[str, Any],
    profile_answers: dict[str, Any],
    tenant_id: str,
    cache: DeterminationCache | None = None,
    atlas: AtlasStore | None = None,
) -> Determination:
    holding_id = holding["holding_id"]
    answers = _gather_answers(domain_pack, holding, profile_answers)

    if cache is not None:
        cached = cache.get(tenant_id, holding_id, answers)
        if cached is not None:
            return cached

    determination = _evaluate(domain_pack, holding_id).run(answers)

    if cache is not None:
        cache.put(tenant_id, holding_id, answers, determination)

    if atlas is not None:
        atlas.append(
            agent="COMPASS",
            step="applicability_determined",
            payload=determination.as_dict(),
            tenant_id=tenant_id,
        )

    return determination
