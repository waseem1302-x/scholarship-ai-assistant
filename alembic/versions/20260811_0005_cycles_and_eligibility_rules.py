"""Add application-cycle history and structured eligibility rules.

Revision ID: 20260811_0005
Revises: 20260722_0004
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_0005"
down_revision: str | None = "20260722_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum_values(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "opportunity_cycles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("intake_year", sa.Integer(), nullable=True),
        sa.Column("application_opening_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("is_rolling", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "application_deadline IS NULL OR application_opening_date IS NULL "
            "OR application_deadline >= application_opening_date",
            name="ck_opportunity_cycles_deadline_after_opening",
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_cycles_opportunity_id", "opportunity_cycles", ["opportunity_id"]
    )

    op.create_table(
        "eligibility_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "rule_type",
            enum_values(
                "nationality",
                "residence",
                "target_degree",
                "field",
                "cgpa",
                "percentage",
                "ielts",
                "toefl",
                "work_experience_months",
                "application_window",
                name="eligibility_rule_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "operator",
            enum_values("equals", "in", "not_in", "gte", "lte", name="eligibility_operator"),
            nullable=False,
        ),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("grading_scale", sa.Numeric(5, 2), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "confidence",
            enum_values("low", "medium", "high", name="eligibility_rule_confidence"),
            nullable=False,
        ),
        sa.Column("curator_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eligibility_rules_opportunity_id", "eligibility_rules", ["opportunity_id"])


def downgrade() -> None:
    op.drop_index("ix_eligibility_rules_opportunity_id", table_name="eligibility_rules")
    op.drop_table("eligibility_rules")
    op.drop_index("ix_opportunity_cycles_opportunity_id", table_name="opportunity_cycles")
    op.drop_table("opportunity_cycles")
