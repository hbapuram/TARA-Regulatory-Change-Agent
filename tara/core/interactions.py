"""Loads compact interaction specs (``domains/interactions.yaml``) and
expands each into an ordinary ``DomainPack`` — the shared, lightweight home
for obligations that exist only in the intersection of two or more of a
holder's own facts (an Indian citizen who is also an Irish tax resident),
rather than in any one country's own guidance.

Why this module exists: the original corridor mechanism modeled an
interaction as a full, hand-written ``DomainPack`` YAML file — its own
register_schema, its own scoping_questions re-deriving the same two-fact
check by hand, its own date_triggers/evidence_rules blocks — repeated in
full for every country pair. That does not scale past one pair, and it
buries the one thing that actually makes an interaction an interaction (the
facts that must both be true) inside a lot of boilerplate that is
mechanically the same every time.

What actually varies between interactions is small: which facts must both
be true, which instrument/source backs the obligations, and what the
obligations themselves are. Everything else — the register schema, the
generic "does the holder have fact X" scoping question, and the
``corridor`` metadata block MERIDIAN's discovery filter reads — is
mechanically derivable from that, and is synthesized here, once, in code.

This keeps the actual authoring surface (``domains/interactions.yaml``) down
to just the facts that make an interaction unique, while COMPASS, PLOT,
COURSE, ANCHOR and MERIDIAN keep working against an ordinary ``DomainPack``
object and never learn this module exists. A fourth interaction — a new
country pair, or a new combination of facts — is a new YAML entry, not a
line of new code, exactly like a new standalone domain pack is a new YAML
file rather than a code change.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .domain_pack import (
    DateTrigger,
    DomainPack,
    ObligationSpec,
    ScopingQuestion,
    SourceConfig,
)

# Maps a `requires` requirement name (as authored in interactions.yaml) to
# the register field a holder's own facts are read from (see
# HOLDER_LEVEL_FACT_FIELDS in tara/mcp_server/context.py) and the human
# question text COMPASS's generic scoping-question evaluator needs. Adding a
# genuinely new *kind* of requirement (not just a new country using the two
# kinds already here) means one new entry in this map — still no change to
# COMPASS, PLOT, COURSE or MERIDIAN, which only ever see the ordinary
# DomainPack this module produces.
_REQUIREMENT_FIELD_MAP: dict[str, dict[str, str]] = {
    "citizenship_of": {
        "register_field": "citizenships",
        "text": "Is the holder a citizen of {value}?",
    },
    "tax_residency_of": {
        "register_field": "tax_residencies",
        "text": "Is the holder tax resident of {value}?",
    },
}


class InteractionError(ValueError):
    pass


@dataclass(frozen=True)
class FactRequirement:
    requirement: str   # key into _REQUIREMENT_FIELD_MAP, e.g. "citizenship_of"
    value: str          # e.g. "India"

    @property
    def register_field(self) -> str:
        try:
            return _REQUIREMENT_FIELD_MAP[self.requirement]["register_field"]
        except KeyError as exc:
            raise InteractionError(f"unknown requirement kind: {self.requirement!r}") from exc

    def question_text(self) -> str:
        return _REQUIREMENT_FIELD_MAP[self.requirement]["text"].format(value=self.value)


@dataclass(frozen=True)
class InteractionObligation:
    obligation_id: str
    provision: str
    text: str
    severity: str
    artefact_type: str
    date_trigger: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    depends_on: tuple[str, ...] = ()
    applies_when: tuple[dict[str, Any], ...] = ()
    effective_from: str | None = None
    effective_to: str | None = None


@dataclass(frozen=True)
class InteractionSpec:
    domain_id: str
    title: str
    sector: str
    requires: tuple[FactRequirement, ...]
    source: SourceConfig
    obligations: tuple[InteractionObligation, ...]


def load_interactions(path: str | Path) -> list[InteractionSpec]:
    """Reads every interaction entry out of a compact interactions YAML
    file. Structurally analogous to ``load_domain_pack`` — this is the only
    place that reads ``domains/interactions.yaml``.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    specs: list[InteractionSpec] = []

    for entry in raw.get("interactions", []):
        requires = tuple(
            FactRequirement(requirement=r["requirement"], value=r["value"])
            for r in entry["requires"]
        )
        s = entry["source"]
        source = SourceConfig(
            source_id=s["source_id"],
            instrument=s["instrument"],
            issuing_authority=s["issuing_authority"],
            url=s["url"],
            v1_path=s["v1_path"],
            v2_path=s["v2_path"],
            last_verified=s["last_verified"],
            max_verification_age_days=s["max_verification_age_days"],
        )
        obligations = tuple(
            InteractionObligation(
                obligation_id=o["obligation_id"],
                provision=o["provision"],
                text=o["text"].strip(),
                severity=o["severity"],
                artefact_type=o["artefact_type"],
                date_trigger=o.get("date_trigger"),
                evidence=o.get("evidence"),
                depends_on=tuple(o.get("depends_on", [])),
                applies_when=tuple(o.get("applies_when", [])),
                effective_from=o.get("effective_from"),
                effective_to=o.get("effective_to"),
            )
            for o in entry["obligations"]
        )
        specs.append(InteractionSpec(
            domain_id=entry["domain_id"],
            title=entry["title"],
            sector=entry["sector"],
            requires=requires,
            source=source,
            obligations=obligations,
        ))

    return specs


