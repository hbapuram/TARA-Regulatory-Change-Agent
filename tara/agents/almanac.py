"""ALMANAC — Assurance of Legislative Monitoring and Amended Content.  OPEN · computed once.

    refresh(domain) -> coverage_report + graph_diff

Owns the refresh cycle. Runs SURVEY on every configured source and asserts
coverage — every source reached, or explicitly recorded as unreachable. A
source that 404s or silently moves surfaces as a coverage failure rather
than a false "no changes detected". Versions the obligation graph so every
downstream finding records which version it was made against, and marks
each currently-catalogued obligation unchanged, amended, superseded or
withdrawn relative to the last recorded version. Its output is a graph
diff, not a document diff.

For the prototype, ALMANAC runs on command rather than on a scheduler — the
coverage assertion and graph diff are what matter; the cron is trivial.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..atlas.store import AtlasStore
from ..core.domain_pack import DomainPack, ObligationSpec
from . import anchor, survey


def _text_hash(obligation: ObligationSpec) -> str:
    body = f"{obligation.provision}|{obligation.text}|{obligation.severity}|{obligation.artefact_type}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _current_graph(domain_pack: DomainPack) -> dict[str, str]:
    """The obligation graph as the domain pack currently catalogues it —
    every obligation, live or superseded. Supersession is a structural
    relationship (``obligation.superseded_by``) checked fresh against the
    *current* pack every refresh, not something inferred only from an
    obligation disappearing between two stored versions — so OBL-002 is
    detected as superseded (and any prior closure against it reopened)
    identically whether this is the very first refresh ever run or the
    hundredth. Excluding superseded obligations here, as an earlier version
    of this function did, made the reopen path structurally unreachable:
    an obligation that's filtered out before it's ever saved can never be
    observed "disappearing" later.
    """
    return {o.obligation_id: _text_hash(o) for o in domain_pack.obligations.values()}


@dataclass(frozen=True)
class SourceCoverage:
    source_id: str
    reached: bool
    changed: bool
    stale: bool
    # Fingerprint of exactly what SURVEY read this refresh, carried through
    # so a coverage report proves *which* content it's a coverage report of —
    # the same fingerprint ATLAS records under step="source_accessed" via
    # AtlasStore.entries_for_source(), so a reader can cross-check the two.
    v1_sha256: str | None = None
    v2_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "reached": self.reached,
            "changed": self.changed,
            "stale": self.stale,
            "v1_sha256": self.v1_sha256,
            "v2_sha256": self.v2_sha256,
        }


@dataclass(frozen=True)
class GraphDiffEntry:
    obligation_id: str
    marking: str   # unchanged | amended | superseded | added | withdrawn

    def as_dict(self) -> dict[str, Any]:
        return {"obligation_id": self.obligation_id, "marking": self.marking}


@dataclass(frozen=True)
class RefreshResult:
    domain_id: str
    version: int
    coverage: list[SourceCoverage]
    graph_diff: list[GraphDiffEntry]
    reopened: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "version": self.version,
            "coverage": [c.as_dict() for c in self.coverage],
            "graph_diff": [g.as_dict() for g in self.graph_diff],
            "reopened": self.reopened,
        }


def _load_version_store(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_version_store(path: Path, version: int, graph: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": version, "obligations": graph}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def refresh(
    domain_pack: DomainPack,
    version_store_path: str | Path,
    as_of: date | None = None,
    atlas: AtlasStore | None = None,
) -> RefreshResult:
    as_of = as_of or date.today()
    version_store_path = Path(version_store_path)

    coverage: list[SourceCoverage] = []
    for source_id in domain_pack.sources:
        change_record = survey.detect_change(domain_pack, source_id, as_of=as_of, atlas=atlas)
        coverage.append(
            SourceCoverage(
                source_id=source_id,
                reached=change_record.reached,
                changed=bool(change_record.changes),
                stale=change_record.stale,
                v1_sha256=change_record.v1_sha256,
                v2_sha256=change_record.v2_sha256,
            )
        )

    current_graph = _current_graph(domain_pack)
    previous = _load_version_store(version_store_path)

    graph_diff: list[GraphDiffEntry] = []
    reopened: list[dict[str, Any]] = []

    version = 1 if previous is None else previous["version"] + 1
    previous_graph: dict[str, str] = {} if previous is None else previous["obligations"]

    for obligation_id, text_hash in current_graph.items():
        spec = domain_pack.obligations[obligation_id]

        if spec.superseded_by is not None and spec.superseded_by in current_graph:
            # Structural, not a diff artefact: this obligation's own record
            # says it has been superseded, checked against the pack as it
            # stands right now. True even on the very first refresh — no
            # prior version needs to have existed for this to fire.
            marking = "superseded"
        elif obligation_id not in previous_graph:
            marking = "added"
        elif previous_graph[obligation_id] != text_hash:
            marking = "amended"
        else:
            marking = "unchanged"

        graph_diff.append(GraphDiffEntry(obligation_id, marking))

        if marking == "superseded" and atlas is not None:
            for entry in atlas.reconstruct(obligation_id):
                if entry["step"] != "closure" or entry["payload"].get("outcome") != "closed":
                    continue
                holding_id = entry["payload"]["holding_id"]
                # Idempotent: don't re-reopen a closure this obligation's
                # chain already shows was reopened for this holding — a
                # refresh run twice in a row must not double-fire.
                already_reopened = any(
                    e["step"] == "reopened" and e["payload"].get("holding_id") == holding_id
                    for e in atlas.reconstruct(obligation_id)
                )
                if already_reopened:
                    continue
                reopened.append(
                    anchor.reopen(
                        obligation_id=obligation_id,
                        holding_id=holding_id,
                        reason=(
                            f"{obligation_id} is superseded by "
                            f"{spec.superseded_by} as of Chart version {version}."
                        ),
                        trigger="supersession",
                        atlas=atlas,
                    )
                )

    for obligation_id in previous_graph:
        if obligation_id in current_graph:
            continue
        # Genuinely removed from the pack, not merely superseded (a
        # superseded obligation is always still catalogued — see above).
        graph_diff.append(GraphDiffEntry(obligation_id, "withdrawn"))

    _save_version_store(version_store_path, version, current_graph)

    result = RefreshResult(
        domain_id=domain_pack.domain_id,
        version=version,
        coverage=coverage,
        graph_diff=graph_diff,
        reopened=reopened,
    )

    if atlas is not None:
        atlas.append(agent="ALMANAC", step="refresh", payload=result.as_dict())

    return result
