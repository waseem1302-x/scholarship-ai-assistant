"""fence source-monitor completion transactions

Revision ID: 20260824_0049
Revises: 20260824_0048
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0049"
down_revision: str | None = "20260824_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("monitor_claim_token", sa.String(length=64), nullable=True))
    op.create_index("ix_sources_monitor_claim_token", "sources", ["monitor_claim_token"])


def downgrade() -> None:
    op.drop_index("ix_sources_monitor_claim_token", table_name="sources")
    op.drop_column("sources", "monitor_claim_token")
