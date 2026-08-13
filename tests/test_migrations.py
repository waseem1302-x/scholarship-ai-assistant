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
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
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
    assert "source_excerpt_id" in {
        column["name"] for column in inspector.get_columns("eligibility_rules")
    }
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
        provider = Provider(name="Legacy Provider")
        opportunity = Opportunity(
            provider=provider,
            name="Legacy Scholarship",
            country="Malaysia",
            degree_level=DegreeLevel.MASTERS,
            application_deadline=deadline,
            funding_type=FundingType.FULL,
            tuition_coverage="Officially stated tuition coverage.",
            status=OpportunityStatus.ACTIVE,
            data_confidence=DataConfidence.HIGH,
        )
        opportunity.sources.append(
            Source(
                url="https://example.edu/legacy-scholarship",
                source_type=SourceType.OFFICIAL,
                title="Legacy scholarship official source",
                relevant_excerpt="Official deadline and document requirements for legacy testing.",
                verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            )
        )
        saved = SavedOpportunity(
            user_id=user_id,
            opportunity=opportunity,
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
