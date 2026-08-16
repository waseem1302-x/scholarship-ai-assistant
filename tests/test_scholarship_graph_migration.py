import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session


def alembic_config_for(database_url: str) -> Config:
    repository_root = Path(__file__).parents[1]
    config = Config(repository_root / "alembic.ini")
    config.set_main_option("script_location", str(repository_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_scholarship_graph_migration_is_expand_first_and_reversible(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'scholarship-graph.db').as_posix()}"
    config = alembic_config_for(database_url)
    command.upgrade(config, "20260815_0037")

    engine = create_engine(database_url)
    provider_id = uuid.uuid4().hex
    opportunity_id = uuid.uuid4().hex
    with Session(engine) as session:
        session.execute(
            text("INSERT INTO providers (id, name) VALUES (:id, :name)"),
            {"id": provider_id, "name": "Legacy graph migration provider"},
        )
        session.execute(
            text(
                "INSERT INTO opportunities "
                "(id, provider_id, name, country, degree_level, funding_type, "
                "required_documents, status, data_confidence, eligibility_warnings) "
                "VALUES (:id, :provider_id, :name, :country, :degree_level, :funding_type, "
                ":required_documents, :status, :data_confidence, :eligibility_warnings)"
            ),
            {
                "id": opportunity_id,
                "provider_id": provider_id,
                "name": "Legacy Scholarship",
                "country": "Malaysia",
                "degree_level": "masters",
                "funding_type": "unknown",
                "required_documents": "[]",
                "status": "draft",
                "data_confidence": "low",
                "eligibility_warnings": "[]",
            },
        )
        session.commit()

    command.upgrade(config, "20260817_0038")
    inspector = inspect(engine)
    assert {
        "application_tracks",
        "institutions",
        "institution_aliases",
        "institution_participations",
        "academic_programmes",
        "track_programmes",
        "scholarship_aliases",
        "scholarship_relationships",
    }.issubset(inspector.get_table_names())

    opportunity_columns = {column["name"] for column in inspector.get_columns("opportunities")}
    assert {
        "canonical_slug",
        "entity_kind",
        "parent_scholarship_id",
        "independence_status",
        "publication_completeness",
        "last_verified_at",
        "next_review_at",
    }.issubset(opportunity_columns)
    # The existing provider_id remains the canonical provider relationship; do not
    # introduce a parallel canonical_provider_id identity path.
    assert "provider_id" in opportunity_columns
    assert "canonical_provider_id" not in opportunity_columns
    # Current-cycle selection stays on opportunity_cycles.is_current instead of
    # adding a second, potentially inconsistent current_cycle_id pointer.
    assert "current_cycle_id" not in opportunity_columns

    assert {
        "label",
        "status",
        "is_current",
        "source_id",
        "updated_at",
        "version",
    }.issubset({column["name"] for column in inspector.get_columns("opportunity_cycles")})
    assert "uq_opportunity_canonical_slug" in {
        index["name"] for index in inspector.get_indexes("opportunities")
    }
    assert "uq_opportunity_cycles_one_current" in {
        index["name"] for index in inspector.get_indexes("opportunity_cycles")
    }

    with Session(engine) as session:
        row = session.execute(
            text(
                "SELECT name, entity_kind, independence_status, publication_completeness "
                "FROM opportunities WHERE id = :id"
            ),
            {"id": opportunity_id},
        ).one()
        assert row.name == "Legacy Scholarship"
        assert row.entity_kind == "scholarship"
        assert row.independence_status == "legacy_unreviewed"
        assert row.publication_completeness == "incomplete"

    command.downgrade(config, "20260815_0037")
    inspector = inspect(engine)
    assert not {
        "application_tracks",
        "institutions",
        "institution_aliases",
        "institution_participations",
        "academic_programmes",
        "track_programmes",
        "scholarship_aliases",
        "scholarship_relationships",
    }.intersection(inspector.get_table_names())
    assert "canonical_slug" not in {
        column["name"] for column in inspector.get_columns("opportunities")
    }
    with Session(engine) as session:
        assert session.scalar(
            text("SELECT count(*) FROM opportunities WHERE id = :id"),
            {"id": opportunity_id},
        ) == 1
    engine.dispose()
