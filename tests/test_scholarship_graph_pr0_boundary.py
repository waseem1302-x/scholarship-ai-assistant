import json
from pathlib import Path

from app.core.config import Settings


FIXTURE = Path(__file__).parent / "fixtures" / "scholarship_graph" / "csc_pr0_safety_boundary.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def canonical_scholarship_count(payload: dict) -> int:
    return sum(
        1
        for item in payload["canonical_scholarships"]
        if item["counts_as_scholarship"]
    )


def test_csc_fixture_has_exactly_one_canonical_scholarship() -> None:
    assert canonical_scholarship_count(load_fixture()) == 1


def test_csc_relationship_entities_do_not_create_scholarships() -> None:
    payload = load_fixture()

    assert all(not item["counts_as_scholarship"] for item in payload["tracks"])
    assert all(not item["counts_as_scholarship"] for item in payload["institution_participation"])
    assert all(not item["counts_as_scholarship"] for item in payload["eligible_programmes"])
    assert all(not item["counts_as_scholarship"] for item in payload["local_deadlines"])
    assert all(not item["counts_as_scholarship"] for item in payload["institution_requirements"])


def test_csc_aliases_map_to_one_identity() -> None:
    aliases = load_fixture()["canonical_scholarships"][0]["aliases"]

    assert {alias.casefold() for alias in aliases} == {
        "csc",
        "cgs",
        "chinese government scholarship",
    }


def test_ambiguous_candidates_remain_unresolved() -> None:
    candidate = load_fixture()["unresolved_candidates"][0]

    assert candidate["relationship"] == "unresolved"
    assert candidate["counts_as_scholarship"] is False


def test_pr0_keeps_all_graph_and_external_capabilities_disabled_by_default() -> None:
    settings = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="pr0-safety-test-secret-that-is-at-least-32-characters",
    )

    assert settings.catalogue_graph_reads_enabled is False
    assert settings.catalogue_graph_writes_enabled is False
    assert settings.catalogue_ai_ingestion_enabled is False
    assert settings.catalogue_web_discovery_enabled is False
    assert settings.catalogue_browser_fetching_enabled is False
    assert settings.catalogue_document_intelligence_enabled is False
    assert settings.catalogue_scheduled_ingestion_enabled is False
