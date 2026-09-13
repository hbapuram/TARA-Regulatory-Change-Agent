from pathlib import Path

from tara.core.diff import diff_documents, split_into_provisions

REPO_ROOT = Path(__file__).resolve().parent.parent
V1 = (REPO_ROOT / "data" / "sources" / "revenue_guidance_v1.txt").read_text()
V2 = (REPO_ROOT / "data" / "sources" / "revenue_guidance_v2.txt").read_text()


def test_split_into_provisions_finds_all_sections():
    provisions = split_into_provisions(V1)
    assert set(provisions) == {
        "Section 4.1", "Section 4.2", "Section 4.3", "Section 4.4", "Section 4.5",
    }


def test_diff_documents_flags_only_changed_and_added_provisions():
    changes = diff_documents(V1, V2)
    by_ref = {c.reference: c for c in changes}

    # Section 4.3's rate changed -> amended.
    assert by_ref["Section 4.3"].change_type == "amended"
    assert "41 per cent" in by_ref["Section 4.3"].before
    assert "38 per cent" in by_ref["Section 4.3"].after

    # Sections 4.1, 4.2, 4.4, 4.5 are untouched and must not appear at all.
    assert "Section 4.1" not in by_ref
    assert "Section 4.2" not in by_ref
    assert "Section 4.4" not in by_ref
    assert "Section 4.5" not in by_ref
    assert len(by_ref) == 1
