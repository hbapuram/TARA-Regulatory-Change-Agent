"""Stable identifiers and hashing helpers used by ATLAS's append-only chain."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_hash(payload: dict[str, Any]) -> str:
    """A deterministic hash of a JSON-serialisable payload, used to chain
    ATLAS entries together (each entry's hash covers the previous entry's
    hash, so a tampered or reordered ledger is detectable).
    """
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
