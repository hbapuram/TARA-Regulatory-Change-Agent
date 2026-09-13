from tara.agents.compass import DeterminationCache, _matches, assess


def test_indeterminate_when_register_lacks_remittance_answer(ctx):
    holding = ctx.holding("HLD-001")
    determination = assess(ctx.domain_pack, holding, {}, tenant_id="HLD-001", atlas=ctx.atlas)
    assert determination.status == "INDETERMINATE"
    assert determination.missing_question == "SQ-03"


def test_confirmed_once_missing_fact_is_supplied(ctx):
    holding = ctx.holding("HLD-001")
    determination = assess(ctx.domain_pack, holding, {"SQ-03": False}, tenant_id="HLD-001", atlas=ctx.atlas)
    assert determination.status == "CONFIRMED"


def test_exempt_on_instrument_type_outside_scope(ctx):
    holding = ctx.holding("HLD-003")  # direct_equity — not a covered instrument type
    determination = assess(ctx.domain_pack, holding, {}, tenant_id="HLD-003", atlas=ctx.atlas)
    assert determination.status == "EXEMPT"
    assert determination.relied_on == "SQ-02"


def test_indeterminate_when_remittance_basis_previously_claimed(ctx):
    # SQ-03=True is an answer, not a missing fact — it must be evaluated,
    # not silently ignored the way an earlier version of COMPASS did.
    holding = ctx.holding("HLD-001")
    determination = assess(ctx.domain_pack, holding, {"SQ-03": True}, tenant_id="HLD-001", atlas=ctx.atlas)
    assert determination.status == "INDETERMINATE"
    assert determination.relied_on == "SQ-03"
    assert determination.missing_question is None


def test_determination_cache_avoids_relitigation():
    cache = DeterminationCache()

    assert cache.get("H-001", "HLD-001", {}) is None
    from tara.agents.compass import Determination
    d = Determination("HLD-001", "CONFIRMED", "test", None, None)
    cache.put("H-001", "HLD-001", {"SQ-01": "x"}, d)
    assert cache.get("H-001", "HLD-001", {"SQ-01": "x"}) is d


def test_determination_cache_hashes_list_valued_answers():
    # citizenships/tax_residencies-style register fields are list-valued —
    # the cache key must not blow up on them (the multi-jurisdiction packs
    # answer scoping questions straight off these fields).
    cache = DeterminationCache()
    from tara.agents.compass import Determination
    d = Determination("HLD-001", "EXEMPT", "test", "SQ-IN-01", None)
    cache.put("HLD-001", "HLD-001", {"SQ-IN-01": ["Ireland"]}, d)
    assert cache.get("HLD-001", "HLD-001", {"SQ-IN-01": ["Ireland"]}) is d


def test_contains_operator_matches_list_valued_answers():
    assert _matches({"contains": "India"}, ["India", "United Kingdom"]) is True
    assert _matches({"contains": "India"}, ["Ireland"]) is False
    # A non-list answer (a config mistake, or a field that turned out to be
    # scalar) fails closed rather than raising.
    assert _matches({"contains": "India"}, None) is False
    assert _matches({"contains": "India"}, "India") is True  # "India" in "India" as a substring is also True for strings, which is fine — a scalar exact match still passes.
