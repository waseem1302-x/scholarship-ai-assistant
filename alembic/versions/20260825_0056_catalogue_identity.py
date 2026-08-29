"""add deterministic family, route, and cycle identity keys

Revision ID: 20260825_0056
Revises: 20260825_0055
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260825_0056"
down_revision: str | None = "20260825_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("programme_route_id", sa.String(120)))
    op.add_column("opportunities", sa.Column("catalogue_family_key", sa.String(64)))
    op.add_column("opportunities", sa.Column("catalogue_route_key", sa.String(64)))
    op.add_column("opportunities", sa.Column("catalogue_identity_key", sa.String(64)))
    op.add_column(
        "opportunities", sa.Column("catalogue_identity_policy_version", sa.String(64))
    )
    op.create_index(
        "ix_opportunity_programme_route_id",
        "opportunities",
        ["programme_route_id"],
    )
    op.create_index(
        "ix_opportunity_catalogue_family_key",
        "opportunities",
        ["catalogue_family_key"],
    )
    op.create_index(
        "ix_opportunity_catalogue_route_key",
        "opportunities",
        ["catalogue_route_key"],
    )
    op.create_index(
        "uq_opportunity_catalogue_identity_key",
        "opportunities",
        ["catalogue_identity_key"],
        unique=True,
        sqlite_where=sa.text("catalogue_identity_key IS NOT NULL"),
        postgresql_where=sa.text("catalogue_identity_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_opportunity_catalogue_identity_key", table_name="opportunities")
    op.drop_index("ix_opportunity_catalogue_route_key", table_name="opportunities")
    op.drop_index("ix_opportunity_catalogue_family_key", table_name="opportunities")
    op.drop_index("ix_opportunity_programme_route_id", table_name="opportunities")
    op.drop_column("opportunities", "catalogue_identity_policy_version")
    op.drop_column("opportunities", "catalogue_identity_key")
    op.drop_column("opportunities", "catalogue_route_key")
    op.drop_column("opportunities", "catalogue_family_key")
    op.drop_column("opportunities", "programme_route_id")
