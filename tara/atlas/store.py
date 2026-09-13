"""ATLAS — Audit Trail and Lineage Assurance Store.

Append-only across every agent: change detected, obligation decomposed,
applicability determined, gap found, action opened, evidence submitted,
closure reasoned. Entries are added, never edited or deleted. Backed by a
plain JSONL file so the ledger is inspectable without tooling, and each
entry's hash covers the previous entry's hash so tampering or reordering is
detectable.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.ids import stable_hash

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class AtlasEntry:
    seq: int
    timestamp: str
    agent: str            # SURVEY | LEGEND | ALMANAC | COMPASS | PLOT | COURSE | ANCHOR
    step: str             # e.g. "change_detected", "obligation_decomposed", "closure"
    obligation_id: str | None
    tenant_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str = field(init=False)

    def __post_init__(self):
        body = {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "agent": self.agent,
            "step": self.step,
            "obligation_id": self.obligation_id,
            "tenant_id": self.tenant_id,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }
        object.__setattr__(self, "entry_hash", stable_hash(body))

    def to_json_line(self) -> str:
        d = asdict(self)
        return json.dumps(d, sort_keys=True, default=str)


class AtlasStore:
    """An append-only JSONL ledger rooted at ``path``."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _last_hash(self) -> str:
        last = None
        for line in self._read_lines():
            last = line
        if last is None:
            return GENESIS_HASH
        return json.loads(last)["entry_hash"]

    def _read_lines(self):
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line

    def _next_seq(self) -> int:
        count = sum(1 for _ in self._read_lines())
        return count + 1

    def append(
        self,
        agent: str,
        step: str,
        payload: dict[str, Any],
        obligation_id: str | None = None,
        tenant_id: str | None = None,
    ) -> AtlasEntry:
        entry = AtlasEntry(
            seq=self._next_seq(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=agent,
            step=step,
            obligation_id=obligation_id,
            tenant_id=tenant_id,
            payload=payload,
            prev_hash=self._last_hash(),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(entry.to_json_line() + "\n")
        return entry

    def all_entries(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self._read_lines()]

    def entries_for_source(self, source_id: str) -> list[dict[str, Any]]:
        """Every time this source was accessed — SURVEY's own monitoring
        history, independent of any single obligation: reached/unreached,
        changed/unchanged, and the sha256 of exactly what was read each
        time. This is the "was this source actually checked, and what did
        we read" audit trail; reconstruct() answers the different question
        of "what happened to this one obligation".
        """
        return [
            e for e in self.all_entries()
            if e["step"] == "source_accessed" and e["payload"].get("source_id") == source_id
        ]

    def reconstruct(self, obligation_id: str) -> list[dict[str, Any]]:
        """The full chain — from source provision to closed action — for a
        single obligation, in the order it was recorded.
        """
        return [e for e in self.all_entries() if e["obligation_id"] == obligation_id]

    def verify_chain(self) -> bool:
        """Recomputes each entry's hash from its recorded fields and checks
        prev_hash linkage. Returns False if the ledger has been tampered
        with or reordered.
        """
        prev = GENESIS_HASH
        for raw in self.all_entries():
            body = {
                "seq": raw["seq"],
                "timestamp": raw["timestamp"],
                "agent": raw["agent"],
                "step": raw["step"],
                "obligation_id": raw["obligation_id"],
                "tenant_id": raw["tenant_id"],
                "payload": raw["payload"],
                "prev_hash": raw["prev_hash"],
            }
            if raw["prev_hash"] != prev:
                return False
            if stable_hash(body) != raw["entry_hash"]:
                return False
            prev = raw["entry_hash"]
        return True
