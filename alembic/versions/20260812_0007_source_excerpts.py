"""Add source evidence excerpts for Phase 2 curation.

Revision ID: 20260812_0007
Revises: 20260811_0006
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0007"
down_revision: str | None = "20260811_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_excerpts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("section_label", sa.String(length=255), nullable=True),
        sa.Column("locator", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("captured_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("text = trim(text)", name="ck_source_excerpts_text_trimmed"),
        sa.ForeignKeyConstraint(["captured_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_excerpts_source_id", "source_excerpts", ["source_id"])
    op.create_index(
        "ix_source_excerpts_source_captured", "source_excerpts", ["source_id", "captured_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_excerpts_source_captured", table_name="source_excerpts")
    op.drop_index("ix_source_excerpts_source_id", table_name="source_excerpts")
    op.drop_table("source_excerpts")
