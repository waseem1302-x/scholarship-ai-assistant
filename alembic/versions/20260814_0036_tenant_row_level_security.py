"""Enforce tenant isolation on private student records with PostgreSQL RLS.

Revision ID: 20260814_0036
Revises: 20260814_0035
Create Date: 2026-08-14
"""

from collections.abc import Sequence

from alembic import op

revision = "20260814_0036"
down_revision = "20260814_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIRECT_POLICIES = {
    "student_profiles": "user_id = scholarship_current_tenant_id()",
    "saved_opportunities": "user_id = scholarship_current_tenant_id()",
    "application_notification_preferences": "user_id = scholarship_current_tenant_id()",
    "assistant_conversations": "user_id = scholarship_current_tenant_id()",
    "assistant_evidence_packets": "user_id = scholarship_current_tenant_id()",
    "assistant_privacy_preferences": "user_id = scholarship_current_tenant_id()",
    "document_assets": "user_id = scholarship_current_tenant_id()",
    "community_preferences": "user_id = scholarship_current_tenant_id()",
    "community_bookmarks": "user_id = scholarship_current_tenant_id()",
    "community_blocks": "user_id = scholarship_current_tenant_id()",
    "community_reports": "reporter_user_id = scholarship_current_tenant_id()",
}

RELATIONAL_POLICIES = {
    "applications": """
        user_id = scholarship_current_tenant_id()
        AND (
            saved_opportunity_id IS NULL
            OR EXISTS (
                SELECT 1
                FROM saved_opportunities AS saved
                WHERE saved.id = saved_opportunity_id
            )
        )
    """,
    "application_tasks": """
        EXISTS (
            SELECT 1 FROM applications AS parent
            WHERE parent.id = application_id
        )
    """,
    "application_reminders": """
        EXISTS (
            SELECT 1 FROM applications AS parent
            WHERE parent.id = application_id
        )
    """,
    "application_events": """
        EXISTS (
            SELECT 1 FROM applications AS parent
            WHERE parent.id = application_id
        )
    """,
    "application_documents": """
        EXISTS (
            SELECT 1 FROM applications AS parent
            WHERE parent.id = application_id
        )
    """,
    "assistant_messages": """
        EXISTS (
            SELECT 1 FROM assistant_conversations AS parent
            WHERE parent.id = conversation_id
        )
    """,
    "assistant_answers": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM assistant_conversations AS conversation
            WHERE conversation.id = conversation_id
        )
        AND EXISTS (
            SELECT 1 FROM assistant_evidence_packets AS packet
            WHERE packet.id = evidence_packet_id
        )
    """,
    "assistant_citations": """
        EXISTS (
            SELECT 1 FROM assistant_answers AS parent
            WHERE parent.id = answer_id
        )
    """,
    "assistant_feedback": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM assistant_answers AS parent
            WHERE parent.id = answer_id
        )
    """,
    "document_versions": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM document_assets AS parent
            WHERE parent.id = asset_id
        )
    """,
    "document_extractions": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM document_versions AS parent
            WHERE parent.id = version_id
        )
    """,
    "document_consents": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM document_versions AS parent
            WHERE parent.id = version_id
        )
    """,
    "document_analyses": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM document_versions AS version
            WHERE version.id = version_id
        )
        AND EXISTS (
            SELECT 1 FROM document_consents AS consent
            WHERE consent.id = consent_id
        )
    """,
    "document_feedback_items": """
        EXISTS (
            SELECT 1 FROM document_analyses AS parent
            WHERE parent.id = analysis_id
        )
    """,
    "document_analysis_jobs": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM document_versions AS version
            WHERE version.id = version_id
        )
        AND (
            analysis_id IS NULL
            OR EXISTS (
                SELECT 1 FROM document_analyses AS analysis
                WHERE analysis.id = analysis_id
            )
        )
    """,
    "application_document_links": """
        user_id = scholarship_current_tenant_id()
        AND EXISTS (
            SELECT 1 FROM application_documents AS application_document
            WHERE application_document.id = application_document_id
        )
        AND EXISTS (
            SELECT 1 FROM document_versions AS version
            WHERE version.id = version_id
        )
    """,
    "match_evaluations": """
        user_id = scholarship_current_tenant_id()
        AND (
            profile_id IS NULL
            OR EXISTS (
                SELECT 1 FROM student_profiles AS profile
                WHERE profile.id = profile_id
            )
        )
    """,
    "match_evaluation_results": """
        EXISTS (
            SELECT 1 FROM match_evaluations AS parent
            WHERE parent.id = evaluation_id
        )
    """,
    "match_rule_outcomes": """
        EXISTS (
            SELECT 1
            FROM match_evaluation_results AS result
            WHERE result.id = evaluation_result_id
        )
    """,
}

PROTECTED_TABLES = tuple(DIRECT_POLICIES) + tuple(RELATIONAL_POLICIES)


def _policy_sql(table: str, predicate: str) -> str:
    return f"""
        CREATE POLICY tenant_isolation ON {table}
        FOR ALL
        USING (scholarship_tenant_bypass() OR ({predicate}))
        WITH CHECK (scholarship_tenant_bypass() OR ({predicate}))
    """


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE FUNCTION scholarship_current_tenant_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION scholarship_tenant_bypass()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT COALESCE(current_setting('app.tenant_bypass', true), '') = 'on'
        $$
        """
    )

    for table, predicate in {**DIRECT_POLICIES, **RELATIONAL_POLICIES}.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(_policy_sql(table, predicate))


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    for table in reversed(PROTECTED_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS scholarship_tenant_bypass()")
    op.execute("DROP FUNCTION IF EXISTS scholarship_current_tenant_id()")
