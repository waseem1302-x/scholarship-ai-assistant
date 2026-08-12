"""Add assistant consent, retention, and claim citation controls.

Revision ID: 20260812_0012
Revises: 20260812_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260812_0012"
down_revision = "20260812_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assistant_conversations", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_assistant_conversations_expires_at", "assistant_conversations", ["expires_at"]
    )
    op.add_column("assistant_answers", sa.Column("failure_code", sa.String(100)))
    op.add_column(
        "assistant_citations",
        sa.Column("claim_key", sa.String(100), nullable=False, server_default="source_record"),
    )
    op.add_column("assistant_feedback", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_assistant_feedback_expires_at", "assistant_feedback", ["expires_at"])
    op.create_table(
        "assistant_privacy_preferences",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("history_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("consented_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("assistant_privacy_preferences")
    op.drop_index("ix_assistant_feedback_expires_at", table_name="assistant_feedback")
    op.drop_column("assistant_feedback", "expires_at")
    op.drop_column("assistant_citations", "claim_key")
    op.drop_column("assistant_answers", "failure_code")
    op.drop_index("ix_assistant_conversations_expires_at", table_name="assistant_conversations")
    op.drop_column("assistant_conversations", "expires_at")
