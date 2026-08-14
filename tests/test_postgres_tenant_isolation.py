import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.db.session import bind_tenant_context
from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationNotificationPreference,
    ApplicationReminder,
    ApplicationTask,
    SavedOpportunity,
    TaskCategory,
)
from app.modules.assistant.models import (
    AssistantAnswer,
    AssistantAnswerStatus,
    AssistantConversation,
    AssistantEvidencePacket,
    AssistantMessage,
    AssistantMessageRole,
)
from app.modules.auth.models import User
from app.modules.community.models import CommunityBlock, CommunityPreference
from app.modules.document_lab.models import (
    DocumentAsset,
    DocumentKind,
    DocumentVersion,
)
from app.modules.matching.models import MatchEvaluation
from app.modules.opportunities.models import DegreeLevel, Opportunity, Provider
from app.modules.profiles.models import StudentProfile
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgres

PROTECTED_TABLES = {
    "application_document_links",
    "application_documents",
    "application_events",
    "application_notification_preferences",
    "application_reminders",
    "application_tasks",
    "applications",
    "assistant_answers",
    "assistant_citations",
    "assistant_conversations",
    "assistant_evidence_packets",
    "assistant_feedback",
    "assistant_messages",
    "assistant_privacy_preferences",
    "community_blocks",
    "community_bookmarks",
    "community_preferences",
    "community_reports",
    "document_analyses",
    "document_analysis_jobs",
    "document_assets",
    "document_consents",
    "document_extractions",
    "document_feedback_items",
    "document_versions",
    "match_evaluation_results",
    "match_evaluations",
    "match_rule_outcomes",
    "saved_opportunities",
    "student_profiles",
}


