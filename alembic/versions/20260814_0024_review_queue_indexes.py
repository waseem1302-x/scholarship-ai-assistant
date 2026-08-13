"""Index SQL-backed opportunity review queues.

Revision ID: 20260814_0024
Revises: 20260813_0023
Create Date: 2026-08-14
"""

from alembic import op

revision = "20260814_0024"
down_revision = "20260813_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sources_review_status_freshness",
        "sources",
        ["verification_status", "last_verified_at", "opportunity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sources_review_status_freshness", table_name="sources")
