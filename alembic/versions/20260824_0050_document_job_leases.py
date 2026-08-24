"""add bounded document preparation job leases

Revision ID: 20260824_0050
Revises: 20260824_0049
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0050"
down_revision: str | None = "20260824_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_analysis_jobs", sa.Column("claim_token", sa.String(length=64)))
    op.add_column("document_analysis_jobs", sa.Column("claimed_until", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_document_analysis_jobs_claim_token", "document_analysis_jobs", ["claim_token"]
    )
    op.create_index(
        "ix_document_analysis_jobs_claimed_until", "document_analysis_jobs", ["claimed_until"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_analysis_jobs_claimed_until", table_name="document_analysis_jobs")
    op.drop_index("ix_document_analysis_jobs_claim_token", table_name="document_analysis_jobs")
    op.drop_column("document_analysis_jobs", "claimed_until")
    op.drop_column("document_analysis_jobs", "claim_token")
