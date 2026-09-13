"""Builds the Source Registry: a real, queryable SQLite database of every
regulatory source TARA knows about, every obligation traced back to it, and
every time SURVEY has actually checked it — plus a self-contained, readable
HTML view over that same database.

This is the direct answer to "I need to see what data is being referenced
from where, and at what time it was updated" — which is not a new
requirement, it's guardrail #3 from the original MERIDIAN handoff document:
"Compliance facts get cross-checked. Regulatory thresholds and rates...
are versioned with a 'last verified' date and treated as perishable — not
trusted to model memory alone." That fact already existed in every domain
pack (source.last_verified, source.url) and in ATLAS's source_accessed
events; it just had no legible, queryable home of its own. This gives it
one.

Two outputs, same underlying facts:
    registers/source_registry.db     — real SQLite, query it with any tool
    tools/source_registry.html       — the same data, rendered readable

Regenerate with:
    python tools/build_source_registry.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tara.agents import survey  # noqa: E402
from tara.atlas.store import AtlasStore  # noqa: E402
from tara.core.dates import VerificationStatus, parse_iso_date  # noqa: E402
from tara.core.domain_pack import DomainPack, load_domain_pack  # noqa: E402
from tara.core.interactions import load_interaction_packs  # noqa: E402

DB_PATH = REPO_ROOT / "registers" / "source_registry.db"
ATLAS_PATH = REPO_ROOT / "registers" / "source_registry_atlas.jsonl"
HTML_PATH = REPO_ROOT / "tools" / "source_registry.html"

DOMAIN_YAMLS = [
    REPO_ROOT / "domains" / "tax.yaml",
    REPO_ROOT / "domains" / "india.yaml",
    REPO_ROOT / "domains" / "us.yaml",
    REPO_ROOT / "domains" / "ireland-irp.yaml",
    # Added 2026-09-12: this list is independent of
    # tara/mcp_server/server.py's DEFAULT_LINKED_DOMAIN_YAMLS, so a new pack
    # has to be registered in both places or the registry silently omits it
    # (as it did here for a full day after the pack shipped). If a third
    # place ever needs this list, it should be extracted into one shared
    # constant instead of copied a third time.
    REPO_ROOT / "domains" / "ireland-cgt-property.yaml",
]
# Cross-jurisdiction interactions (India-Ireland, and any future pair) live
# in the shared, compact domains/interactions.yaml store rather than as
# full pack files — see tara/core/interactions.py. Each entry is
# synthesized into an ordinary DomainPack here, exactly as build_context()
# does for a running server, so the registry shows it identically to every
# standalone pack: same tables, same joins, same freshness computation.
INTERACTIONS_YAML = REPO_ROOT / "domains" / "interactions.yaml"

SCHEMA = """
CREATE TABLE domains (
    domain_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sector TEXT NOT NULL,
    is_corridor INTEGER NOT NULL,
    corridor_citizenship_of TEXT,
    corridor_tax_residency_of TEXT
);

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL REFERENCES domains(domain_id),
    instrument TEXT NOT NULL,
    issuing_authority TEXT NOT NULL,
    url TEXT NOT NULL,
    last_verified TEXT NOT NULL,
    max_verification_age_days INTEGER NOT NULL,
    v1_path TEXT NOT NULL,
    v2_path TEXT NOT NULL
);

