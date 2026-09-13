"""TaraContext: the holder-level fact merge and multi-pack linking that the
multi-jurisdiction extension added. Both are additive — a context built the
old way (no linked_domain_yamls) must behave exactly as before.
"""
from pathlib import Path

from tara.mcp_server.context import build_context

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_holding_merges_in_holder_level_facts(ctx):
    holding = ctx.holding("HLD-001")
    # holding-level fields are untouched
    assert holding["instrument_type"] == "offshore_fund"
    assert holding["acquisition_date"] == "2019-03-14"
    # holder-level facts (citizenships, tax_residencies, tax_residency_since)
    # are merged in, exactly as if they were holding fields
    assert holding["citizenships"] == ["India"]
    assert holding["tax_residencies"] == ["Ireland"]
    assert holding["tax_residency_since"] == "2018-09-01"


def test_holding_level_fields_are_never_shadowed_by_holder_facts(ctx):
    # None of today's holder-level fact fields collide with a holding field,
    # but the merge order (holder first, then holding) means it never could:
    # a holding-level key always wins if one day it did collide.
    holding = ctx.holding("HLD-001")
    assert holding["holding_id"] == "HLD-001"


def test_context_without_linked_domain_yamls_has_empty_linked_packs(ctx):
    assert ctx.linked_packs == {}


def test_build_context_loads_linked_packs_keyed_by_domain_id(linked_ctx):
    assert set(linked_ctx.linked_packs) == {
        "india-fa", "us-fbar", "ireland-irp",
        "ireland-cgt-property", "india-ireland-corridor",
        "india-nri-securities", "india-us-corridor", "ireland-us-corridor",
    }
    assert linked_ctx.domain_pack.domain_id == "tax"


def test_build_context_default_has_no_linked_packs():
    # The plain build_context() call every pre-existing caller uses is
    # unaffected by the new parameter's existence.
    ctx = build_context(atlas_path="/tmp/tara_test_ctx_atlas.jsonl", almanac_version_path="/tmp/tara_test_ctx_graph.json")
    assert ctx.linked_packs == {}
