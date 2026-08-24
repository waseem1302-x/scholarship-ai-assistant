import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.core.security import hash_password
from app.modules.applications.models import (
    Application,
    ApplicationStatus,
    SavedOpportunity,
    TaskStatus,
)
from app.modules.auth.models import UserRole
from app.modules.auth.service import AuthService
from app.modules.opportunities.models import (
    DataConfidence,
    DegreeLevel,
    FundingType,
    OpportunityStatus,
    SourceType,
    VerificationStatus,
)


def test_alembic_schema_accepts_orm_enums_and_portable_timestamp_defaults(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-integration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    profile_columns = {column["name"] for column in inspector.get_columns("student_profiles")}
    assert "target_intake_year" in profile_columns
    assert {
        "nationality_code",
        "country_of_residence_code",
        "intended_field_taxonomy",
        "intended_field_detail",
        "preferred_destination_country_codes",
        "version",
    } <= profile_columns
    profile_indexes = {index["name"] for index in inspector.get_indexes("student_profiles")}
    assert {
        "ix_student_profiles_nationality_code",
        "ix_student_profiles_country_of_residence_code",
        "ix_student_profiles_intended_field_taxonomy",
    } <= profile_indexes
    reminder_constraints = {
        constraint["name"]: set(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("application_reminders")
    }
    assert reminder_constraints["uq_application_reminders_application_idempotency"] == {
        "application_id",
        "idempotency_key",
    }
    assert "source_excerpt_id" in {
        column["name"] for column in inspector.get_columns("eligibility_rules")
    }
    assert "application_fee_status" in {
        column["name"] for column in inspector.get_columns("opportunities")
    }
    assert {
        "deletion_status",
        "deletion_requested_at",
    } <= {column["name"] for column in inspector.get_columns("document_assets")}
    assert "encryption_key_version" in {
        column["name"] for column in inspector.get_columns("document_versions")
    }
    assert {
        "rubric_category",
        "confidence",
    } <= {column["name"] for column in inspector.get_columns("document_feedback_items")}
    assert {
        "public_id",
        "display_name_normalized",
    } <= {column["name"] for column in inspector.get_columns("community_preferences")}
    assert "operational_job_runs" in inspector.get_table_names()
    assert {
        "previous_integrity_hash",
        "integrity_hash",
    } <= {column["name"] for column in inspector.get_columns("audit_logs")}
    assert "eligibility_rule_values" in inspector.get_table_names()
    settings = Settings(
        env="test",
        database_url=database_url,
        jwt_secret="migration-test-secret-at-least-32-characters",
    )
    with Session(engine) as session:
        result = AuthService(session, settings).register(
            "migrated@example.com", "MigrationPassword123"
        )
        assert result.user.role is UserRole.STUDENT

        session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, is_active) "
                "VALUES (:id, :email, :password_hash, :role, :is_active)"
            ),
            {
                "id": uuid.uuid4().hex,
                "email": "database-default@example.com",
                "password_hash": "unused",
                "role": "student",
                "is_active": True,
            },
        )
        session.commit()
        created_at = session.scalar(
            text("SELECT created_at FROM users WHERE email = 'database-default@example.com'")
        )
        assert created_at is not None
    engine.dispose()


