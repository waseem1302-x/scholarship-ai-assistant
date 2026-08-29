"""persist versioned official-source acquisition bundles

Revision ID: 20260825_0055
Revises: 20260825_0054
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260825_0055"
down_revision: str | None = "20260825_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalogue_candidates",
        sa.Column("acquisition_bundle", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("catalogue_candidates", "acquisition_bundle")
