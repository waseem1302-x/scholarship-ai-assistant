"""Complete structured eligibility categories and evidence references.

Revision ID: 20260812_0009
Revises: 20260812_0008
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0009"
down_revision: str | None = "20260812_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_RULE_TYPES = (
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
)
NEW_RULE_TYPES = (*OLD_RULE_TYPES, *(
    "study_mode",
    "intake_year",
    "current_education_level",
    "english_test_status",
    "gre_status",
    "duolingo",
    "gre",
))


def rule_type_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="eligibility_rule_type", native_enum=False, create_constraint=True)


def upgrade() -> None:
    with op.batch_alter_table("student_profiles") as batch:
        batch.add_column(sa.Column("target_intake_year", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_profiles_target_intake_year_range",
            "target_intake_year IS NULL OR target_intake_year BETWEEN 2000 AND 2100",
        )

    with op.batch_alter_table("eligibility_rules") as batch:
        batch.add_column(sa.Column("source_excerpt_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_eligibility_rules_source_excerpt_id_source_excerpts",
            "source_excerpts",
            ["source_excerpt_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.alter_column(
            "rule_type",
            existing_type=rule_type_enum(OLD_RULE_TYPES),
            type_=rule_type_enum(NEW_RULE_TYPES),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("eligibility_rules") as batch:
        batch.alter_column(
            "rule_type",
            existing_type=rule_type_enum(NEW_RULE_TYPES),
            type_=rule_type_enum(OLD_RULE_TYPES),
            existing_nullable=False,
        )
        batch.drop_constraint(
            "fk_eligibility_rules_source_excerpt_id_source_excerpts", type_="foreignkey"
        )
        batch.drop_column("source_excerpt_id")

    with op.batch_alter_table("student_profiles") as batch:
        batch.drop_constraint("ck_profiles_target_intake_year_range", type_="check")
        batch.drop_column("target_intake_year")
