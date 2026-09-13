from tara.agents.legend import decompose
from tara.agents.survey import detect_change


def test_decompose_returns_full_catalogued_set_on_first_run(ctx):
    change_record = detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    obligations = decompose(ctx.domain_pack, change_record, atlas=ctx.atlas)
    ids = {o.obligation_id for o in obligations}
    assert ids == {"OBL-001", "OBL-002", "OBL-002B", "OBL-003", "OBL-004"}


def test_decompose_marks_changed_and_new_correctly(ctx):
    change_record = detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    obligations = {o.obligation_id: o for o in decompose(ctx.domain_pack, change_record, atlas=ctx.atlas)}

    assert obligations["OBL-002"].change_type == "amended"
    assert obligations["OBL-002B"].change_type == "amended"
    assert obligations["OBL-001"].change_type == "unchanged"


def test_decompose_skips_already_known_unchanged_obligations(ctx):
    change_record = detect_change(ctx.domain_pack, "revenue-27-01a-02", atlas=ctx.atlas)
    obligations = decompose(
        ctx.domain_pack, change_record, existing_graph={"OBL-001", "OBL-003", "OBL-004"}, atlas=ctx.atlas
    )
    ids = {o.obligation_id for o in obligations}
    # OBL-001/003/004 are untouched by this diff and already known -> excluded.
    assert "OBL-001" not in ids
    assert "OBL-003" not in ids
    assert "OBL-004" not in ids
    # OBL-002/002B are touched by this diff -> always reported.
    assert {"OBL-002", "OBL-002B"} <= ids
