"""Harden Document Lab storage consistency and metadata.

Revision ID: 20260814_0031
Revises: 20260814_0030
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260814_0031"
down_revision = "20260814_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_assets", sa.Column("deletion_status", sa.String(32)))
    op.add_column("document_assets", sa.Column("deletion_requested_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_document_assets_deletion_status", "document_assets", ["deletion_status"]
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "encryption_key_version",
            sa.String(100),
            nullable=False,
            server_default="phase7.local-key.v1",
        ),
    )
    op.add_column(
        "document_feedback_items",
        sa.Column("rubric_category", sa.String(100), nullable=False, server_default="general"),
    )
    op.add_column(
        "document_feedback_items",
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
    )


def downgrade() -> None:
    op.drop_column("document_feedback_items", "confidence")
    op.drop_column("document_feedback_items", "rubric_category")
    op.drop_column("document_versions", "encryption_key_version")
    op.drop_index("ix_document_assets_deletion_status", table_name="document_assets")
    op.drop_column("document_assets", "deletion_requested_at")
    op.drop_column("document_assets", "deletion_status")
