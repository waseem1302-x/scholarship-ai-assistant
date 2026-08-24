"""add durable private document deletion jobs

Revision ID: 20260824_0051
Revises: 20260824_0050
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0051"
down_revision: str | None = "20260824_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_deletion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        # Deliberately no asset FK: completed jobs survive hard asset deletion
        # as compact operational evidence without retaining private payloads.
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("storage_keys", sa.JSON(), nullable=False),
        sa.Column("object_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.String(length=64)),
        sa.Column("claimed_until", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_code", sa.String(length=100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", name="uq_document_deletion_jobs_asset"),
    )
    op.create_index("ix_document_deletion_jobs_asset_id", "document_deletion_jobs", ["asset_id"])
    op.create_index("ix_document_deletion_jobs_status", "document_deletion_jobs", ["status"])
    op.create_index(
        "ix_document_deletion_jobs_claim_token", "document_deletion_jobs", ["claim_token"]
    )
    op.create_index(
        "ix_document_deletion_jobs_claimed_until", "document_deletion_jobs", ["claimed_until"]
    )
    op.create_index(
        "ix_document_deletion_jobs_status_next",
        "document_deletion_jobs",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_deletion_jobs_status_next", table_name="document_deletion_jobs")
    op.drop_index("ix_document_deletion_jobs_claimed_until", table_name="document_deletion_jobs")
    op.drop_index("ix_document_deletion_jobs_claim_token", table_name="document_deletion_jobs")
    op.drop_index("ix_document_deletion_jobs_status", table_name="document_deletion_jobs")
    op.drop_index("ix_document_deletion_jobs_asset_id", table_name="document_deletion_jobs")
    op.drop_table("document_deletion_jobs")