def test_application_command_centre_migration_preserves_legacy_tracker_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-tracker.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "20260812_0009")

    engine = create_engine(database_url)
    deadline = datetime(2027, 5, 30, 23, 59, tzinfo=UTC)
    with Session(engine) as session:
        # This is intentionally a pre-token-version schema. Insert its user
        # through the historic table shape rather than the current ORM mapper.
        user_id = uuid.uuid4()
        session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, is_active) "
                "VALUES (:id, :email, :password_hash, :role, :is_active)"
            ),
            {
                "id": user_id.hex,
                "email": "legacy-tracker@example.com",
                "password_hash": hash_password("LegacyTrackerPassword123"),
                "role": UserRole.STUDENT.value,
                "is_active": True,
            },
        )
        provider_id = uuid.uuid4()
        session.execute(
            text("INSERT INTO providers (id, name) VALUES (:id, :name)"),
            {"id": provider_id.hex, "name": "Legacy Provider"},
        )
        opportunity_id = uuid.uuid4()
        source_id = uuid.uuid4()
        # The database is intentionally pinned to the historic 0009 schema.
        # Use that table shape instead of the current ORM mapper.
        session.execute(
            text(
                "INSERT INTO opportunities "
                "(id, provider_id, name, country, degree_level, application_deadline, "
                "funding_type, tuition_coverage, required_documents, status, data_confidence, "
                "eligibility_warnings) "
                "VALUES (:id, :provider_id, :name, :country, :degree_level, :deadline, "
                ":funding_type, :tuition_coverage, :required_documents, :status, "
                ":data_confidence, :eligibility_warnings)"
            ),
            {
                "id": opportunity_id.hex,
                "provider_id": provider_id.hex,
                "name": "Legacy Scholarship",
                "country": "Malaysia",
                "degree_level": DegreeLevel.MASTERS.value,
                "deadline": deadline,
                "funding_type": FundingType.FULL.value,
                "tuition_coverage": "Officially stated tuition coverage.",
                "required_documents": "[]",
                "status": OpportunityStatus.ACTIVE.value,
                "data_confidence": DataConfidence.HIGH.value,
                "eligibility_warnings": "[]",
            },
        )
        session.execute(
            text(
                "INSERT INTO sources "
                "(id, opportunity_id, url, source_type, title, relevant_excerpt, "
                "verification_status) "
                "VALUES (:id, :opportunity_id, :url, :source_type, :title, :excerpt, "
                ":verification_status)"
            ),
            {
                "id": source_id.hex,
                "opportunity_id": opportunity_id.hex,
                "url": "https://example.edu/legacy-scholarship",
                "source_type": SourceType.OFFICIAL.value,
                "title": "Legacy scholarship official source",
                "excerpt": "Official deadline and document requirements for legacy testing.",
                "verification_status": VerificationStatus.OFFICIALLY_VERIFIED.value,
            },
        )
        saved = SavedOpportunity(
            user_id=user_id,
            opportunity_id=opportunity_id,
            status=ApplicationStatus.SUBMITTED,
            personal_notes="Confirm portal receipt.",
            personal_deadline=deadline,
            submitted_at=deadline,
            outcome_notes="Awaiting decision.",
            document_checklist=[
                {
                    "name": "Transcript",
                    "is_complete": True,
                    "notes": "Uploaded",
                }
            ],
            recommendation_letters=[{"name": "Referee letter", "is_complete": False}],
            test_requirements=[{"name": "IELTS", "is_complete": True}],
        )
        session.add(saved)
        session.commit()
        saved_id = saved.id

    command.upgrade(alembic_config, "head")
    with Session(engine) as session:
        application = session.scalar(select(Application))
        assert application is not None
        assert application.saved_opportunity_id == saved_id
        assert application.lifecycle.value == "submitted"
        assert application.notes == "Confirm portal receipt."
        assert application.personal_deadline is not None
        assert application.personal_deadline.replace(tzinfo=UTC) == deadline
        assert application.submitted_at is not None
        assert application.submitted_at.replace(tzinfo=UTC) == deadline
        assert application.decision_notes == "Awaiting decision."
        tasks = {task.title: task for task in application.tasks}
        assert tasks["Transcript"].status is TaskStatus.COMPLETED
        assert tasks["Transcript"].notes == "Uploaded"
        assert tasks["Referee letter"].status is TaskStatus.TODO

    command.downgrade(alembic_config, "20260812_0009")
    assert "applications" not in inspect(engine).get_table_names()
    with Session(engine) as session:
        restored_saved = session.get(SavedOpportunity, saved_id)
        assert restored_saved is not None
        assert restored_saved.personal_notes == "Confirm portal receipt."
        assert restored_saved.document_checklist[0]["name"] == "Transcript"
    engine.dispose()


