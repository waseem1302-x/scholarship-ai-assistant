"""Create student profiles.

Revision ID: 20260722_0003
Revises: 20260722_0002
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260722_0003"
down_revision: str | None = "20260722_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum_values(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "student_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nationality", sa.String(length=100), nullable=True),
        sa.Column("country_of_residence", sa.String(length=100), nullable=True),
        sa.Column(
            "current_education_level",
            enum_values(
                "high_school",
                "diploma",
                "bachelors",
                "masters",
                "phd",
                "other",
                name="education_level",
            ),
            nullable=True,
        ),
        sa.Column(
            "target_degree_level",
            enum_values(
                "bachelors",
                "masters",
                "phd",
                "short_course",
                "other",
                name="target_degree_level",
            ),
            nullable=True,
        ),
        sa.Column("intended_field", sa.String(length=255), nullable=True),
        sa.Column("academic_discipline", sa.String(length=255), nullable=True),
        sa.Column("cgpa", sa.Numeric(4, 2), nullable=True),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("grading_scale", sa.Numeric(4, 2), nullable=True),
        sa.Column(
            "english_test_status",
            enum_values(
                "not_taken", "planned", "taken", "not_required", "unknown", name="test_status"
            ),
            nullable=False,
        ),
        sa.Column("ielts_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("toefl_score", sa.Integer(), nullable=True),
        sa.Column("duolingo_score", sa.Integer(), nullable=True),
        sa.Column(
            "gre_status",
            enum_values(
                "not_taken", "planned", "taken", "not_required", "unknown", name="gre_status"
            ),
            nullable=False,
        ),
        sa.Column("gre_score", sa.Integer(), nullable=True),
        sa.Column("work_experience_months", sa.Integer(), nullable=True),
        sa.Column("research_experience", sa.Text(), nullable=True),
        sa.Column("publications", sa.JSON(), nullable=False),
        sa.Column("leadership_experience", sa.Text(), nullable=True),
        sa.Column("financial_need", sa.Text(), nullable=True),
        sa.Column("preferred_destination_countries", sa.JSON(), nullable=False),
        sa.Column(
            "preferred_study_mode",
            enum_values("on_campus", "online", "hybrid", "any", name="study_mode"),
            nullable=True,
        ),
        sa.Column("target_intake", sa.String(length=100), nullable=True),
        sa.Column("application_constraints", sa.Text(), nullable=True),
        sa.Column("additional_eligibility_information", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("cgpa IS NULL OR cgpa >= 0", name="ck_profiles_cgpa_non_negative"),
        sa.CheckConstraint(
            "grading_scale IS NULL OR grading_scale > 0",
            name="ck_profiles_grading_scale_positive",
        ),
        sa.CheckConstraint(
            "cgpa IS NULL OR grading_scale IS NULL OR cgpa <= grading_scale",
            name="ck_profiles_cgpa_within_scale",
        ),
        sa.CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100",
            name="ck_profiles_percentage_range",
        ),
        sa.CheckConstraint(
            "ielts_score IS NULL OR ielts_score BETWEEN 0 AND 9",
            name="ck_profiles_ielts_range",
        ),
        sa.CheckConstraint(
            "toefl_score IS NULL OR toefl_score BETWEEN 0 AND 120",
            name="ck_profiles_toefl_range",
        ),
        sa.CheckConstraint(
            "duolingo_score IS NULL OR duolingo_score BETWEEN 10 AND 160",
            name="ck_profiles_duolingo_range",
        ),
        sa.CheckConstraint(
            "gre_score IS NULL OR gre_score BETWEEN 260 AND 340",
            name="ck_profiles_gre_range",
        ),
        sa.CheckConstraint(
            "work_experience_months IS NULL OR work_experience_months >= 0",
            name="ck_profiles_work_experience_non_negative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_student_profiles_target_degree_level"),
        "student_profiles",
        ["target_degree_level"],
        unique=False,
    )
    op.create_index(
        op.f("ix_student_profiles_user_id"), "student_profiles", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_student_profiles_user_id"), table_name="student_profiles")
    op.drop_index(op.f("ix_student_profiles_target_degree_level"), table_name="student_profiles")
    op.drop_table("student_profiles")
