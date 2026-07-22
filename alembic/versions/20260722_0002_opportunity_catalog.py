"""Create source-first opportunity catalog.

Revision ID: 20260722_0002
Revises: 20260718_0001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260722_0002"
down_revision: str | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum_values(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("name = trim(name)", name="ck_providers_name_trimmed"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_providers_name"),
    )

    op.create_table(
        "universities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("name = trim(name)", name="ck_universities_name_trimmed"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "country", name="uq_universities_name_country"),
    )

    op.create_table(
        "opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column(
            "degree_level",
            enum_values(
                "bachelors",
                "masters",
                "phd",
                "postdoc",
                "short_course",
                name="degree_level",
            ),
            nullable=False,
        ),
        sa.Column("field_eligibility", sa.Text(), nullable=True),
        sa.Column("nationality_eligibility", sa.Text(), nullable=True),
        sa.Column("application_opening_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intake_year", sa.Integer(), nullable=True),
        sa.Column(
            "funding_type",
            enum_values(
                "full", "partial", "tuition_only", "stipend_only", "unknown", name="funding_type"
            ),
            nullable=False,
        ),
        sa.Column("tuition_coverage", sa.Text(), nullable=True),
        sa.Column("monthly_stipend_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_stipend_currency", sa.String(length=3), nullable=True),
        sa.Column("accommodation_coverage", sa.Text(), nullable=True),
        sa.Column("travel_allowance", sa.Text(), nullable=True),
        sa.Column("health_insurance", sa.Text(), nullable=True),
        sa.Column("application_fee_info", sa.Text(), nullable=True),
        sa.Column("english_language_requirement", sa.Text(), nullable=True),
        sa.Column("standardized_test_requirement", sa.Text(), nullable=True),
        sa.Column("minimum_academic_requirement", sa.Text(), nullable=True),
        sa.Column("required_documents", sa.JSON(), nullable=False),
        sa.Column("application_method", sa.Text(), nullable=True),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column(
            "status",
            enum_values("draft", "active", "expired", "archived", name="opportunity_status"),
            nullable=False,
        ),
        sa.Column(
            "data_confidence",
            enum_values("low", "medium", "high", name="data_confidence"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("eligibility_warnings", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("name = trim(name)", name="ck_opportunities_name_trimmed"),
        sa.CheckConstraint("country = trim(country)", name="ck_opportunities_country_trimmed"),
        sa.CheckConstraint(
            "application_deadline IS NULL OR application_opening_date IS NULL "
            "OR application_deadline >= application_opening_date",
            name="ck_opportunities_deadline_after_opening",
        ),
        sa.CheckConstraint(
            "monthly_stipend_amount IS NULL OR monthly_stipend_amount >= 0",
            name="ck_opportunities_non_negative_stipend",
        ),
        sa.CheckConstraint(
            "intake_year IS NULL OR intake_year >= 2000", name="ck_intake_year_range"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "name",
            "country",
            "intake_year",
            name="uq_opportunities_provider_name_country_intake",
        ),
    )
    op.create_index("ix_opportunities_country_degree", "opportunities", ["country", "degree_level"])
    op.create_index(op.f("ix_opportunities_country"), "opportunities", ["country"], unique=False)
    op.create_index(
        op.f("ix_opportunities_degree_level"), "opportunities", ["degree_level"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_funding_type"), "opportunities", ["funding_type"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_intake_year"), "opportunities", ["intake_year"], unique=False
    )
    op.create_index(
        op.f("ix_opportunities_provider_id"), "opportunities", ["provider_id"], unique=False
    )
    op.create_index(op.f("ix_opportunities_status"), "opportunities", ["status"], unique=False)

    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column(
            "source_type",
            enum_values(
                "official", "government", "university", "provider", "other", name="source_type"
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "date_collected",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("relevant_excerpt", sa.Text(), nullable=False),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "verification_status",
            enum_values(
                "unverified",
                "needs_review",
                "officially_verified",
                "expired",
                "conflicting_information",
                "archived",
                name="verification_status",
            ),
            nullable=False,
        ),
        sa.CheckConstraint("url = trim(url)", name="ck_sources_url_trimmed"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id", "url", name="uq_sources_opportunity_url"),
    )
    op.create_index(op.f("ix_sources_opportunity_id"), "sources", ["opportunity_id"], unique=False)
    op.create_index(
        op.f("ix_sources_verification_status"), "sources", ["verification_status"], unique=False
    )

    op.create_table(
        "verification_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            enum_values(
                "unverified",
                "needs_review",
                "officially_verified",
                "expired",
                "conflicting_information",
                "archived",
                name="verification_record_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("checked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["checked_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verification_records_opportunity_id"),
        "verification_records",
        ["opportunity_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_verification_records_opportunity_id"), table_name="verification_records")
    op.drop_table("verification_records")
    op.drop_index(op.f("ix_sources_verification_status"), table_name="sources")
    op.drop_index(op.f("ix_sources_opportunity_id"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(op.f("ix_opportunities_status"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_provider_id"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_intake_year"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_funding_type"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_degree_level"), table_name="opportunities")
    op.drop_index(op.f("ix_opportunities_country"), table_name="opportunities")
    op.drop_index("ix_opportunities_country_degree", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_table("universities")
    op.drop_table("providers")
