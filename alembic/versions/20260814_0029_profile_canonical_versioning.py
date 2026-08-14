"""Add canonical profile fields and edit versioning.

Revision ID: 20260814_0029
Revises: 20260814_0028
Create Date: 2026-08-14
"""

import sqlalchemy as sa

from alembic import op

revision = "20260814_0029"
down_revision = "20260814_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.add_column(sa.Column("nationality_code", sa.String(length=2), nullable=True))
        batch_op.add_column(
            sa.Column("country_of_residence_code", sa.String(length=2), nullable=True)
        )
        batch_op.add_column(
            sa.Column("intended_field_taxonomy", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column("intended_field_detail", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "preferred_destination_country_codes",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_index("ix_student_profiles_nationality_code", ["nationality_code"])
        batch_op.create_index(
            "ix_student_profiles_country_of_residence_code", ["country_of_residence_code"]
        )
        batch_op.create_index(
            "ix_student_profiles_intended_field_taxonomy", ["intended_field_taxonomy"]
        )


def downgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch_op:
        batch_op.drop_index("ix_student_profiles_intended_field_taxonomy")
        batch_op.drop_index("ix_student_profiles_country_of_residence_code")
        batch_op.drop_index("ix_student_profiles_nationality_code")
        batch_op.drop_column("version")
        batch_op.drop_column("preferred_destination_country_codes")
        batch_op.drop_column("intended_field_detail")
        batch_op.drop_column("intended_field_taxonomy")
        batch_op.drop_column("country_of_residence_code")
        batch_op.drop_column("nationality_code")
