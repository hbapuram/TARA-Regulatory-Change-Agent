"""LEGEND — Legal Enumeration of Granular Enforceable Duties.  OPEN · computed once.

    decompose(change_record) -> obligation_set

Turns a changed provision into the discrete, individually testable
obligations catalogued against it in the domain pack — each carrying its
citation, severity and the artefact type that would satisfy it. Detects
overlap with obligations already in the graph (by obligation_id), so a
re-run extends the graph rather than duplicating it. What a rule requires
does not vary by who is reading it, which is why this is open rather than
tenant work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..atlas.store import AtlasStore
from ..core.domain_pack import DomainPack, ObligationSpec
from .survey import ChangeRecord


@dataclass(frozen=True)
class ObligationRecord:
    obligation_id: str
    provision: str
    text: str
    severity: str
    artefact_type: str
    source_id: str
    change_type: str   # "amended" | "added" | "removed" | "unchanged"

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "provision": self.provision,
            "text": self.text,
            "severity": self.severity,
            "artefact_type": self.artefact_type,
            "source_id": self.source_id,
            "change_type": self.change_type,
        }


def decompose(
    domain_pack: DomainPack,
    change_record: ChangeRecord,
    existing_graph: set[str] | None = None,
    atlas: AtlasStore | None = None,
) -> list[ObligationRecord]:
    """Map a SURVEY change_record's changed provisions to catalogued
    obligations. ``existing_graph`` is the set of obligation_ids already
    known (from a prior run) — obligations in it are marked "unchanged"-safe
    for dedup by the caller (ALMANAC uses this to compute unchanged / amended
    / superseded / withdrawn markings).
    """
    existing_graph = existing_graph or set()
    changed_refs = {c.reference: c.change_type for c in change_record.changes}

    catalogued = domain_pack.obligations_for_source(change_record.source_id)
    records: list[ObligationRecord] = []

    for obligation in catalogued:
        change_type = changed_refs.get(obligation.provision)
        if change_type is None:
            # Provision untouched by this diff. Only report it if it's not
            # already in the graph (first run) — otherwise it's genuinely
            # unaffected by *this* change and ALMANAC will mark it separately.
            if obligation.obligation_id in existing_graph:
                continue
            change_type = "unchanged"

        record = ObligationRecord(
            obligation_id=obligation.obligation_id,
            provision=obligation.provision,
            text=obligation.text,
            severity=obligation.severity,
            artefact_type=obligation.artefact_type,
            source_id=obligation.source_id,
            change_type=change_type,
        )
        records.append(record)

        if atlas is not None:
            atlas.append(
                agent="LEGEND",
                step="obligation_decomposed",
                obligation_id=record.obligation_id,
                payload=record.as_dict(),
            )

    return records