def to_domain_pack(spec: InteractionSpec, base_path: Path) -> DomainPack:
    """Synthesizes an ordinary ``DomainPack`` from a compact interaction
    spec. ``sources``, ``obligations``, ``date_triggers`` and
    ``evidence_rules`` are a direct, unmodified carry-over of what the YAML
    authored; ``register_schema``, ``scoping_questions`` and the
    ``corridor`` metadata block are mechanically derived from
    ``spec.requires``. The result is indistinguishable, to every agent that
    consumes it, from a hand-written DomainPack loaded by
    ``load_domain_pack()`` — same dataclass, same fields, same shape.
    """
    sources = {spec.source.source_id: spec.source}
    obligations = {
        o.obligation_id: ObligationSpec(
            obligation_id=o.obligation_id,
            provision=o.provision,
            source_id=spec.source.source_id,
            text=o.text,
            severity=o.severity,
            artefact_type=o.artefact_type,
            depends_on=o.depends_on,
            applies_when=o.applies_when,
            effective_from=o.effective_from,
            effective_to=o.effective_to,
        )
        for o in spec.obligations
    }

    # The register schema needs every requirement's register field (so
    # COMPASS's scoping questions can read it) plus any date trigger's
    # base_field that isn't already one of those (e.g. tax_residency_since,
    # which dates *when* a fact became true rather than being the fact
    # itself) — both derived straight from the spec, nothing hard-coded
    # about which two countries or facts are involved.
    schema_fields = ["holding_id", "instrument_type", "jurisdiction", "acquisition_date", "status"]
    extra_fields = {r.register_field for r in spec.requires}
    extra_fields |= {
        o.date_trigger["base_field"] for o in spec.obligations
        if o.date_trigger and o.date_trigger["base_field"] not in schema_fields
    }
    schema_fields += sorted(extra_fields)
    register_schema = {"entity": "holding", "fields": schema_fields}

    first_provision = spec.obligations[0].provision if spec.obligations else None
    scoping_questions = [
        ScopingQuestion(
            question_id=f"SQ-{spec.domain_id.upper().replace('-', '_')}-{i + 1:02d}",
            text=r.question_text(),
            answerable_from_register=True,
            register_field=r.register_field,
            provision=first_provision,
            expect={"contains": r.value},
            on_fail="EXEMPT",
            fail_reason_template=(
                f"Holder's {r.register_field} ({{value}}) do not include {r.value}, "
                f"so this interaction does not apply."
            ),
        )
        for i, r in enumerate(spec.requires)
    ]

    date_triggers = [
        DateTrigger(
            trigger_id=f"DT-{o.obligation_id}",
            obligation_id=o.obligation_id,
            description=o.date_trigger["description"],
            base_field=o.date_trigger["base_field"],
            interval_years=o.date_trigger["interval_years"],
            recurring=o.date_trigger["recurring"],
        )
        for o in spec.obligations if o.date_trigger
    ]

    evidence_rules = {
        o.obligation_id: {"artefact_type": o.artefact_type, **o.evidence}
        for o in spec.obligations if o.evidence
    }

    # Same shape MERIDIAN's discovery filter (_corridor_applies) already
    # reads off a hand-written pack's `corridor` block — {requirement: value}
    # pairs, e.g. {"citizenship_of": "India", "tax_residency_of": "Ireland"}.
    corridor = {r.requirement: r.value for r in spec.requires}

    return DomainPack(
        domain_id=spec.domain_id,
        title=spec.title,
        sector=spec.sector,
        sources=sources,
        obligations=obligations,
        register_schema=register_schema,
        scoping_questions=scoping_questions,
        date_triggers=date_triggers,
        evidence_rules=evidence_rules,
        base_path=base_path,
        corridor=corridor,
    )


def load_interaction_packs(path: str | Path, base_path: Path) -> dict[str, DomainPack]:
    """Convenience wrapper: load every interaction in one file and
    synthesize each into a DomainPack, keyed by domain_id — the shape
    ``build_context`` merges into ``TaraContext.linked_packs`` alongside any
    ordinary standalone packs.
    """
    return {
        spec.domain_id: to_domain_pack(spec, base_path)
        for spec in load_interactions(path)
    }
