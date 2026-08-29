import json
from pathlib import Path

from app.modules.opportunities.publication_readiness import (
    PUBLICATION_READINESS_POLICY_VERSION,
    PublicationReadinessPolicy,
)

FIXTURE = Path(__file__).parent / "fixtures/catalogue_readiness/three_family_gold.v1.json"


def test_three_family_gold_fixture_is_synthetic_exact_and_complete() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert payload["policy_version"] == PUBLICATION_READINESS_POLICY_VERSION
    assert "Non-authoritative synthetic" in payload["notice"]
    assert {record["family"] for record in payload["records"]} == {
        "Chinese Government Scholarship",
        "DAAD EPOS",
        "Erasmus Mundus Joint Masters",
    }
    required = set(PublicationReadinessPolicy.REQUIRED_DIMENSIONS)
    for record in payload["records"]:
        artifact = record["artifact"]
        mappings = record["evidence_mappings"]
        assert record["expected"]["ready"] is True
        assert {mapping["dimension"] for mapping in mappings} == required
        assert all(mapping["artifact_id"] == artifact["id"] for mapping in mappings)
        assert all(mapping["excerpt"] in artifact["normalized_text"] for mapping in mappings)
