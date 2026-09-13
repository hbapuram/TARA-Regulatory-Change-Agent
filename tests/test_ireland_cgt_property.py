"""domains/ireland-cgt-property.yaml — the third proof that a new domain is a
YAML file rather than a code change, and the pack that closed a coverage gap
found by running the system end to end rather than by reading it.

The gap: an Irish citizen who has become US tax resident and disposes of a
house in Ireland matched none of the five packs previously loaded. Each of
those five answers was individually correct (instrument type, tax residency,
citizenship, EEA nationality, corridor citizenship pre-filter) and the
aggregate was still wrong, because nothing modelled a disposal of Irish land.

These tests exercise the pack through the same pipeline every other pack uses
and pin the two behaviours that matter most: that a non-resident is still
brought into scope by the situs of the asset, and that the principal private
residence question is asked rather than assumed.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from tara import pipeline
from tara.agents import compass
from tara.core.domain_pack import load_domain_pack

REPO_ROOT = Path(__file__).resolve().parent.parent

PACK = REPO_ROOT / "domains" / "ireland-cgt-property.yaml"

# An Irish emigrant's disposed family home. Deliberately NOT in
# registers/holder_register.json: the committed register models a different
# holder entirely, and these tests should not depend on that file growing a
# holding for them.
DISPOSED_HOME = {
    "holding_id": "HLD-TEST-HOME",
    "instrument_type": "residential_property",
    "jurisdiction": "Ireland",
    "acquisition_date": "2016-05-20",
    "disposal_date": "2026-07-15",
    "disposal_consideration": 1250000,
    "cgt_payment_due_date": "2026-12-15",
    "cgt_return_due_date": "2027-10-31",
    "holder_residency": "Irish ordinarily resident",
    "status": "disposed",
}

NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT = {"SQ-CGT-04": False}


def _pack():
    return load_domain_pack(PACK)


def _assess(holding, answers, tenant="t"):
    return compass.assess(_pack(), holding, answers, tenant_id=tenant)


def test_pack_loads_with_no_code_change():
    pack = _pack()
    assert pack.domain_id == "ireland-cgt-property"
    assert not pack.is_corridor
    assert set(pack.obligations) == {
        "OBL-CGT-001", "OBL-CGT-002", "OBL-CGT-003",
        "OBL-CGT-004", "OBL-CGT-005", "OBL-CGT-006",
    }


def test_confirms_for_a_non_resident_on_the_situs_of_the_asset():
    """The whole point of the pack: residence does not take an Irish house out
    of the Irish CGT charge. The holder here is not Irish tax resident.
    """
    determination = _assess(DISPOSED_HOME, NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT)
    assert determination.status == "CONFIRMED"


def test_asks_rather_than_assumes_the_principal_private_residence_question():
    """SQ-CGT-04 is deliberately not answerable from the register. With no
    answer on file COMPASS must return INDETERMINATE naming that question —
    never guess, in either direction.
    """
    determination = _assess(DISPOSED_HOME, {})
    assert determination.status == "INDETERMINATE"
    assert determination.missing_question == "SQ-CGT-04"


def test_full_principal_private_residence_relief_exempts():
    determination = _assess(DISPOSED_HOME, {"SQ-CGT-04": True}, tenant="ppr")
    assert determination.status == "EXEMPT"
    assert determination.relied_on == "SQ-CGT-04"
    assert "principal private residence" in determination.reason.lower()


def test_asset_outside_the_state_is_exempt():
    """Section 1.1's charge on a non-resident reaches land *in the State*
    only — a Spanish apartment is not within it.
    """
    spanish = dict(DISPOSED_HOME, jurisdiction="Spain", holding_id="HLD-TEST-ES")
    determination = _assess(spanish, NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT, tenant="es")
    assert determination.status == "EXEMPT"
    assert determination.relied_on == "SQ-CGT-02"


def test_a_holding_still_held_is_exempt_because_no_disposal_has_occurred():
    still_held = dict(DISPOSED_HOME, status="held", holding_id="HLD-TEST-HELD")
    determination = _assess(still_held, NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT, tenant="held")
    assert determination.status == "EXEMPT"
    assert determination.relied_on == "SQ-CGT-03"


def test_a_financial_holding_is_exempt_on_instrument_type():
    """This pack and domains/tax.yaml must not both claim the same holding:
    an offshore fund belongs to tax.yaml, a house belongs here.
    """
    fund = dict(DISPOSED_HOME, instrument_type="offshore_fund", holding_id="HLD-TEST-FUND")
    determination = _assess(fund, NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT, tenant="fund")
    assert determination.status == "EXEMPT"
    assert determination.relied_on == "SQ-CGT-01"


def test_statutory_dates_come_from_the_register_not_from_arithmetic(tmp_path):
    """The payment and filing triggers read real dates off the register rather
    than deriving them from disposal_date by an assumed interval — the same
    decision domains/ireland-irp.yaml makes for irp_expiry_date. Pin it, so a
    later 'simplification' back to interval arithmetic fails here.
    """
    from tara.mcp_server.context import build_context

    ctx = build_context(
        domain_yaml=PACK,
        register_json=REPO_ROOT / "registers" / "holder_register.json",
        atlas_path=tmp_path / "atlas_log.jsonl",
        almanac_version_path=tmp_path / "graph_version.json",
    )
    ctx.register["holdings"].append(DISPOSED_HOME)

    _, gaps = pipeline.gaps_for(
        ctx, "HLD-TEST-HOME", NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT,
        as_of=date(2026, 9, 12),
    )
    by_id = {g.obligation_id: g for g in gaps}
    assert by_id["OBL-CGT-003"].trigger_date == "2026-12-15"   # payment
    assert by_id["OBL-CGT-004"].trigger_date == "2027-10-31"   # Form CG1
    assert by_id["OBL-CGT-001"].trigger_date == "2026-07-15"   # the disposal itself


def test_evidence_is_checked_at_the_statutory_rate(tmp_path):
    """33% closes; 30% is returned. Exactness, not approximation."""
    from tara.mcp_server.context import build_context
    from tara.agents import course

    ctx = build_context(
        domain_yaml=PACK,
        register_json=REPO_ROOT / "registers" / "holder_register.json",
        atlas_path=tmp_path / "atlas_log.jsonl",
        almanac_version_path=tmp_path / "graph_version.json",
    )
    ctx.register["holdings"].append(DISPOSED_HOME)

    action = course.Action(
        action_id="ACT-OBL-CGT-002-HLD-TEST-HOME", obligation_id="OBL-CGT-002",
        holding_id="HLD-TEST-HOME", owner="Test", deadline=None,
        required_evidence_type="cgt_computation", depends_on=(),
        escalated=False, escalation_reason=None,
    )
    base = {"artefact_type": "cgt_computation", "annual_exemption_applied": 1270}

    wrong = pipeline.verify_action(
        ctx, action, dict(base, rate_applied=0.30, computed_tax=300000.0),
        profile_answers=NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT, as_of=date(2026, 9, 12),
    )
    assert wrong.outcome == "returned"
    assert "33%" in wrong.reason

    right = pipeline.verify_action(
        ctx, action, dict(base, rate_applied=0.33, computed_tax=330000.0),
        profile_answers=NOT_ONLY_OR_MAIN_RESIDENCE_THROUGHOUT, as_of=date(2026, 9, 12),
    )
    assert right.outcome == "closed"