CREATE TABLE obligations (
    obligation_id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL REFERENCES domains(domain_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    provision TEXT NOT NULL,
    severity TEXT NOT NULL,
    artefact_type TEXT NOT NULL,
    introduced_in TEXT,
    supersedes TEXT,
    superseded_by TEXT
);

-- One row per SURVEY check of a source — independent of any obligation.
-- This is the literal, queryable answer to "when was this last checked,
-- and what did we actually read."
CREATE TABLE source_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    checked_at TEXT NOT NULL,
    reached INTEGER NOT NULL,
    changed INTEGER NOT NULL,
    stale INTEGER NOT NULL,
    v1_sha256 TEXT,
    v2_sha256 TEXT
);
"""


def build() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    if ATLAS_PATH.exists():
        ATLAS_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    atlas = AtlasStore(ATLAS_PATH)
    as_of = date.today()

    packs: list[DomainPack] = [load_domain_pack(p) for p in DOMAIN_YAMLS]
    packs += list(load_interaction_packs(INTERACTIONS_YAML, base_path=REPO_ROOT).values())

    for pack in packs:
        conn.execute(
            "INSERT INTO domains VALUES (?,?,?,?,?,?)",
            (
                pack.domain_id, pack.title, pack.sector, int(pack.is_corridor),
                (pack.corridor or {}).get("citizenship_of"),
                (pack.corridor or {}).get("tax_residency_of"),
            ),
        )

        for source in pack.sources.values():
            conn.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    source.source_id, pack.domain_id, source.instrument,
                    source.issuing_authority, source.url, source.last_verified,
                    source.max_verification_age_days, source.v1_path, source.v2_path,
                ),
            )

            # A real SURVEY check, right now, against the actual configured
            # source files — not a synthetic row. This is the same function
            # every MCP tool call and every scheduled refresh would run.
            record = survey.detect_change(pack, source.source_id, as_of=as_of, atlas=atlas)
            conn.execute(
                "INSERT INTO source_checks (source_id, checked_at, reached, changed, stale, v1_sha256, v2_sha256) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    source.source_id, as_of.isoformat(), int(record.reached),
                    int(bool(record.changes)), int(record.stale),
                    record.v1_sha256, record.v2_sha256,
                ),
            )

        for obligation in pack.obligations.values():
            conn.execute(
                "INSERT INTO obligations VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    obligation.obligation_id, pack.domain_id, obligation.source_id,
                    obligation.provision, obligation.severity, obligation.artefact_type,
                    obligation.introduced_in, obligation.supersedes, obligation.superseded_by,
                ),
            )

    conn.commit()

    # ---- Prove it's a real, queryable database: three example queries ----
    print("=" * 78)
    print("SOURCE REGISTRY — example queries against registers/source_registry.db")
    print("=" * 78)

    print("\n-- Every source, its authority, and how stale it is right now --")
    for row in conn.execute(
        "SELECT s.source_id, s.issuing_authority, s.last_verified, "
        "julianday('now') - julianday(s.last_verified) AS age_days, "
        "s.max_verification_age_days FROM sources s ORDER BY age_days DESC"
    ):
        source_id, authority, last_verified, age_days, max_age = row
        flag = "STALE" if age_days > max_age else "fresh"
        print(f"  {source_id:24s} {authority:45s} verified {last_verified}  "
              f"age={age_days:5.1f}d / max {max_age}d  [{flag}]")

    print("\n-- Every obligation, traced back to its source and citation --")
    for row in conn.execute(
        "SELECT o.obligation_id, o.provision, s.instrument, s.url "
        "FROM obligations o JOIN sources s ON o.source_id = s.source_id "
        "ORDER BY o.domain_id, o.obligation_id"
    ):
        obligation_id, provision, instrument, url = row
        print(f"  {obligation_id:14s} {provision:14s} <- {instrument} ({url})")

    print("\n-- Full check history for one source (India Schedule FA) --")
    for row in conn.execute(
        "SELECT checked_at, reached, changed, stale, v1_sha256 "
        "FROM source_checks WHERE source_id = 'cbdt-schedule-fa'"
    ):
        checked_at, reached, changed, stale, v1_sha = row
        print(f"  checked {checked_at}  reached={bool(reached)}  changed={bool(changed)}  "
              f"stale={bool(stale)}  v1_sha256={v1_sha[:16]}...")

    conn.close()
    print(f"\nWrote {DB_PATH.relative_to(REPO_ROOT)}")

    _build_html()
    print(f"Wrote {HTML_PATH.relative_to(REPO_ROOT)}")


def _build_html() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    domains = [dict(r) for r in conn.execute("SELECT * FROM domains ORDER BY domain_id")]
    sources = [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY domain_id, source_id")]
    obligations = [dict(r) for r in conn.execute("SELECT * FROM obligations ORDER BY domain_id, obligation_id")]
    checks = [dict(r) for r in conn.execute("SELECT * FROM source_checks ORDER BY checked_at DESC")]
    conn.close()

    data = {"domains": domains, "sources": sources, "obligations": obligations, "checks": checks}
    template = (REPO_ROOT / "tools" / "source_registry_template.html").read_text(encoding="utf-8")
    if "__REGISTRY_DATA_JSON__" not in template:
        raise SystemExit("source_registry_template.html is missing the __REGISTRY_DATA_JSON__ placeholder")
    HTML_PATH.write_text(
        template.replace("__REGISTRY_DATA_JSON__", json.dumps(data, separators=(",", ":"))),
        encoding="utf-8",
    )


if __name__ == "__main__":
    build()
