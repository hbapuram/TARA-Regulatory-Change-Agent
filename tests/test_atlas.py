from tara.atlas.store import AtlasStore


def test_append_and_reconstruct(tmp_path):
    store = AtlasStore(tmp_path / "atlas.jsonl")
    store.append("SURVEY", "change_detected", {"a": 1}, obligation_id="OBL-001")
    store.append("LEGEND", "obligation_decomposed", {"b": 2}, obligation_id="OBL-001")
    store.append("LEGEND", "obligation_decomposed", {"c": 3}, obligation_id="OBL-002")

    chain = store.reconstruct("OBL-001")
    assert [e["step"] for e in chain] == ["change_detected", "obligation_decomposed"]

    assert len(store.all_entries()) == 3


def test_entries_are_hash_chained_and_verifiable(tmp_path):
    store = AtlasStore(tmp_path / "atlas.jsonl")
    store.append("SURVEY", "change_detected", {"a": 1})
    store.append("LEGEND", "obligation_decomposed", {"b": 2})
    assert store.verify_chain() is True


def test_tampering_breaks_verification(tmp_path):
    path = tmp_path / "atlas.jsonl"
    store = AtlasStore(path)
    store.append("SURVEY", "change_detected", {"a": 1})
    store.append("LEGEND", "obligation_decomposed", {"b": 2})

    lines = path.read_text().splitlines()
    tampered = lines[0].replace('"a": 1', '"a": 999')
    path.write_text("\n".join([tampered] + lines[1:]) + "\n")

    tampered_store = AtlasStore(path)
    assert tampered_store.verify_chain() is False


def test_entries_for_source_filters_by_source_id(tmp_path):
    store = AtlasStore(tmp_path / "atlas.jsonl")
    store.append("SURVEY", "source_accessed", {"source_id": "revenue-27-01a-02", "reached": True})
    store.append("SURVEY", "change_detected", {"source_id": "revenue-27-01a-02"})  # not a source_accessed step
    store.append("SURVEY", "source_accessed", {"source_id": "other-source", "reached": True})
    store.append("SURVEY", "source_accessed", {"source_id": "revenue-27-01a-02", "reached": False})

    history = store.entries_for_source("revenue-27-01a-02")
    assert len(history) == 2
    assert all(e["step"] == "source_accessed" for e in history)
    assert all(e["payload"]["source_id"] == "revenue-27-01a-02" for e in history)


def test_append_only_never_edits_prior_entries(tmp_path):
    store = AtlasStore(tmp_path / "atlas.jsonl")
    store.append("ANCHOR", "closure", {"outcome": "closed"}, obligation_id="OBL-001")
    store.append("ANCHOR", "reopened", {"reason": "superseded"}, obligation_id="OBL-001")
    chain = store.reconstruct("OBL-001")
    assert len(chain) == 2
    assert chain[0]["step"] == "closure"
    assert chain[1]["step"] == "reopened"