def test_assistant_safety_migration_upgrades_and_downgrades(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "assistant-safety.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "20260812_0011")
    command.upgrade(alembic_config, "20260812_0012")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "assistant_privacy_preferences" in inspector.get_table_names()
    assert "claim_key" in {
        column["name"] for column in inspector.get_columns("assistant_citations")
    }
    assert "failure_code" in {
        column["name"] for column in inspector.get_columns("assistant_answers")
    }
    command.downgrade(alembic_config, "20260812_0011")
    inspector = inspect(engine)
    assert "assistant_privacy_preferences" not in inspector.get_table_names()
    assert "claim_key" not in {
        column["name"] for column in inspector.get_columns("assistant_citations")
    }
    engine.dispose()


def test_document_lab_foundation_migration_upgrades_and_downgrades(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "document-lab.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "20260812_0013")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "document_assets",
        "document_versions",
        "document_extractions",
        "document_consents",
        "document_analyses",
        "document_feedback_items",
        "document_analysis_jobs",
        "application_document_links",
    }.issubset(inspector.get_table_names())
    command.downgrade(alembic_config, "20260812_0012")
    inspector = inspect(engine)
    assert "document_assets" not in inspector.get_table_names()
    assert "application_document_links" not in inspector.get_table_names()
    engine.dispose()


def test_community_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    database_path = tmp_path / "community.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "20260813_0014")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "community_preferences",
        "community_posts",
        "community_replies",
        "community_bookmarks",
        "community_blocks",
        "community_reports",
        "community_moderation_records",
    }.issubset(inspector.get_table_names())
    command.downgrade(alembic_config, "20260812_0013")
    inspector = inspect(engine)
    assert "community_posts" not in inspector.get_table_names()
    assert "community_reports" not in inspector.get_table_names()
    engine.dispose()


def test_phase_nine_schema_upgrades_and_rolls_back_to_community(tmp_path: Path) -> None:
    database_path = tmp_path / "phase-nine.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260813_0019")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "beta_invitations",
        "beta_legal_acceptances",
        "webauthn_credentials",
        "webauthn_challenges",
        "operational_job_health",
    }.issubset(inspector.get_table_names())
    invitation_columns = {column["name"] for column in inspector.get_columns("beta_invitations")}
    assert {"reserved_by_user_id", "reserved_at"}.issubset(invitation_columns)

    command.downgrade(alembic_config, "20260813_0014")
    inspector = inspect(engine)
    assert not {
        "beta_invitations",
        "beta_legal_acceptances",
        "webauthn_credentials",
        "webauthn_challenges",
        "operational_job_health",
    }.intersection(inspector.get_table_names())
    engine.dispose()


def test_token_version_migration_upgrades_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'token-version.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260813_0020")
    engine = create_engine(database_url)
    assert "token_version" in {column["name"] for column in inspect(engine).get_columns("users")}

    command.downgrade(alembic_config, "20260813_0019")
    assert "token_version" not in {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    engine.dispose()


def test_admin_step_up_scope_migration_upgrades_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'admin-step-up-scope.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260813_0021")
    engine = create_engine(database_url)
    assert "scope" in {
        column["name"] for column in inspect(engine).get_columns("admin_step_up_tokens")
    }

    command.downgrade(alembic_config, "20260813_0020")
    assert "scope" not in {
        column["name"] for column in inspect(engine).get_columns("admin_step_up_tokens")
    }
    engine.dispose()


def test_passkey_lifecycle_migration_upgrades_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'passkey-lifecycle.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260813_0022")
    engine = create_engine(database_url)
    credential_columns = {
        column["name"] for column in inspect(engine).get_columns("webauthn_credentials")
    }
    assert {"display_name", "revoked_at"}.issubset(credential_columns)

    command.downgrade(alembic_config, "20260813_0021")
    credential_columns = {
        column["name"] for column in inspect(engine).get_columns("webauthn_credentials")
    }
    assert not {"display_name", "revoked_at"}.intersection(credential_columns)
    engine.dispose()


def test_catalogue_ingestion_migration_is_additive_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'catalogue-ingestion.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260815_0037")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "catalogue_ingestion_runs",
        "catalogue_candidates",
        "catalogue_candidate_sources",
        "catalogue_extraction_attempts",
    }.issubset(inspector.get_table_names())
    assert {
        "monitor_next_check_at",
        "monitor_claimed_until",
        "monitor_failure_count",
    }.issubset({column["name"] for column in inspector.get_columns("sources")})
    assert "ix_catalogue_candidates_claim" in {
        index["name"] for index in inspector.get_indexes("catalogue_candidates")
    }

    command.downgrade(alembic_config, "20260814_0036")
    inspector = inspect(engine)
    assert "catalogue_ingestion_runs" not in inspector.get_table_names()
    assert not {
        "monitor_next_check_at",
        "monitor_claimed_until",
        "monitor_failure_count",
    }.intersection({column["name"] for column in inspector.get_columns("sources")})
    engine.dispose()


