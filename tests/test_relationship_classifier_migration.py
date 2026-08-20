import uuid
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command


def alembic_config_for(database_url: str) -> Config:
    repository_root = Path(__file__).parents[1]
    config = Config(repository_root / "alembic.ini")
    config.set_main_option("script_location", str(repository_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_relationship_classifier_migration_is_expand_first_and_reversible(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'classifier.db').as_posix()}"
    config = alembic_config_for(database_url)
    command.upgrade(config, "20260817_0039")

    engine = create_engine(database_url)
    run_id = uuid.uuid4().hex
    candidate_id = uuid.uuid4().hex
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO catalogue_ingestion_runs "
                "(id, source_label, source_fingerprint, mode, status, dry_run, "
                "max_candidates, max_pages_per_candidate, max_model_calls, "
                "max_input_characters, max_output_tokens, max_estimated_cost, "
                "aggregate_summary) "
                "VALUES (:id, :label, :fingerprint, 'candidate_only', 'pending', 1, "
                "10, 3, 0, 80000, 4000, 0, '{}')"
            ),
            {
                "id": run_id,
                "label": "PR3 legacy candidate run",
                "fingerprint": uuid.uuid4().hex,
            },
        )
        session.execute(
            text(
                "INSERT INTO catalogue_candidates "
                "(id, run_id, seed_index, idempotency_key, seed_name, seed_keywords, status, "
                "validation_errors, conflicts, duplicate_opportunity_ids) "
                "VALUES (:id, :run_id, 0, :key, :name, '[]', 'discovered', '[]', '[]', '[]')"
            ),
            {
                "id": candidate_id,
                "run_id": run_id,
                "key": uuid.uuid4().hex,
                "name": "Legacy candidate before PR3",
            },
        )
        session.commit()

    command.upgrade(config, "20260817_0040")
    inspector = inspect(engine)
    assert "classification_decisions" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("classification_decisions")}
    assert {
        "id",
        "candidate_id",
        "proposed_relationship",
        "parent_scholarship_id",
        "proposed_new_scholarship_id",
        "deterministic_signals",
        "model_output",
        "confidence_band",
        "evidence_snapshot_ids",
        "decision_status",
        "reason_code",
        "reviewer_id",
        "reviewed_at",
        "created_at",
    }.issubset(columns)

    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM catalogue_candidates WHERE id = :id"),
                {"id": candidate_id},
            )
            == 1
        )
        session.execute(
            text(
                "INSERT INTO classification_decisions "
                "(id, candidate_id, proposed_relationship, deterministic_signals, "
                "confidence_band, evidence_snapshot_ids, decision_status, reason_code) "
                "VALUES (:id, :candidate_id, 'unresolved', '[]', 'unresolved', '[]', "
                "'needs_review', 'migration_fixture')"
            ),
            {"id": uuid.uuid4().hex, "candidate_id": candidate_id},
        )
        session.commit()
        assert (
            session.scalar(
                text("SELECT count(*) FROM classification_decisions WHERE candidate_id = :id"),
                {"id": candidate_id},
            )
            == 1
        )

    command.downgrade(config, "20260817_0039")
    inspector = inspect(engine)
    assert "classification_decisions" not in inspector.get_table_names()
    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM catalogue_candidates WHERE id = :id"),
                {"id": candidate_id},
            )
            == 1
        )
    engine.dispose()
