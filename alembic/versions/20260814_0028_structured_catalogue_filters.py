"""Add structured public catalogue filter support.

Revision ID: 20260814_0028
Revises: 20260814_0027
Create Date: 2026-08-14
"""

import sqlalchemy as sa

from alembic import op

revision = "20260814_0028"
down_revision = "20260814_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "application_fee_status",
                sa.String(length=16),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.create_index("ix_opportunities_application_fee_status", ["application_fee_status"])

    op.create_table(
        "eligibility_rule_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("value_key", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["eligibility_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id", "value_key", name="uq_eligibility_rule_value_key"),
    )
    op.create_index(
        "ix_eligibility_rule_values_rule_id",
        "eligibility_rule_values",
        ["rule_id"],
    )
    op.create_index(
        "ix_eligibility_rule_values_value_key",
        "eligibility_rule_values",
        ["value_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_eligibility_rule_values_value_key", table_name="eligibility_rule_values")
    op.drop_index("ix_eligibility_rule_values_rule_id", table_name="eligibility_rule_values")
    op.drop_table("eligibility_rule_values")
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_index("ix_opportunities_application_fee_status")
        batch_op.drop_column("application_fee_status")