def test_catalogue_run_queue_migration_backfills_prior_runs_and_rolls_back(
    tmp_path: Path,
) -> None:
    """Exercise the queue migration against its immediate production-like predecessor."""

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'catalogue-run-queue.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260823_0044")
    engine = create_engine(database_url)
    run_id = uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO catalogue_ingestion_runs "
                "(id, source_label, source_fingerprint, mode, status, dry_run, "
                "max_candidates, max_pages_per_candidate, max_model_calls, "
                "max_input_characters, max_output_tokens, max_estimated_cost, "
                "model_calls, input_tokens, output_tokens, estimated_cost, aggregate_summary) "
                "VALUES (:id, :label, :fingerprint, 'candidate_only', 'pending', 1, "
                "1, 1, 0, 1000, 256, 0, 0, 0, 0, 0, '{}')"
            ),
            {"id": run_id, "label": "prior-queue-run", "fingerprint": "a" * 64},
        )

    command.upgrade(alembic_config, "20260824_0045")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("catalogue_ingestion_runs")}
    assert {
        "idempotency_key",
        "stage",
        "max_attempts",
        "attempt_count",
        "next_attempt_at",
        "claimed_until",
        "lease_token",
        "dead_lettered_at",
    }.issubset(columns)
    assert "ix_catalogue_ingestion_runs_claim" in {
        index["name"] for index in inspector.get_indexes("catalogue_ingestion_runs")
    }
    with engine.connect() as connection:
        migrated = connection.execute(
            text(
                "SELECT idempotency_key, stage, max_attempts, attempt_count "
                "FROM catalogue_ingestion_runs WHERE id = :id"
            ),
            {"id": run_id},
        ).one()
    assert migrated == (f"legacy:{run_id}", "queued", 3, 0)

    command.downgrade(alembic_config, "20260823_0044")
    restored_columns = {
        column["name"] for column in inspect(engine).get_columns("catalogue_ingestion_runs")
    }
    assert not {
        "idempotency_key",
        "stage",
        "max_attempts",
        "attempt_count",
        "next_attempt_at",
        "claimed_until",
        "lease_token",
        "dead_lettered_at",
    }.intersection(restored_columns)
    engine.dispose()


def test_catalogue_evidence_block_migration_is_additive_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'catalogue-evidence-blocks.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260824_0045")
    engine = create_engine(database_url)
    assert "catalogue_evidence_blocks" not in inspect(engine).get_table_names()

    command.upgrade(alembic_config, "20260824_0046")
    inspector = inspect(engine)
    assert {
        "id",
        "artifact_id",
        "block_id",
        "canonicalization_version",
        "block_index",
        "start_offset",
        "end_offset",
        "text",
        "locator",
    }.issubset({column["name"] for column in inspector.get_columns("catalogue_evidence_blocks")})
    assert "ix_catalogue_evidence_blocks_artifact_offsets" in {
        index["name"] for index in inspector.get_indexes("catalogue_evidence_blocks")
    }

    command.downgrade(alembic_config, "20260824_0045")
    assert "catalogue_evidence_blocks" not in inspect(engine).get_table_names()
    engine.dispose()


