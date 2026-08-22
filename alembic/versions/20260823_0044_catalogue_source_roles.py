"""add explicit provenance roles to catalogue candidate sources

Revision ID: 20260823_0044
Revises: 20260822_0043
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_0044"
down_revision: str | None = "20260822_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


source_role = sa.Enum(
    "discovered",
    "primary",
    "supporting",
    "crawled",
    name="catalogue_candidate_source_role",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("catalogue_candidate_sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_role",
                source_role,
                nullable=False,
                server_default="discovered",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("catalogue_candidate_sources") as batch_op:
        batch_op.drop_constraint("catalogue_candidate_source_role", type_="check")
        batch_op.drop_column("source_role")
