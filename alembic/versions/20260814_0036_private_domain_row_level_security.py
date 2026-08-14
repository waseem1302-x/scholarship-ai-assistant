"""Add a second PostgreSQL tenant boundary for private student domains.

Revision ID: 20260814_0036
Revises: 20260814_0035
Create Date: 2026-08-14

The HTTP application still performs explicit owner-scoped authorization. These
policies are defense in depth: a missed owner predicate should return no other
student's private rows when the API runtime uses its restricted database role.

Scheduled cross-tenant jobs use a distinct `scholarship_worker` database login
and a distinct managed identity/Key Vault secret. That role is intentionally
recognized by these policies; the public API database login must never use it.
"""

from collections.abc import Sequence

from alembic import op

revision = "20260814_0036"
down_revision = "20260814_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_EXPR = (
    "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
)
_WORKER_EXPR = "current_user = 'scholarship_worker'"

_DIRECT_OWNER_TABLES = (
    "student_profiles",
    "saved_opportunities",
    "applications",
    "application_notification_preferences",
    "match_evaluations",
    "assistant_conversations",
    "assistant_evidence_packets",
    "assistant_answers",
    "assistant_feedback",
    "assistant_privacy_preferences",
    "document_assets",
    "document_versions",
    "document_extractions",
    "document_consents",
    "document_analyses",
    "document_analysis_jobs",
    "application_document_links",
)

_CHILD_POLICIES = {
    "application_tasks": (
        "EXISTS (SELECT 1 FROM applications a "
        "WHERE a.id = application_tasks.application_id "
        f"AND a.user_id = {_TENANT_EXPR})"
    ),
    "application_reminders": (
        "EXISTS (SELECT 1 FROM applications a "
        "WHERE a.id = application_reminders.application_id "
        f"AND a.user_id = {_TENANT_EXPR})"
    ),
    "application_events": (
        "EXISTS (SELECT 1 FROM applications a "
        "WHERE a.id = application_events.application_id "
        f"AND a.user_id = {_TENANT_EXPR})"
    ),
    "application_documents": (
        "EXISTS (SELECT 1 FROM applications a "
        "WHERE a.id = application_documents.application_id "
        f"AND a.user_id = {_TENANT_EXPR})"
    ),
    "match_evaluation_results": (
        "EXISTS (SELECT 1 FROM match_evaluations e "
        "WHERE e.id = match_evaluation_results.evaluation_id "
        f"AND e.user_id = {_TENANT_EXPR})"
    ),
    "match_rule_outcomes": (
        "EXISTS (SELECT 1 FROM match_evaluation_results r "
        "JOIN match_evaluations e ON e.id = r.evaluation_id "
        "WHERE r.id = match_rule_outcomes.evaluation_result_id "
        f"AND e.user_id = {_TENANT_EXPR})"
    ),
    "assistant_messages": (
        "EXISTS (SELECT 1 FROM assistant_conversations c "
        "WHERE c.id = assistant_messages.conversation_id "
        f"AND c.user_id = {_TENANT_EXPR})"
    ),
    "assistant_citations": (
        "EXISTS (SELECT 1 FROM assistant_answers a "
        "WHERE a.id = assistant_citations.answer_id "
        f"AND a.user_id = {_TENANT_EXPR})"
    ),
    "document_feedback_items": (
        "EXISTS (SELECT 1 FROM document_analyses a "
        "WHERE a.id = document_feedback_items.analysis_id "
        f"AND a.user_id = {_TENANT_EXPR})"
    ),
}


def _enable_policy(table: str, predicate: str) -> None:
    policy_name = f"tenant_isolation_{table}"
    expression = f"(({predicate}) OR ({_WORKER_EXPR}))"
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{policy_name}" ON "{table}" '
        f"USING ({expression}) WITH CHECK ({expression})"
    )


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        # SQLite remains the fast portable unit-test database. CI also runs the
        # migration and dedicated RLS regression against PostgreSQL.
        return

    for table in _DIRECT_OWNER_TABLES:
        _enable_policy(table, f"user_id = {_TENANT_EXPR}")
    for table, predicate in _CHILD_POLICIES.items():
        _enable_policy(table, predicate)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    for table in (*_DIRECT_OWNER_TABLES, *_CHILD_POLICIES):
        policy_name = f"tenant_isolation_{table}"
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