def test_catalogue_source_routing_migration_is_additive_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'catalogue-source-routing.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260824_0046")
    engine = create_engine(database_url)
    assert "catalogue_source_routing_decisions" not in inspect(engine).get_table_names()

    command.upgrade(alembic_config, "20260824_0047")
    inspector = inspect(engine)
    assert {
        "artifact_id",
        "classifier_version",
        "role",
        "cycle",
        "deterministic_signals",
        "applicable_objectives",
        "requires_manual_review",
    }.issubset(
        {column["name"] for column in inspector.get_columns("catalogue_source_routing_decisions")}
    )
    assert "ix_catalogue_source_routing_role_cycle" in {
        index["name"] for index in inspector.get_indexes("catalogue_source_routing_decisions")
    }

    command.downgrade(alembic_config, "20260824_0046")
    assert "catalogue_source_routing_decisions" not in inspect(engine).get_table_names()
    engine.dispose()


def test_assistant_quota_reservation_migration_is_additive_and_rolls_back(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'assistant-quota.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260824_0047")
    engine = create_engine(database_url)
    assert "assistant_quota_counters" not in inspect(engine).get_table_names()

    command.upgrade(alembic_config, "20260824_0048")
    inspector = inspect(engine)
    assert {
        "user_id",
        "window",
        "window_start",
        "used_slots",
    }.issubset({column["name"] for column in inspector.get_columns("assistant_quota_counters")})
    assert {
        "user_id",
        "daily_window_start",
        "monthly_window_start",
        "status",
        "answer_id",
        "terminal_reason",
    }.issubset({column["name"] for column in inspector.get_columns("assistant_quota_reservations")})

    command.downgrade(alembic_config, "20260824_0047")
    inspector = inspect(engine)
    assert not {
        "assistant_quota_counters",
        "assistant_quota_reservations",
    }.intersection(inspector.get_table_names())
    engine.dispose()


def test_source_monitor_fencing_migration_is_additive_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'source-monitor-fencing.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260824_0048")
    engine = create_engine(database_url)
    assert "monitor_claim_token" not in {
        column["name"] for column in inspect(engine).get_columns("sources")
    }

    command.upgrade(alembic_config, "20260824_0049")
    inspector = inspect(engine)
    assert "monitor_claim_token" in {column["name"] for column in inspector.get_columns("sources")}
    assert "ix_sources_monitor_claim_token" in {
        index["name"] for index in inspector.get_indexes("sources")
    }

    command.downgrade(alembic_config, "20260824_0048")
    assert "monitor_claim_token" not in {
        column["name"] for column in inspect(engine).get_columns("sources")
    }
    engine.dispose()


def test_document_job_lease_migration_is_additive_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'document-job-lease.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260824_0049")
    engine = create_engine(database_url)
    assert "claim_token" not in {
        column["name"] for column in inspect(engine).get_columns("document_analysis_jobs")
    }
    command.upgrade(alembic_config, "20260824_0050")
    assert {"claim_token", "claimed_until"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("document_analysis_jobs")}
    )
    command.downgrade(alembic_config, "20260824_0049")
    assert "claim_token" not in {
        column["name"] for column in inspect(engine).get_columns("document_analysis_jobs")
    }
    engine.dispose()


def test_document_deletion_job_migration_is_additive_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'document-deletion-job.db').as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(alembic_config, "20260824_0050")
    engine = create_engine(database_url)
    assert "document_deletion_jobs" not in inspect(engine).get_table_names()
    command.upgrade(alembic_config, "20260824_0051")
    assert {"asset_id", "storage_keys", "next_attempt_at"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("document_deletion_jobs")}
    )
    command.downgrade(alembic_config, "20260824_0050")
    assert "document_deletion_jobs" not in inspect(engine).get_table_names()
    engine.dispose()
