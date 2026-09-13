"""SURVEY — Source Update Review.  OPEN · computed once.

    detect_change(source_id) -> change_record

Maintains a versioned index over named authoritative sources. Diffs the
current version against the prior indexed one and returns only what
changed, with instrument, provision reference, effective date and source
URL. Flags sources past their verification window rather than trusting
them silently. Configured source list only — never open-web scraping, so
coverage is auditable.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..atlas.store import AtlasStore
from ..core.dates import VerificationStatus, parse_iso_date
from ..core.diff import ProvisionChange, diff_documents
from ..core.domain_pack import DomainPack, SourceConfig


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChangeRecord:
    source_id: str
    instrument: str
    url: str
    reached: bool
    stale: bool
    verification: VerificationStatus | None
    changes: list[ProvisionChange]
    # Fingerprints of the exact document bytes SURVEY read this run — the
    # audit trail's proof of *which* content a finding traces back to,
    # independent of whatever the file on disk says later. None when the
    # source wasn't reached at all.
    v1_sha256: str | None = None
    v2_sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "instrument": self.instrument,
            "url": self.url,
            "reached": self.reached,
            "stale": self.stale,
            "verification_age_days": self.verification.age_days if self.verification else None,
            "v1_sha256": self.v1_sha256,
            "v2_sha256": self.v2_sha256,
            "changes": [
                {
                    "provision": c.reference,
                    "heading": c.heading,
                    "change_type": c.change_type,
                    "unified_diff": c.unified_diff,
                }
                for c in self.changes
            ],
        }


def _read_source_file(base_path: Path, relative_path: str) -> str | None:
    full_path = base_path / relative_path
    if not full_path.exists():
        return None
    return full_path.read_text(encoding="utf-8")


def detect_change(
    domain_pack: DomainPack,
    source_id: str,
    as_of: date | None = None,
    atlas: AtlasStore | None = None,
) -> ChangeRecord:
    """Diff a configured source's v1 and v2 snapshots at provision
    granularity. In production this would fetch the current published
    version; for the prototype, sources are snapshotted for demo
    reliability, per the architecture.
    """
    as_of = as_of or date.today()
    source: SourceConfig = domain_pack.source(source_id)

    v1_text = _read_source_file(domain_pack.base_path, source.v1_path)
    v2_text = _read_source_file(domain_pack.base_path, source.v2_path)

    if v1_text is None or v2_text is None:
        record = ChangeRecord(
            source_id=source.source_id,
            instrument=source.instrument,
            url=source.url,
            reached=False,
            stale=True,
            verification=None,
            changes=[],
        )
    else:
        verification = VerificationStatus(
            source_id=source.source_id,
            last_verified=parse_iso_date(source.last_verified),
            max_age_days=source.max_verification_age_days,
            as_of=as_of,
        )
        changes = diff_documents(v1_text, v2_text)
        record = ChangeRecord(
            source_id=source.source_id,
            instrument=source.instrument,
            url=source.url,
            reached=True,
            stale=verification.stale,
            verification=verification,
            changes=changes,
            v1_sha256=_sha256(v1_text),
            v2_sha256=_sha256(v2_text),
        )

    if atlas is not None:
        # A dedicated, separately-queryable event: SOURCE was accessed, here
        # is exactly what was read (by hash), independent of any obligation.
        # AtlasStore.entries_for_source() reads this back as the source's own
        # monitoring history — reached/unreached, changed/unchanged, and the
        # fingerprint of what was actually read, every time it was checked.
        atlas.append(
            agent="SURVEY",
            step="source_accessed",
            payload={
                "source_id": record.source_id,
                "url": record.url,
                "reached": record.reached,
                "stale": record.stale,
                "v1_sha256": record.v1_sha256,
                "v2_sha256": record.v2_sha256,
                "provisions_changed": [c.reference for c in record.changes],
            },
        )
        atlas.append(
            agent="SURVEY",
            step="change_detected",
            payload=record.as_dict(),
        )

    return record
