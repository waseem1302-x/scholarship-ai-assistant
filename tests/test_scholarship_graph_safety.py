import json
from itertools import chain
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

FIXTURE_PATH = Path("tests/fixtures/scholarship_graph/csc_reviewed.json")
GRAPH_NODE_COLLECTIONS = (
    "scholarships",
    "application_tracks",
    "participating_institutions",
    "eligible_programmes",
    "scoped_deadlines",
    "scoped_requirements",
    "sources",
)
DISABLED_CATALOGUE_FLAGS = (
    "catalogue_ai_ingestion_enabled",
    "catalogue_graph_reads_enabled",
    "catalogue_graph_writes_enabled",
    "catalogue_web_discovery_enabled",
    "catalogue_browser_fetch_enabled",
    "catalogue_document_intelligence_enabled",
    "catalogue_scheduled_ingestion_enabled",
    "catalogue_auto_publish_enabled",
)


def load_csc_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_new_graph_and_external_capabilities_are_disabled_by_default() -> None:
    settings = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="graph-safety-test-secret-at-least-32-characters",
    )

    assert all(getattr(settings, flag) is False for flag in DISABLED_CATALOGUE_FLAGS)


def test_automatic_publication_cannot_be_enabled_by_configuration() -> None:
    with pytest.raises(ValidationError, match="catalogue_auto_publish_enabled"):
        Settings(
            env="test",
            database_url="sqlite+pysqlite:///:memory:",
            jwt_secret="graph-safety-test-secret-at-least-32-characters",
            catalogue_auto_publish_enabled=True,
        )


def test_csc_fixture_contains_exactly_one_canonical_scholarship() -> None:
    fixture = load_csc_fixture()
    collections = [fixture[name] for name in GRAPH_NODE_COLLECTIONS]
    all_nodes = list(chain.from_iterable(collections))

    scholarships = [node for node in all_nodes if node["entity_kind"] == "scholarship"]

    assert len(scholarships) == 1
    assert scholarships[0]["id"] == "scholarship:csc"
    assert {"CSC", "CGS", "Chinese Government Scholarship"} <= set(scholarships[0]["aliases"])


def test_csc_routes_institutions_and_programmes_are_links_not_scholarships() -> None:
    fixture = load_csc_fixture()
    csc_id = fixture["scholarships"][0]["id"]

    assert fixture["application_tracks"]
    assert fixture["participating_institutions"]
    assert fixture["eligible_programmes"]
    assert all(node["scholarship_id"] == csc_id for node in fixture["application_tracks"])
    assert all(
        node["relationship_kind"] == "same_scheme_track" for node in fixture["application_tracks"]
    )
    assert all(
        node["scholarship_id"] == csc_id
        and node["relationship_kind"] == "participating_institution"
        and node["entity_kind"] == "institution"
        for node in fixture["participating_institutions"]
    )
    assert all(
        node["scholarship_id"] == csc_id
        and node["relationship_kind"] == "eligible_programme"
        and node["entity_kind"] == "eligible_programme"
        for node in fixture["eligible_programmes"]
    )


def test_csc_local_deadline_and_requirement_retain_tsinghua_scope() -> None:
    fixture = load_csc_fixture()
    local_facts = fixture["scoped_deadlines"] + fixture["scoped_requirements"]

    assert local_facts
    assert all(fact["scope_kind"] == "institution_track" for fact in local_facts)
    assert all(fact["institution_id"] == "institution:tsinghua-university" for fact in local_facts)
    assert all(fact["track_id"] == "track:csc-type-b" for fact in local_facts)
    assert not any(fact["scope_kind"] == "scholarship" for fact in local_facts)


def test_reviewed_csc_fixture_uses_only_https_official_sources() -> None:
    fixture = load_csc_fixture()
    source_ids = {source["id"] for source in fixture["sources"]}

    assert source_ids
    assert all(source["url"].startswith("https://") for source in fixture["sources"])
    assert all(source["owner_kind"] == "institution" for source in fixture["sources"])
    for collection_name in GRAPH_NODE_COLLECTIONS[:-1]:
        for node in fixture[collection_name]:
            assert set(node["source_ids"]) <= source_ids


def test_disabled_graph_flags_preserve_current_public_catalogue_api(client) -> None:
    response = client.get("/api/v1/opportunities")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_azure_templates_keep_all_graph_and_external_capabilities_off() -> None:
    application = Path("infra/azure/application.bicep").read_text(encoding="utf-8")
    jobs = Path("infra/azure/scheduled-jobs.bicep").read_text(encoding="utf-8")
    expected_false_environment = {
        "APP_CATALOGUE_GRAPH_READS_ENABLED",
        "APP_CATALOGUE_GRAPH_WRITES_ENABLED",
        "APP_CATALOGUE_WEB_DISCOVERY_ENABLED",
        "APP_CATALOGUE_BROWSER_FETCH_ENABLED",
        "APP_CATALOGUE_DOCUMENT_INTELLIGENCE_ENABLED",
        "APP_CATALOGUE_SCHEDULED_INGESTION_ENABLED",
        "APP_CATALOGUE_AUTO_PUBLISH_ENABLED",
    }

    for variable in expected_false_environment:
        assert variable in jobs
        jobs_tail = jobs.split(f"name: '{variable}'", maxsplit=1)[1]
        assert "value: 'false'" in jobs_tail.split("}", maxsplit=1)[0]

    for variable in {
        "APP_CATALOGUE_GRAPH_READS_ENABLED",
        "APP_CATALOGUE_GRAPH_WRITES_ENABLED",
        "APP_CATALOGUE_AUTO_PUBLISH_ENABLED",
    }:
        assert variable in application
        application_tail = application.split(f"name: '{variable}'", maxsplit=1)[1]
        assert "value: 'false'" in application_tail.split("}", maxsplit=1)[0]
