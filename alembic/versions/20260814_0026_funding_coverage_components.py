"""Add component-level funding coverage evidence.

Revision ID: 20260814_0026
Revises: 20260814_0025
Create Date: 2026-08-14
"""

import sqlalchemy as sa

from alembic import op

revision = "20260814_0026"
down_revision = "20260814_0025"
branch_labels = None
depends_on = None

COVERAGE_COLUMNS = (
    "tuition_coverage_status",
    "stipend_coverage_status",
    "accommodation_coverage_status",
    "travel_coverage_status",
    "insurance_coverage_status",
    "fees_coverage_status",
)


def upgrade() -> None:
    # A single named SQLAlchemy Enum check cannot be reused across several
    # PostgreSQL columns: each generated CHECK would have the same constraint
    # name. Keep the value type portable and create one uniquely named check per
    # column instead.
    coverage_status = sa.Enum(
        "confirmed",
        "partial",
        "not_covered",
        "unknown",
        name="funding_coverage_status",
        native_enum=False,
        create_constraint=False,
    )
    classification = sa.Enum(
        "fully_funded",
        "partial",
        "unknown",
        name="funding_classification",
        native_enum=False,
        create_constraint=False,
    )
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "funding_classification", classification, nullable=False, server_default="unknown"
            )
        )
        batch_op.create_check_constraint(
            "ck_opportunities_funding_classification",
            "funding_classification IN ('fully_funded', 'partial', 'unknown')",
        )
        batch_op.add_column(sa.Column("funding_policy", sa.Text(), nullable=True))
        for column in COVERAGE_COLUMNS:
            batch_op.add_column(
                sa.Column(column, coverage_status, nullable=False, server_default="unknown")
            )
            batch_op.create_check_constraint(
                f"ck_opportunities_{column}",
                f"{column} IN ('confirmed', 'partial', 'not_covered', 'unknown')",
            )
        batch_op.create_index("ix_opportunities_funding_classification", ["funding_classification"])

    # Historic free text is not reliable enough to assert full coverage.
    op.execute(
        "UPDATE opportunities SET funding_classification = 'partial' "
        "WHERE funding_type IN ('full', 'partial', 'tuition_only', 'stipend_only')"
    )


def downgrade() -> None:
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_index("ix_opportunities_funding_classification")
        batch_op.drop_constraint("ck_opportunities_funding_classification", type_="check")
        for column in reversed(COVERAGE_COLUMNS):
            batch_op.drop_constraint(f"ck_opportunities_{column}", type_="check")
            batch_op.drop_column(column)
        batch_op.drop_column("funding_policy")
        batch_op.drop_column("funding_classification")
