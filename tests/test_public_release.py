from __future__ import annotations

from pathlib import Path

import pytest

from tools.build_public_release import prepare_output


def test_release_builder_refuses_unrecognized_existing_directory(tmp_path: Path):
    unrelated = tmp_path / "tara-public-release-important"
    unrelated.mkdir()
    sentinel = unrelated / "keep.txt"
    sentinel.write_text("do not delete", encoding="utf-8")

    with pytest.raises(ValueError, match="unrecognized existing directory"):
        prepare_output(unrelated)

    assert sentinel.read_text(encoding="utf-8") == "do not delete"


def test_release_builder_refuses_arbitrary_output_name(tmp_path: Path):
    unrelated = tmp_path / "ordinary-folder"
    with pytest.raises(ValueError, match="must start with"):
        prepare_output(unrelated)
    assert not unrelated.exists()


def test_release_builder_replaces_only_its_marked_directory(tmp_path: Path):
    release = tmp_path / "tara-public-release-test"
    release.mkdir()
    (release / "PUBLIC_RELEASE_REVIEW.md").write_text("owned", encoding="utf-8")
    (release / "stale.txt").write_text("stale", encoding="utf-8")

    prepare_output(release)

    assert release.is_dir()
    assert list(release.iterdir()) == []
