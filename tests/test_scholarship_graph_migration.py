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
    assert {
        "canonical_slug",
        "entity_kind",
        "canonical_provider_id",
        "parent_scholarship_id",
        "independence_status",
        "publication_completeness",
        "current_cycle_id",
        "last_verified_at",
        "next_review_at",
    }.issubset({column["name"] for column in inspector.get_columns("opportunities")})
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
        assert (
            session.scalar(
                text("SELECT count(*) FROM opportunities WHERE id = :id"),
                {"id": opportunity_id},
            )
            == 1
        )
    engine.dispose()


def test_scholarship_graph_evidence_migration_reuses_legacy_tables_and_is_reversible(
    tmp_path: Path,
) -> None:
    database_url = (
        f"sqlite+pysqlite:///{(tmp_path / 'scholarship-graph-evidence.db').as_posix()}"
    )
    config = alembic_config_for(database_url)
    command.upgrade(config, "20260817_0038")

    engine = create_engine(database_url)
    provider_id = uuid.uuid4().hex
    opportunity_id = uuid.uuid4().hex
    source_id = uuid.uuid4().hex
    rule_id = uuid.uuid4().hex

    with Session(engine) as session:
        session.execute(
            text("INSERT INTO providers (id, name) VALUES (:id, :name)"),
            {"id": provider_id, "name": "PR2 legacy source provider"},
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
                "name": "PR2 Legacy Scholarship",
                "country": "China",
                "degree_level": "masters",
                "funding_type": "unknown",
                "required_documents": "[]",
                "status": "draft",
                "data_confidence": "low",
                "eligibility_warnings": "[]",
            },
        )
        session.execute(
            text(
                "INSERT INTO sources "
                "(id, opportunity_id, url, source_type, title, relevant_excerpt, "
                "verification_status) "
                "VALUES (:id, :opportunity_id, :url, :source_type, :title, "
                ":relevant_excerpt, :verification_status)"
            ),
            {
                "id": source_id,
                "opportunity_id": opportunity_id,
                "url": "https://example.edu/legacy-scholarship",
                "source_type": "official",
                "title": "Legacy official source",
                "relevant_excerpt": "Legacy official scholarship evidence.",
                "verification_status": "officially_verified",
            },
        )
        session.execute(
            text(
                "INSERT INTO eligibility_rules "
                "(id, opportunity_id, rule_type, operator, value_json, required, confidence) "
                "VALUES (:id, :opportunity_id, :rule_type, :operator, :value_json, "
                ":required, :confidence)"
            ),
            {
                "id": rule_id,
                "opportunity_id": opportunity_id,
                "rule_type": "nationality",
                "operator": "in",
                "value_json": '["PK"]',
                "required": 1,
                "confidence": "high",
            },
        )
        session.commit()

    command.upgrade(config, "20260817_0039")
    inspector = inspect(engine)
    pr2_tables = {
        "source_snapshots",
        "field_evidence",
        "scoped_deadlines",
        "funding_components",
        "required_documents",
        "application_steps",
    }
    assert pr2_tables.issubset(inspector.get_table_names())
    assert "official_sources" not in inspector.get_table_names()

    source_columns = {column["name"] for column in inspector.get_columns("sources")}
    assert {
        "normalized_url",
        "domain",
        "source_owner_type",
        "source_owner_id",
        "officiality_status",
        "officiality_reason",
        "robots_status",
        "content_type",
        "is_active",
    }.issubset(source_columns)

    eligibility_columns = {
        column["name"] for column in inspector.get_columns("eligibility_rules")
    }
    assert {"cycle_id", "track_id", "institution_id", "programme_id"}.issubset(
        eligibility_columns
    )
    assert "scholarship_id" not in eligibility_columns

    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM sources WHERE id = :id"),
                {"id": source_id},
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM eligibility_rules WHERE id = :id"),
                {"id": rule_id},
            )
            == 1
        )

    command.downgrade(config, "20260817_0038")
    inspector = inspect(engine)
    assert not pr2_tables.intersection(inspector.get_table_names())
    assert "normalized_url" not in {
        column["name"] for column in inspector.get_columns("sources")
    }
    assert "cycle_id" not in {
        column["name"] for column in inspector.get_columns("eligibility_rules")
    }
    with Session(engine) as session:
        assert (
            session.scalar(
                text("SELECT count(*) FROM sources WHERE id = :id"),
                {"id": source_id},
            )
            == 1
        )
        assert (
            session.scalar(
                text("SELECT count(*) FROM eligibility_rules WHERE id = :id"),
                {"id": rule_id},
            )
            == 1
        )
    engine.dispose()
