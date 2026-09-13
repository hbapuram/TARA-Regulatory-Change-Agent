"""Loads and validates a domain pack YAML file.

If adding a domain requires editing Python, the abstraction leaked. This
module is the only place that reads ``domains/*.yaml`` — every agent works
off the dataclasses below, never off raw dict access into YAML.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REQUIRED_OPEN_KEYS = {"sources", "obligations"}
REQUIRED_TENANT_KEYS = {
    "register_schema",
    "scoping_questions",
    "date_triggers",
    "evidence_rules",
}


class DomainPackError(ValueError):
    pass


@dataclass(frozen=True)
class SourceConfig:
    source_id: str
    instrument: str
    issuing_authority: str
    url: str
    v1_path: str
    v2_path: str
    last_verified: str
    max_verification_age_days: int


@dataclass(frozen=True)
class ObligationSpec:
    obligation_id: str
    provision: str
    source_id: str
    text: str
    severity: str
    artefact_type: str
    introduced_in: str | None = None
    depends_on: tuple[str, ...] = ()
    supersedes: str | None = None
    superseded_by: str | None = None
    # Optional, deterministic conditions evaluated by PLOT for this specific
    # obligation after COMPASS has established that the pack is in scope.
    # This prevents a broad pack-level determination from opening every duty
    # in the pack when a threshold, event, instrument type, or effective date
    # is not actually satisfied.
    applies_when: tuple[dict[str, Any], ...] = ()
    effective_from: str | None = None
    effective_to: str | None = None


@dataclass(frozen=True)
class ScopingQuestion:
    """A single, self-contained applicability rule. COMPASS evaluates these
    generically (see tara/agents/compass.py::_evaluate) — no scoping logic
    lives in code, so a new domain pack needs only its own list of these,
    never a change to COMPASS itself.
    """
    question_id: str
    text: str
    answerable_from_register: bool
    register_field: str | None
    provision: str | None = None
    # {"in": [...]} | {"not_in": [...]} | {"equals": value} — the condition
    # the answer must satisfy to pass. None means "no pass/fail condition":
    # COMPASS still requires an answer, but any answer satisfies it.
    expect: dict[str, Any] | None = None
    on_fail: str = "EXEMPT"          # CONFIRMED is never a legal on_fail value
    fail_reason_template: str | None = None


@dataclass(frozen=True)
class DateTrigger:
    trigger_id: str
    obligation_id: str
    description: str
    base_field: str
    interval_years: int
    recurring: bool


@dataclass(frozen=True)
class DomainPack:
    domain_id: str
    title: str
    sector: str
    sources: dict[str, SourceConfig]
    obligations: dict[str, ObligationSpec]
    register_schema: dict[str, Any]
    scoping_questions: list[ScopingQuestion]
    date_triggers: list[DateTrigger]
    evidence_rules: dict[str, dict[str, Any]]
    base_path: Path = field(repr=False)
    # None for an ordinary, single-jurisdiction pack. Set for a *corridor*
    # pack — one whose source is a bilateral instrument (a tax treaty, a
    # mutual reporting agreement) rather than one country's own guidance,
    # and whose obligations only apply to a holder who is both things at
    # once. A corridor pack is not a different kind of file — same shape,
    # same loader, same agents — this block is just what lets MERIDIAN
    # discover which packs are corridors and which combination of facts
    # about a holder makes one apply.
    corridor: dict[str, str] | None = None

    @property
    def is_corridor(self) -> bool:
        return self.corridor is not None

    def source(self, source_id: str) -> SourceConfig:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise DomainPackError(f"unknown source_id: {source_id}") from exc

    def obligations_for_source(self, source_id: str) -> list[ObligationSpec]:
        return [o for o in self.obligations.values() if o.source_id == source_id]

    def obligation(self, obligation_id: str) -> ObligationSpec:
        try:
            return self.obligations[obligation_id]
        except KeyError as exc:
            raise DomainPackError(f"unknown obligation_id: {obligation_id}") from exc


def _validate(raw: dict[str, Any]) -> None:
    missing_top = {"domain_id", "title", "sector", "open", "tenant"} - raw.keys()
    if missing_top:
        raise DomainPackError(f"domain pack missing top-level keys: {sorted(missing_top)}")

    missing_open = REQUIRED_OPEN_KEYS - raw["open"].keys()
    if missing_open:
        raise DomainPackError(f"domain pack 'open' block missing keys: {sorted(missing_open)}")

    missing_tenant = REQUIRED_TENANT_KEYS - raw["tenant"].keys()
    if missing_tenant:
        raise DomainPackError(f"domain pack 'tenant' block missing keys: {sorted(missing_tenant)}")


def load_domain_pack(path: str | Path) -> DomainPack:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    _validate(raw)

    base_path = path.parent.parent  # domains/tax.yaml -> repo root

    sources = {
        s["source_id"]: SourceConfig(
            source_id=s["source_id"],
            instrument=s["instrument"],
            issuing_authority=s["issuing_authority"],
            url=s["url"],
            v1_path=s["v1_path"],
            v2_path=s["v2_path"],
            last_verified=s["last_verified"],
            max_verification_age_days=s["max_verification_age_days"],
        )
        for s in raw["open"]["sources"]
    }

    obligations = {
        o["obligation_id"]: ObligationSpec(
            obligation_id=o["obligation_id"],
            provision=o["provision"],
            source_id=o["source_id"],
            text=o["text"].strip(),
            severity=o["severity"],
            artefact_type=o["artefact_type"],
            introduced_in=o.get("introduced_in"),
            depends_on=tuple(o.get("depends_on", [])),
            supersedes=o.get("supersedes"),
            superseded_by=o.get("superseded_by"),
            applies_when=tuple(o.get("applies_when", [])),
            effective_from=o.get("effective_from"),
            effective_to=o.get("effective_to"),
        )
        for o in raw["open"]["obligations"]
    }

    scoping_questions = [
        ScopingQuestion(
            question_id=q["question_id"],
            text=q["text"],
            answerable_from_register=q["answerable_from_register"],
            register_field=q.get("register_field"),
            provision=q.get("provision"),
            expect=q.get("expect"),
            on_fail=q.get("on_fail", "EXEMPT"),
            fail_reason_template=q.get("fail_reason_template"),
        )
        for q in raw["tenant"]["scoping_questions"]
    ]

    date_triggers = [
        DateTrigger(
            trigger_id=t["trigger_id"],
            obligation_id=t["obligation_id"],
            description=t["description"],
            base_field=t["base_field"],
            interval_years=t["interval_years"],
            recurring=t["recurring"],
        )
        for t in raw["tenant"]["date_triggers"]
    ]

    return DomainPack(
        domain_id=raw["domain_id"],
        title=raw["title"],
        sector=raw["sector"],
        sources=sources,
        obligations=obligations,
        register_schema=raw["tenant"]["register_schema"],
        scoping_questions=scoping_questions,
        date_triggers=date_triggers,
        evidence_rules=raw["tenant"]["evidence_rules"],
        base_path=base_path,
        corridor=raw.get("corridor"),
    )
