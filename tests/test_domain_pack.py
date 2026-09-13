from pathlib import Path

import pytest

from tara.core.domain_pack import DomainPackError, load_domain_pack
from tara.core.interactions import load_interaction_packs

REPO_ROOT = Path(__file__).resolve().parent.parent
TAX_YAML = REPO_ROOT / "domains" / "tax.yaml"


def test_loads_tax_domain_pack():
    pack = load_domain_pack(TAX_YAML)
    assert pack.domain_id == "tax"
    assert "revenue-27-01a-02" in pack.sources
    assert "OBL-001" in pack.obligations
    assert len(pack.scoping_questions) == 3
    assert len(pack.date_triggers) == 5


def test_open_tenant_split_is_visible():
    pack = load_domain_pack(TAX_YAML)
    # open: obligations don't vary by tenant
    assert pack.obligation("OBL-001").text
    # tenant: register schema, scoping questions, date triggers, evidence rules
    assert pack.register_schema["entity"] == "holding"
    assert any(q.question_id == "SQ-03" and not q.answerable_from_register for q in pack.scoping_questions)


def test_obl002_superseded_by_obl002b():
    pack = load_domain_pack(TAX_YAML)
    assert pack.obligation("OBL-001").depends_on == ()
    assert pack.obligation("OBL-002").superseded_by == "OBL-002B"
    assert pack.obligation("OBL-002B").supersedes == "OBL-002"


def test_missing_required_block_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("domain_id: x\ntitle: y\nsector: z\nopen: {}\ntenant: {}\n")
    with pytest.raises(DomainPackError):
        load_domain_pack(bad)


def test_ordinary_pack_is_not_a_corridor():
    pack = load_domain_pack(TAX_YAML)
    assert pack.corridor is None
    assert pack.is_corridor is False


def test_corridor_pack_carries_its_metadata():
    """The India-Ireland corridor is no longer its own hand-written
    DomainPack file — it's synthesized from the shared, compact
    domains/interactions.yaml store (see tara/core/interactions.py). The
    synthesized pack must still be an ordinary DomainPack carrying the same
    `corridor` metadata block MERIDIAN's discovery filter reads.
    """
    packs = load_interaction_packs(REPO_ROOT / "domains" / "interactions.yaml", base_path=REPO_ROOT)
    pack = packs["india-ireland-corridor"]
    assert pack.is_corridor is True
    assert pack.corridor == {"citizenship_of": "India", "tax_residency_of": "Ireland"}


def test_standalone_country_packs_load_like_any_other_pack():
    for filename, domain_id in [
        ("india.yaml", "india-fa"),
        ("us.yaml", "us-fbar"),
        ("ireland-irp.yaml", "ireland-irp"),
    ]:
        pack = load_domain_pack(REPO_ROOT / "domains" / filename)
        assert pack.domain_id == domain_id
        assert pack.is_corridor is False
        assert pack.obligations
        assert pack.scoping_questions