@pytest.fixture(scope="module")
def postgres_admin_engine():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL tenant tests")

    engine = create_engine(database_url, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def postgres_runtime_engine(postgres_admin_engine):
    role = f"tenant_runtime_{uuid.uuid4().hex[:12]}"
    password = uuid.uuid4().hex
    quoted_role = f'"{role}"'

    with postgres_admin_engine.begin() as connection:
        can_create_role = connection.scalar(
            text("SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname = current_user")
        )
        assert can_create_role, "Disposable PostgreSQL must permit a non-bypass runtime role"
        connection.exec_driver_sql(
            f"CREATE ROLE {quoted_role} LOGIN PASSWORD '{password}' "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        database_name = connection.scalar(text("SELECT current_database()"))
        quoted_database = connection.dialect.identifier_preparer.quote(database_name)
        connection.exec_driver_sql(f"GRANT CONNECT ON DATABASE {quoted_database} TO {quoted_role}")
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {quoted_role}")
        connection.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted_role}"
        )
        connection.exec_driver_sql(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted_role}"
        )

    runtime_url = make_url(os.environ["TEST_POSTGRES_URL"]).set(
        username=role,
        password=password,
    )
    runtime_engine = create_engine(
        runtime_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    with runtime_engine.connect() as connection:
        properties = connection.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert tuple(properties) == (False, False)

    yield runtime_engine

    runtime_engine.dispose()
    with postgres_admin_engine.begin() as connection:
        connection.exec_driver_sql(f"DROP OWNED BY {quoted_role}")
        connection.exec_driver_sql(f"DROP ROLE {quoted_role}")


@pytest.fixture(scope="module")
def tenant_records(postgres_admin_engine):
    now = datetime.now(UTC)
    ids = {
        name: uuid.uuid4()
        for name in (
            "user_a",
            "user_b",
            "provider",
            "opportunity",
            "saved",
            "application",
            "task",
            "reminder",
            "event",
            "application_document",
            "conversation",
            "message",
            "evidence",
            "answer",
            "asset",
            "version",
            "profile",
            "evaluation",
            "community_block",
        )
    }

    with Session(postgres_admin_engine) as session:
        session.add_all(
            [
                User(
                    id=ids["user_a"],
                    email=f"tenant-a-{uuid.uuid4().hex}@example.com",
                    password_hash="test-password-hash",
                ),
                User(
                    id=ids["user_b"],
                    email=f"tenant-b-{uuid.uuid4().hex}@example.com",
                    password_hash="test-password-hash",
                ),
                Provider(id=ids["provider"], name=f"Tenant test {uuid.uuid4().hex}"),
                Opportunity(
                    id=ids["opportunity"],
                    provider_id=ids["provider"],
                    name="Tenant isolation opportunity",
                    country="Italy",
                    degree_level=DegreeLevel.MASTERS,
                ),
                SavedOpportunity(
                    id=ids["saved"],
                    user_id=ids["user_a"],
                    opportunity_id=ids["opportunity"],
                    personal_notes="private saved record",
                ),
                Application(
                    id=ids["application"],
                    user_id=ids["user_a"],
                    opportunity_id=ids["opportunity"],
                    saved_opportunity_id=ids["saved"],
                    notes="private application",
                ),
                ApplicationTask(
                    id=ids["task"],
                    application_id=ids["application"],
                    category=TaskCategory.DOCUMENT,
                    title="Private task",
                ),
                ApplicationReminder(
                    id=ids["reminder"],
                    application_id=ids["application"],
                    task_id=ids["task"],
                    scheduled_at=now + timedelta(days=1),
                    idempotency_key=uuid.uuid4().hex,
                    message="private reminder",
                ),
                ApplicationNotificationPreference(user_id=ids["user_a"]),
                ApplicationEvent(
                    id=ids["event"],
                    application_id=ids["application"],
                    actor_user_id=ids["user_a"],
                    event_type="tenant.test",
                ),
                ApplicationDocument(
                    id=ids["application_document"],
                    application_id=ids["application"],
                    task_id=ids["task"],
                    name="Private transcript",
                ),
                AssistantConversation(
                    id=ids["conversation"],
                    user_id=ids["user_a"],
                    title="Private conversation",
                ),
                AssistantMessage(
                    id=ids["message"],
                    conversation_id=ids["conversation"],
                    role=AssistantMessageRole.USER,
                    content="private assistant message",
                ),
                AssistantEvidencePacket(
                    id=ids["evidence"],
                    user_id=ids["user_a"],
                    retrieval_version="tenant-test",
                    rule_version="tenant-test",
                ),
                AssistantAnswer(
                    id=ids["answer"],
                    user_id=ids["user_a"],
                    conversation_id=ids["conversation"],
                    evidence_packet_id=ids["evidence"],
                    status=AssistantAnswerStatus.COMPLETED,
                    provider="test",
                    model_version="test",
                    prompt_template_version="test",
                    retrieval_version="test",
                ),
                DocumentAsset(
                    id=ids["asset"],
                    user_id=ids["user_a"],
                    document_kind=DocumentKind.CV_RESUME,
                    display_name_ciphertext="private-name",
                    retention_expires_at=now + timedelta(days=30),
                ),
                DocumentVersion(
                    id=ids["version"],
                    asset_id=ids["asset"],
                    user_id=ids["user_a"],
                    version_number=1,
                    storage_key=f"tenant-test/{uuid.uuid4().hex}",
                    content_sha256="a" * 64,
                    declared_content_type="application/pdf",
                    detected_content_type="application/pdf",
                    size_bytes=128,
                ),
                StudentProfile(id=ids["profile"], user_id=ids["user_a"]),
                MatchEvaluation(
                    id=ids["evaluation"],
                    user_id=ids["user_a"],
                    profile_id=ids["profile"],
                    matcher_version="tenant-test",
                    evaluated_at=now,
                    expires_at=now + timedelta(days=30),
                    profile_snapshot_json={},
                    profile_snapshot_hash="b" * 64,
                ),
                CommunityPreference(
                    user_id=ids["user_a"],
                    display_name=f"tenant_{uuid.uuid4().hex[:12]}",
                    display_name_normalized=f"tenant_{uuid.uuid4().hex[:12]}",
                ),
                CommunityBlock(
                    id=ids["community_block"],
                    user_id=ids["user_a"],
                    blocked_user_id=ids["user_b"],
                ),
            ]
        )
        session.commit()

    return ids


def _count(session: Session, table: str, column: str, row_id: uuid.UUID) -> int:
    return session.scalar(
        text(f"SELECT count(*) FROM {table} WHERE {column} = :row_id"),
        {"row_id": row_id},
    )


def test_all_private_tables_have_forced_rls_and_policy(postgres_admin_engine) -> None:
    with postgres_admin_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       count(p.policyname) FILTER (
                           WHERE p.policyname = 'tenant_isolation'
                       ) AS policy_count
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                LEFT JOIN pg_policies AS p
                  ON p.schemaname = n.nspname AND p.tablename = c.relname
                WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
                GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity
                """
            ),
            {"tables": sorted(PROTECTED_TABLES)},
        ).all()

    assert {row.relname for row in rows} == PROTECTED_TABLES
    assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)
    assert all(row.policy_count == 1 for row in rows)


def test_user_b_cannot_read_update_or_delete_user_a_records(
    postgres_runtime_engine,
    tenant_records,
) -> None:
    records = {
        "saved_opportunities": ("id", tenant_records["saved"]),
        "applications": ("id", tenant_records["application"]),
        "application_tasks": ("id", tenant_records["task"]),
        "application_reminders": ("id", tenant_records["reminder"]),
        "application_notification_preferences": ("user_id", tenant_records["user_a"]),
        "application_events": ("id", tenant_records["event"]),
        "application_documents": ("id", tenant_records["application_document"]),
        "assistant_conversations": ("id", tenant_records["conversation"]),
        "assistant_messages": ("id", tenant_records["message"]),
        "assistant_evidence_packets": ("id", tenant_records["evidence"]),
        "assistant_answers": ("id", tenant_records["answer"]),
        "document_assets": ("id", tenant_records["asset"]),
        "document_versions": ("id", tenant_records["version"]),
        "student_profiles": ("id", tenant_records["profile"]),
        "match_evaluations": ("id", tenant_records["evaluation"]),
        "community_preferences": ("user_id", tenant_records["user_a"]),
        "community_blocks": ("id", tenant_records["community_block"]),
    }

    with Session(postgres_runtime_engine) as session:
        bind_tenant_context(session, tenant_records["user_b"])
        assert all(
            _count(session, table, column, row_id) == 0
            for table, (column, row_id) in records.items()
        )
        assert (
            session.execute(
                text("UPDATE applications SET notes = 'attacked' WHERE id = :id"),
                {"id": tenant_records["application"]},
            ).rowcount
            == 0
        )
        assert (
            session.execute(
                text("UPDATE application_tasks SET notes = 'attacked' WHERE id = :id"),
                {"id": tenant_records["task"]},
            ).rowcount
            == 0
        )
        assert (
            session.execute(
                text("UPDATE assistant_messages SET content = 'attacked' WHERE id = :id"),
                {"id": tenant_records["message"]},
            ).rowcount
            == 0
        )
        assert (
            session.execute(
                text("DELETE FROM document_versions WHERE id = :id"),
                {"id": tenant_records["version"]},
            ).rowcount
            == 0
        )
        session.commit()


def test_user_b_cannot_spoof_owner_or_cross_tenant_parent(
    postgres_runtime_engine,
    tenant_records,
) -> None:
    with Session(postgres_runtime_engine) as session:
        bind_tenant_context(session, tenant_records["user_b"])
        with pytest.raises(DBAPIError, match="row-level security"):
            session.execute(
                text(
                    """
                    INSERT INTO assistant_conversations
                        (id, user_id, title, history_enabled)
                    VALUES (:id, :user_id, 'spoofed owner', true)
                    """
                ),
                {"id": uuid.uuid4(), "user_id": tenant_records["user_a"]},
            )
            session.commit()

    with Session(postgres_runtime_engine) as session:
        bind_tenant_context(session, tenant_records["user_b"])
        with pytest.raises(DBAPIError, match="row-level security"):
            session.execute(
                text(
                    """
                    INSERT INTO application_tasks
                        (id, application_id, category, title, status, priority, is_generated)
                    VALUES
                        (:id, :application_id, 'document', 'spoofed parent',
                         'todo', 'normal', false)
                    """
                ),
                {"id": uuid.uuid4(), "application_id": tenant_records["application"]},
            )
            session.commit()

    with Session(postgres_runtime_engine) as session:
        bind_tenant_context(session, tenant_records["user_b"])
        with pytest.raises(DBAPIError, match="row-level security"):
            session.add(
                DocumentVersion(
                    asset_id=tenant_records["asset"],
                    user_id=tenant_records["user_b"],
                    version_number=2,
                    storage_key=f"tenant-attack/{uuid.uuid4().hex}",
                    content_sha256="c" * 64,
                    declared_content_type="application/pdf",
                    detected_content_type="application/pdf",
                    size_bytes=64,
                )
            )
            session.commit()


def test_context_survives_commit_and_does_not_leak_through_pool(
    postgres_runtime_engine,
    tenant_records,
) -> None:
    with Session(postgres_runtime_engine) as session:
        bind_tenant_context(session, tenant_records["user_a"])
        assert _count(session, "applications", "id", tenant_records["application"]) == 1
        session.commit()
        assert _count(session, "applications", "id", tenant_records["application"]) == 1

    with Session(postgres_runtime_engine) as session:
        assert _count(session, "applications", "id", tenant_records["application"]) == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            session.execute(
                text(
                    """
                    INSERT INTO assistant_conversations
                        (id, user_id, title, history_enabled)
                    VALUES (:id, :user_id, 'missing context', true)
                    """
                ),
                {"id": uuid.uuid4(), "user_id": tenant_records["user_a"]},
            )
            session.commit()


def test_explicit_system_context_can_process_cross_tenant_rows(
    postgres_runtime_engine,
    tenant_records,
) -> None:
    with Session(
        postgres_runtime_engine,
        info={"tenant_bypass": True},
    ) as session:
        assert _count(session, "applications", "id", tenant_records["application"]) == 1
        assert (
            session.execute(
                text("UPDATE application_reminders SET message = message WHERE id = :id"),
                {"id": tenant_records["reminder"]},
            ).rowcount
            == 1
        )
        session.rollback()


def test_bound_session_cannot_be_reused_for_another_tenant(
    postgres_runtime_engine,
    tenant_records,
) -> None:
    with Session(postgres_runtime_engine) as session:
        bind_tenant_context(session, tenant_records["user_a"])
        with pytest.raises(RuntimeError, match="cannot change tenants"):
            bind_tenant_context(session, tenant_records["user_b"])
