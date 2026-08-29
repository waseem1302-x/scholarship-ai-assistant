"""persist versioned publication readiness

Revision ID: 20260825_0054
Revises: 20260824_0053
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260825_0054"
down_revision: str | None = "20260824_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("publication_readiness_policy_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("publication_readiness_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_opportunities_publication_readiness",
        "opportunities",
        [
            "status",
            "publication_completeness",
            "publication_readiness_policy_version",
            "next_review_at",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_publication_readiness", table_name="opportunities")
    op.drop_column("opportunities", "publication_readiness_evaluated_at")
    op.drop_column("opportunities", "publication_readiness_policy_version")
