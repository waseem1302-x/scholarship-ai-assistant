"""Add Community public identity and normalized display names.

Revision ID: 20260814_0032
Revises: 20260814_0031
Create Date: 2026-08-14
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260814_0032"
down_revision = "20260814_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("community_preferences", sa.Column("public_id", sa.Uuid(), nullable=True))
    op.add_column(
        "community_preferences",
        sa.Column("display_name_normalized", sa.String(40), nullable=True),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT user_id, display_name FROM community_preferences")
    ).mappings()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE community_preferences "
                "SET public_id = :public_id, display_name_normalized = :normalized "
                "WHERE user_id = :user_id"
            ),
            {
                "public_id": uuid.uuid4(),
                "normalized": row["display_name"].casefold(),
                "user_id": row["user_id"],
            },
        )
    with op.batch_alter_table("community_preferences") as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column(
            "display_name_normalized", existing_type=sa.String(40), nullable=False
        )
        batch_op.create_unique_constraint(
            "uq_community_preferences_public_id", ["public_id"]
        )
        batch_op.create_unique_constraint(
            "uq_community_preferences_display_name_normalized",
            ["display_name_normalized"],
        )
    op.create_index(
        "ix_community_preferences_public_id", "community_preferences", ["public_id"]
    )
    op.create_index(
        "ix_community_preferences_display_name_normalized",
        "community_preferences",
        ["display_name_normalized"],
    )


def downgrade() -> None:
    op.drop_index("ix_community_preferences_display_name_normalized", "community_preferences")
    op.drop_index("ix_community_preferences_public_id", "community_preferences")
    with op.batch_alter_table("community_preferences") as batch_op:
        batch_op.drop_constraint(
            "uq_community_preferences_display_name_normalized", type_="unique"
        )
        batch_op.drop_constraint("uq_community_preferences_public_id", type_="unique")
        batch_op.drop_column("display_name_normalized")
        batch_op.drop_column("public_id")
