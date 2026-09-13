from datetime import date

from tara.agents.survey import detect_change


def test_detect_change_reports_only_changed_provisions(ctx):
    record = detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    assert record.reached is True
    refs = {c.reference for c in record.changes}
    assert refs == {"Section 4.3"}


def test_detect_change_stale_flag(ctx):
    # last_verified is 2026-09-01, max age 120 days -> stale well past 2026-12-30
    record = detect_change(ctx.domain_pack, "revenue-27-01a-02", as_of=date(2027, 6, 1), atlas=ctx.atlas)
    assert record.stale is True


def test_detect_change_writes_to_atlas(ctx):
    detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    entries = ctx.atlas.all_entries()
    assert len(entries) == 2
    assert {e["agent"] for e in entries} == {"SURVEY"}
    assert {e["step"] for e in entries} == {"source_accessed", "change_detected"}


def test_detect_change_records_a_content_fingerprint(ctx):
    record = detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    assert record.v1_sha256 is not None
    assert record.v2_sha256 is not None
    assert record.v1_sha256 != record.v2_sha256  # v1 and v2 genuinely differ

    # Re-running against the same files reproduces the exact same fingerprint —
    # this is what lets an auditor later prove the source hasn't drifted.
    record2 = detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    assert record2.v1_sha256 == record.v1_sha256
    assert record2.v2_sha256 == record.v2_sha256


def test_source_access_history_is_queryable_independent_of_obligations(ctx):
    detect_change(ctx.domain_pack, "revenue-27-01a-02", as_of=date(2026, 9, 6), atlas=ctx.atlas)
    detect_change(ctx.domain_pack, "revenue-27-01a-02", as_of=date(2027, 6, 1), atlas=ctx.atlas)

    history = ctx.atlas.entries_for_source("revenue-27-01a-02")
    assert len(history) == 2
    assert history[0]["payload"]["stale"] is False
    assert history[1]["payload"]["stale"] is True
    assert all(h["payload"]["v1_sha256"] for h in history)


def test_unreached_source_has_no_fingerprint(ctx, tmp_path):
    import shutil

    from tara.core.domain_pack import load_domain_pack

    # Build an isolated copy of the repo root whose v2 file is missing, to
    # exercise the "reached=False" path without touching the real domain pack.
    (tmp_path / "domains").mkdir()
    shutil.copytree(ctx.domain_pack.base_path / "data", tmp_path / "data")
    original = (ctx.domain_pack.base_path / "domains" / "tax.yaml").read_text()
    broken_yaml = tmp_path / "domains" / "tax.yaml"
    broken_yaml.write_text(original.replace("data/sources/revenue_guidance_v2.txt", "data/sources/missing.txt"))

    pack = load_domain_pack(broken_yaml)
    record = detect_change(pack, "revenue-27-01a-02", atlas=ctx.atlas)
    assert record.reached is False
    assert record.v1_sha256 is None
    assert record.v2_sha256 is None
