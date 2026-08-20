import uuid
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command
from app.db.base import Base


def _config(database_url: str) -> Config:
    repository_root = Path(__file__).parents[1]
    config = Config(repository_root / "alembic.ini")
    config.set_main_option("script_location", str(repository_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_discovery_foundation_migration_is_additive_and_reversible(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'discovery.db').as_posix()}"
    config = _config(database_url)
    command.upgrade(config, "20260817_0040")
    engine = create_engine(database_url)
    run_id = uuid.uuid4().hex
    candidate_id = uuid.uuid4().hex
    source_id = uuid.uuid4().hex
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO catalogue_ingestion_runs "
                "(id, source_label, source_fingerprint, mode, status, dry_run, "
                "max_candidates, max_pages_per_candidate, max_model_calls, "
                "max_input_characters, max_output_tokens, max_estimated_cost, "
                "aggregate_summary) VALUES "
                "(:id, 'legacy.json', :fingerprint, 'candidate_only', 'pending', 1, "
                "1, 1, 0, 1000, 256, 0, '{}')"
            ),
            {"id": run_id, "fingerprint": uuid.uuid4().hex.ljust(64, "0")},
        )
        session.execute(
            text(
                "INSERT INTO catalogue_candidates "
                "(id, run_id, seed_index, idempotency_key, seed_name, seed_keywords, status, "
                "validation_errors, conflicts, duplicate_opportunity_ids) VALUES "
                "(:id, :run_id, 0, :key, 'Legacy Scholarship', '[]', 'discovered', "
                "'[]', '[]', '[]')"
            ),
            {"id": candidate_id, "run_id": run_id, "key": uuid.uuid4().hex.ljust(64, "0")},
        )
        session.execute(
            text(
                "INSERT INTO catalogue_candidate_sources "
                "(id, candidate_id, url, canonical_url, status, is_official, "
                "classification_reason) VALUES "
                "(:id, :candidate_id, 'https://example.edu', 'https://example.edu', "
                "'discovered', 0, 'legacy source')"
            ),
            {"id": source_id, "candidate_id": candidate_id},
        )
        session.commit()

    command.upgrade(config, "20260820_0041")
    inspector = inspect(engine)
    expected_tables = {
        "catalogue_discovery_runs",
        "catalogue_discovery_queries",
        "catalogue_discovery_attempts",
        "catalogue_discovery_leads",
        "catalogue_discovery_observations",
        "catalogue_discovery_assessments",
        "catalogue_discovery_promotions",
    }
    assert expected_tables.issubset(inspector.get_table_names())
    for table_name in expected_tables:
        migrated_columns = {column["name"] for column in inspector.get_columns(table_name)}
        assert migrated_columns == set(Base.metadata.tables[table_name].columns.keys())
    for table_name in expected_tables | {"catalogue_candidate_sources"}:
        named_schema_objects = (
            inspector.get_indexes(table_name)
            + inspector.get_unique_constraints(table_name)
            + inspector.get_foreign_keys(table_name)
            + inspector.get_check_constraints(table_name)
        )
        assert all(
            len(schema_object["name"]) <= 63
            for schema_object in named_schema_objects
            if schema_object.get("name")
        )
    source_columns = {
        column["name"] for column in inspector.get_columns("catalogue_candidate_sources")
    }
    assert "discovery_lead_id" in source_columns
    source_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("catalogue_candidate_sources")
    }
    assert "uq_catalogue_candidate_source_discovery_lead" in source_uniques
    source_foreign_keys = {
        constraint["name"]
        for constraint in inspector.get_foreign_keys("catalogue_candidate_sources")
    }
    assert "fk_candidate_sources_discovery_lead" in source_foreign_keys
    attempt_columns = {
        column["name"] for column in inspector.get_columns("catalogue_discovery_attempts")
    }
    assert {
        "request_fingerprint",
        "reserved_tool_calls",
        "reserved_estimated_cost",
        "web_search_executed",
        "estimated_total_cost",
    }.issubset(attempt_columns)
    expected_checks = {
        "catalogue_discovery_runs": {
            "raw_leads_seen_nonnegative",
            "unique_leads_nonnegative",
            "promotions_nonnegative",
        },
        "catalogue_discovery_queries": {"latency_nonnegative"},
        "catalogue_discovery_attempts": {
            "http_status_valid",
            "input_tokens_nonnegative",
            "output_tokens_nonnegative",
            "attempt_latency_nonnegative",
        },
        "catalogue_discovery_assessments": {"trust_tier_valid"},
    }
    for table_name, constraint_names in expected_checks.items():
        migrated_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        }
        assert constraint_names.issubset(migrated_checks)
    attempt_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
        for foreign_key in inspector.get_foreign_keys("catalogue_discovery_attempts")
    }
    assert attempt_foreign_keys[("query_id",)] == "RESTRICT"
    observation_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key["options"].get("ondelete")
        for foreign_key in inspector.get_foreign_keys("catalogue_discovery_observations")
    }
    assert observation_foreign_keys == {
        ("lead_id",): "RESTRICT",
        ("query_id",): "RESTRICT",
    }
    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM catalogue_candidate_sources WHERE id = :id"),
                {"id": source_id},
            )
            == 1
        )

    command.downgrade(config, "20260817_0040")
    inspector = inspect(engine)
    assert not expected_tables.intersection(inspector.get_table_names())
    assert "discovery_lead_id" not in {
        column["name"] for column in inspector.get_columns("catalogue_candidate_sources")
    }
    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM catalogue_candidate_sources WHERE id = :id"),
                {"id": source_id},
            )
            == 1
        )
    engine.dispose()
