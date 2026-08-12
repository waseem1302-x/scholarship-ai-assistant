"""Add private citation-first assistant records.

Revision ID: 20260812_0011
Revises: 20260812_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260812_0011"
down_revision = "20260812_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    message_role = enum(("user", "assistant"), "assistant_message_role")
    answer_status = enum(("completed", "abstained", "blocked", "failed"), "assistant_answer_status")
    feedback_type = enum(
        ("helpful", "not_helpful", "incorrect", "outdated", "missing_citation"),
        "assistant_feedback_type",
    )
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(255)),
        sa.Column("history_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_assistant_conversations_user_created",
        "assistant_conversations",
        ["user_id", "created_at"],
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_assistant_messages_conversation_created",
        "assistant_messages",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "assistant_evidence_packets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("query_interpretation", sa.JSON(), nullable=False),
        sa.Column("scholarship_ids", sa.JSON(), nullable=False),
        sa.Column("source_snapshots", sa.JSON(), nullable=False),
        sa.Column("freshness_status", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("retrieval_version", sa.String(100), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_assistant_evidence_packets_user_created",
        "assistant_evidence_packets",
        ["user_id", "created_at"],
    )
    op.create_table(
        "assistant_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_packet_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_evidence_packets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", answer_status, nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(255), nullable=False),
        sa.Column("prompt_template_version", sa.String(100), nullable=False),
        sa.Column("retrieval_version", sa.String(100), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("saved_to_workspace", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("saved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_assistant_answers_user_created", "assistant_answers", ["user_id", "created_at"]
    )
    op.create_index("ix_assistant_answers_conversation", "assistant_answers", ["conversation_id"])
    op.create_table(
        "assistant_citations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "answer_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id", sa.Uuid(), sa.ForeignKey("opportunities.id", ondelete="SET NULL")
        ),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "source_excerpt_id", sa.Uuid(), sa.ForeignKey("source_excerpts.id", ondelete="SET NULL")
        ),
        sa.Column("claim", sa.String(500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_assistant_citations_answer", "assistant_citations", ["answer_id"])
    op.create_table(
        "assistant_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "answer_id",
            sa.Uuid(),
            sa.ForeignKey("assistant_answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("feedback_type", feedback_type, nullable=False),
        sa.Column("comment", sa.String(1000)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_assistant_feedback_answer_user", "assistant_feedback", ["answer_id", "user_id"]
    )
    op.create_table(
        "assistant_evaluation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(255), nullable=False),
        sa.Column("retrieval_version", sa.String(100), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    for table in (
        "assistant_evaluation_runs",
        "assistant_feedback",
        "assistant_citations",
        "assistant_answers",
        "assistant_evidence_packets",
        "assistant_messages",
        "assistant_conversations",
    ):
        op.drop_table(table)
