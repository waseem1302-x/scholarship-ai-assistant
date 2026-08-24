"""persist catalogue routing authority tier

Revision ID: 20260824_0053
Revises: 20260824_0052
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0053"
down_revision: str | None = "20260824_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalogue_source_routing_decisions",
        sa.Column(
            "authority_tier", sa.String(length=16), nullable=False, server_default="unresolved"
        ),
    )


def downgrade() -> None:
    op.drop_column("catalogue_source_routing_decisions", "authority_tier")
