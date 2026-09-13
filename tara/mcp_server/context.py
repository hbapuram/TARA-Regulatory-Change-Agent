"""Shared, process-wide state for the MCP server: the loaded domain pack,
the tenant register, the ATLAS ledger and the COMPASS determination cache.
One instance per running server — this is what every tool call reads and
writes through.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agents.compass import DeterminationCache
from ..atlas.store import AtlasStore
from ..core.domain_pack import DomainPack, load_domain_pack
from ..core.interactions import load_interaction_packs

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# Holder-level facts (as opposed to per-holding facts) that a scoping
# question is allowed to read off a holding dict via register_field, exactly
# as it would read any other holding field. A single-jurisdiction pack like
# tax.yaml never references these; a corridor pack (India-Ireland) or a
# standalone country pack (India, US) can, because its applicability turns
# on who the holder *is* (citizen of X, tax resident of Y), not on any one
# holding.
HOLDER_LEVEL_FACT_FIELDS = ("citizenships", "tax_residencies", "tax_residency_since", "eea_swiss_uk_national")


@dataclass
class TaraContext:
    domain_pack: DomainPack
    register: dict[str, Any]
    atlas: AtlasStore
    determination_cache: DeterminationCache
    almanac_version_path: Path
    # Additional domain packs loaded alongside domain_pack, keyed by
    # domain_id — populated only for a multi-jurisdiction context. Every
    # existing single-pack call site is unaffected: it keeps reading
    # domain_pack and never looks at this dict. MERIDIAN is the only agent
    # that reads it, to discover standalone country packs and corridor packs
    # and re-run the existing tenant agents (unmodified) against each.
    linked_packs: dict[str, DomainPack] = field(default_factory=dict)

    def holding(self, holding_id: str) -> dict[str, Any]:
        for holding in self.register["holdings"]:
            if holding["holding_id"] == holding_id:
                holder = self.register.get("holder", {})
                merged = {
                    k: v for k, v in holder.items()
                    if k in HOLDER_LEVEL_FACT_FIELDS
                }
                merged.update(holding)
                # Derived holder-level fact, not a register field anyone has
                # to supply: a "United States person" for FBAR/FATCA purposes
                # is a US citizen OR a US tax resident (26 U.S.C. § 7701(b);
                # 31 CFR 1010.350) — either limb brings a holder into scope.
                # us.yaml's own SQ-US-01 used to key off citizenship alone,
                # which its own fail_reason_template already flagged as a
                # known gap ("US residency, not modeled in this register,
                # would also bring a holder into scope"). Deriving the OR
                # here means every domain pack sees one boolean fact instead
                # of re-deriving the same two-field check itself.
                merged["us_tax_person"] = (
                    "United States" in (holder.get("citizenships") or [])
                    or "United States" in (holder.get("tax_residencies") or [])
                )
                return merged
        raise KeyError(f"unknown holding_id: {holding_id}")

    def owner_name(self) -> str | None:
        return self.register.get("holder", {}).get("name")


def build_context(
    domain_yaml: str | Path = REPO_ROOT / "domains" / "tax.yaml",
    register_json: str | Path = REPO_ROOT / "registers" / "holder_register.json",
    atlas_path: str | Path = REPO_ROOT / "registers" / "atlas_log.jsonl",
    almanac_version_path: str | Path = REPO_ROOT / "registers" / "graph_version.json",
    linked_domain_yamls: list[str | Path] | None = None,
    interactions_yaml: str | Path | None = None,
) -> TaraContext:
    """``linked_domain_yamls`` links standalone, single-jurisdiction packs
    (India, the US, ...) exactly as before. ``interactions_yaml`` is
    separate: it points at the compact shared interactions store (see
    tara/core/interactions.py) and every interaction in it is synthesized
    into its own DomainPack and merged into the same ``linked_packs`` dict —
    MERIDIAN and every tenant agent never see the difference between a
    standalone pack and a synthesized interaction pack, both are just
    entries in ``linked_packs`` keyed by domain_id.
    """
    domain_pack = load_domain_pack(domain_yaml)
    register = json.loads(Path(register_json).read_text(encoding="utf-8"))
    atlas = AtlasStore(atlas_path)
    linked_packs: dict[str, DomainPack] = {}
    for extra_yaml in linked_domain_yamls or []:
        pack = load_domain_pack(extra_yaml)
        linked_packs[pack.domain_id] = pack
    if interactions_yaml is not None:
        linked_packs.update(load_interaction_packs(interactions_yaml, base_path=REPO_ROOT))
    return TaraContext(
        domain_pack=domain_pack,
        register=register,
        atlas=atlas,
        determination_cache=DeterminationCache(),
        almanac_version_path=Path(almanac_version_path),
        linked_packs=linked_packs,
    )
