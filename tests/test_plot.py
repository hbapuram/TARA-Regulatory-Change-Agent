from datetime import date

import pytest

from tara import pipeline
from tara.agents.compass import Determination
from tara.agents.plot import BandOrderError, align


def test_plot_refuses_a_non_confirmed_determination(ctx):
    holding = ctx.holding("HLD-001")
    obligations = pipeline.full_obligation_set(ctx)
    not_confirmed = Determination("HLD-001", "INDETERMINATE", "x", None, "SQ-03")
    with pytest.raises(BandOrderError):
        align(ctx.domain_pack, holding, obligations, not_confirmed, atlas=ctx.atlas)


def test_plot_fires_the_acceptance_criterion_trigger_date(ctx):
    determination, gaps = pipeline.gaps_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2026, 9, 6))
    assert determination.status == "CONFIRMED"
    by_obligation = {g.obligation_id: g for g in gaps}
    assert by_obligation["OBL-001"].trigger_date == "2027-03-14"
    assert by_obligation["OBL-001"].coverage == "partial"  # not yet due


def test_plot_reports_absent_once_trigger_date_has_passed(ctx):
    determination, gaps = pipeline.gaps_for(ctx, "HLD-001", {"SQ-03": False}, as_of=date(2027, 4, 1))
    by_obligation = {g.obligation_id: g for g in gaps}
    assert by_obligation["OBL-001"].coverage == "absent"


def test_plot_records_negative_findings_not_silence(ctx):
    _determination, gaps = pipeline.gaps_for(ctx, "HLD-002", {"SQ-03": False}, as_of=date(2026, 9, 6))
    # HLD-002 was acquired 2023-01-10 — under 8 years, so its first deemed
    # disposal is still in the future, but every applicable obligation is
    # still reported explicitly rather than PLOT staying silent on a
    # holding with nothing "wrong" yet.
    assert len(gaps) > 0
    assert all(g.coverage in ("partial", "absent", "not_applicable") for g in gaps)
    by_obligation = {g.obligation_id: g for g in gaps}
    assert by_obligation["OBL-001"].coverage == "partial"
    assert by_obligation["OBL-001"].trigger_date == "2031-01-10"
