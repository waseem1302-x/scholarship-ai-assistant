import json
from pathlib import Path

LEDGER = (
    Path(__file__).parent / "fixtures" / "catalogue_extraction" / "source_snapshot_ledger.v1.json"
)


def test_source_snapshot_ledger_freezes_observed_mext_and_open_doors_versions() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    assert ledger["schema_version"] == "catalogue-source-snapshot-ledger.v1"
    entries = ledger["entries"]
    assert {entry["family"] for entry in entries} == {"mext", "open_doors"}
    assert any(entry["content_type"] == "application/pdf" for entry in entries)
    for entry in entries:
        assert entry["source_url"].startswith("https://")
        assert len(entry["raw_sha256"]) == 64
        assert len(entry["normalized_sha256"]) == 64
        assert entry["byte_count"] > 0
        assert entry["normalized_character_count"] > 0


def test_snapshot_ledger_does_not_misrepresent_unpersisted_payloads_as_protected_fixtures() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    assert all(entry["raw_fixture_path"] is None for entry in ledger["entries"])
