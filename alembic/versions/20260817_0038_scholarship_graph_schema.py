"""Add the Scholarship Intelligence Graph core schema.

Revision ID: 20260817_0038
Revises: 20260815_0037
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260817_0038"
down_revision = "20260815_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RELATIONSHIP_KINDS = (
    "same_scholarship",
    "same_scheme_track",
    "participating_institution",
    "eligible_programme",
    "institution_specific_requirement",
    "institution_specific_deadline",
    "independent_university_scholarship",
    "independent_government_scholarship",
    "independent_foundation_scholarship",
    "co_funded_award",
    "successor",
    "predecessor",
    "duplicate",
    "unresolved",
)

INDEPENDENCE_STATUSES = (
    "confirmed_independent",
    "same_scheme",
    "duplicate",
    "unresolved",
    "legacy_unreviewed",
)


def _timestamp_columns() -> tuple[sa.Column, sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def upgrade() -> None:
    # Expand the canonical opportunity record without changing the legacy read path.
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.add_column(sa.Column("canonical_slug", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "entity_kind",
                sa.String(length=32),
                nullable=False,
                server_default="scholarship",
            )
        )
        batch_op.add_column(sa.Column("canonical_provider_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("parent_scholarship_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "independence_status",
                sa.String(length=32),
                nullable=False,
                server_default="legacy_unreviewed",
            )
        )
        batch_op.add_column(
            sa.Column(
                "publication_completeness",
                sa.String(length=32),
                nullable=False,
                server_default="incomplete",
            )
        )
        batch_op.add_column(sa.Column("current_cycle_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_opportunities_parent_scholarship_id_opportunities",
            "opportunities",
            ["parent_scholarship_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_opportunities_parent_not_self",
            "parent_scholarship_id IS NULL OR parent_scholarship_id <> id",
        )
        batch_op.create_check_constraint(
            "ck_opportunities_independence_status",
            "independence_status IN ("
            + ", ".join(f"'{value}'" for value in INDEPENDENCE_STATUSES)
            + ")",
        )

    op.create_index(
        "uq_opportunity_canonical_slug",
        "opportunities",
        ["canonical_slug"],
        unique=True,
        postgresql_where=sa.text("canonical_slug IS NOT NULL"),
        sqlite_where=sa.text("canonical_slug IS NOT NULL"),
    )
    op.create_index(
        "ix_opportunity_provider_kind",
        "opportunities",
        ["canonical_provider_id", "entity_kind"],
        unique=False,
    )

    # Reuse the existing historical cycle table and expand it to the graph contract.
    with op.batch_alter_table("opportunity_cycles") as batch_op:
        batch_op.add_column(sa.Column("label", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("status", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("source_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_unique_constraint(
            "uq_opportunity_cycles_opportunity_label",
            ["opportunity_id", "label"],
        )
        batch_op.create_check_constraint(
            "ck_opportunity_cycles_version_positive",
            "version >= 1",
        )

    op.create_index(
        "ix_opportunity_cycles_status",
        "opportunity_cycles",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_opportunity_cycles_one_current",
        "opportunity_cycles",
        ["opportunity_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
        sqlite_where=sa.text("is_current = 1"),
    )

    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("institution_type", sa.String(length=64), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("official_domain", sa.String(length=255), nullable=True),
        sa.Column("official_website", sa.String(length=2048), nullable=True),
        sa.Column("identity_status", sa.String(length=64), nullable=True),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_institutions_slug"),
    )
    op.create_index("ix_institutions_country_code", "institutions", ["country_code"], unique=False)
    op.create_index(
        "ix_institutions_identity_status",
        "institutions",
        ["identity_status"],
        unique=False,
    )

    op.create_table(
        "institution_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id",
            "normalized_alias",
            name="uq_institution_alias_normalized",
        ),
    )
    op.create_index(
        "ix_institution_aliases_institution_id",
        "institution_aliases",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        "ix_institution_aliases_normalized",
        "institution_aliases",
        ["normalized_alias"],
        unique=False,
    )

    op.create_table(
        "scholarship_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["scholarship_id"],
            ["opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scholarship_id",
            "normalized_alias",
            name="uq_scholarship_alias_normalized",
        ),
    )
    op.create_index(
        "ix_scholarship_aliases_scholarship_id",
        "scholarship_aliases",
        ["scholarship_id"],
        unique=False,
    )
    op.create_index(
        "ix_scholarship_aliases_normalized",
        "scholarship_aliases",
        ["normalized_alias"],
        unique=False,
    )

    relationship_kind_check = (
        "relationship_kind IN ("
        + ", ".join(f"'{value}'" for value in RELATIONSHIP_KINDS)
        + ")"
    )
    op.create_table(
        "scholarship_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("related_scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_kind", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "scholarship_id != related_scholarship_id",
            name="ck_scholarship_relationships_not_self",
        ),
        sa.CheckConstraint(
            relationship_kind_check,
            name="scholarship_relationship_kind",
        ),
        sa.ForeignKeyConstraint(
            ["scholarship_id"],
            ["opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_scholarship_id"],
            ["opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scholarship_id",
            "related_scholarship_id",
            "relationship_kind",
            name="uq_scholarship_relationship_kind",
        ),
    )
    op.create_index(
        "ix_scholarship_relationships_scholarship_id",
        "scholarship_relationships",
        ["scholarship_id"],
        unique=False,
    )
    op.create_index(
        "ix_scholarship_relationships_related",
        "scholarship_relationships",
        ["related_scholarship_id"],
        unique=False,
    )
    op.create_index(
        "ix_scholarship_relationships_relationship_kind",
        "scholarship_relationships",
        ["relationship_kind"],
        unique=False,
    )

    op.create_table(
        "academic_programmes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("degree_level", sa.String(length=32), nullable=True),
        sa.Column("field_codes", sa.JSON(), nullable=False),
        sa.Column("programme_url", sa.String(length=2048), nullable=True),
        sa.Column("active_status", sa.String(length=64), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "institution_id",
            "slug",
            name="uq_academic_programmes_institution_slug",
        ),
    )
    op.create_index(
        "ix_academic_programmes_institution_id",
        "academic_programmes",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        "ix_academic_programmes_degree_level",
        "academic_programmes",
        ["degree_level"],
        unique=False,
    )
    op.create_index(
        "ix_academic_programmes_active_status",
        "academic_programmes",
        ["active_status"],
        unique=False,
    )

    op.create_table(
        "application_tracks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("parent_track_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("track_type", sa.String(length=64), nullable=False),
        sa.Column("application_method", sa.Text(), nullable=True),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column("decision_authority_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["scholarship_id"],
            ["opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["opportunity_cycles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_track_id"],
            ["application_tracks.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decision_authority_id"],
            ["institutions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_id",
            "code",
            name="uq_application_tracks_cycle_code",
        ),
    )
    op.create_index(
        "ix_application_tracks_scholarship_id",
        "application_tracks",
        ["scholarship_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_tracks_cycle_id",
        "application_tracks",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_tracks_track_type",
        "application_tracks",
        ["track_type"],
        unique=False,
    )
    op.create_index(
        "ix_application_tracks_status",
        "application_tracks",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_application_tracks_scholarship_cycle",
        "application_tracks",
        ["scholarship_id", "cycle_id"],
        unique=False,
    )

    op.create_table(
        "institution_participations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("participation_status", sa.String(length=64), nullable=True),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["scholarship_id"],
            ["opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["opportunity_cycles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["application_tracks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_id",
            "track_id",
            "institution_id",
            "role",
            name="uq_institution_participation_scope_role",
        ),
    )
    op.create_index(
        "ix_institution_participations_scholarship_id",
        "institution_participations",
        ["scholarship_id"],
        unique=False,
    )
    op.create_index(
        "ix_institution_participations_cycle_id",
        "institution_participations",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_institution_participations_track_id",
        "institution_participations",
        ["track_id"],
        unique=False,
    )
    op.create_index(
        "ix_institution_participations_institution_id",
        "institution_participations",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        "ix_institution_participations_participation_status",
        "institution_participations",
        ["participation_status"],
        unique=False,
    )
    op.create_index(
        "ix_institution_participations_scholarship_institution",
        "institution_participations",
        ["scholarship_id", "institution_id"],
        unique=False,
    )

    op.create_table(
        "track_programmes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("eligibility_status", sa.String(length=64), nullable=True),
        sa.Column("funding_status", sa.String(length=64), nullable=True),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["scholarship_id"],
            ["opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["opportunity_cycles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["application_tracks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["programme_id"],
            ["academic_programmes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_id",
            "track_id",
            "institution_id",
            "programme_id",
            name="uq_track_programmes_scope_programme",
        ),
    )
    op.create_index(
        "ix_track_programmes_scholarship_id",
        "track_programmes",
        ["scholarship_id"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_cycle_id",
        "track_programmes",
        ["cycle_id"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_track_id",
        "track_programmes",
        ["track_id"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_institution_id",
        "track_programmes",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_programme_id",
        "track_programmes",
        ["programme_id"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_eligibility_status",
        "track_programmes",
        ["eligibility_status"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_funding_status",
        "track_programmes",
        ["funding_status"],
        unique=False,
    )
    op.create_index(
        "ix_track_programmes_scholarship_cycle",
        "track_programmes",
        ["scholarship_id", "cycle_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("track_programmes")
    op.drop_table("institution_participations")
    op.drop_table("application_tracks")
    op.drop_table("academic_programmes")
    op.drop_table("scholarship_relationships")
    op.drop_table("scholarship_aliases")
    op.drop_table("institution_aliases")
    op.drop_table("institutions")

    op.drop_index("uq_opportunity_cycles_one_current", table_name="opportunity_cycles")
    op.drop_index("ix_opportunity_cycles_status", table_name="opportunity_cycles")
    with op.batch_alter_table("opportunity_cycles") as batch_op:
        batch_op.drop_constraint("ck_opportunity_cycles_version_positive", type_="check")
        batch_op.drop_constraint("uq_opportunity_cycles_opportunity_label", type_="unique")
        batch_op.drop_column("version")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("source_id")
        batch_op.drop_column("is_current")
        batch_op.drop_column("status")
        batch_op.drop_column("label")

    op.drop_index("ix_opportunity_provider_kind", table_name="opportunities")
    op.drop_index("uq_opportunity_canonical_slug", table_name="opportunities")
    with op.batch_alter_table("opportunities") as batch_op:
        batch_op.drop_constraint("ck_opportunities_independence_status", type_="check")
        batch_op.drop_constraint("ck_opportunities_parent_not_self", type_="check")
        batch_op.drop_constraint(
            "fk_opportunities_parent_scholarship_id_opportunities",
            type_="foreignkey",
        )
        batch_op.drop_column("next_review_at")
        batch_op.drop_column("last_verified_at")
        batch_op.drop_column("current_cycle_id")
        batch_op.drop_column("publication_completeness")
        batch_op.drop_column("independence_status")
        batch_op.drop_column("parent_scholarship_id")
        batch_op.drop_column("canonical_provider_id")
        batch_op.drop_column("entity_kind")
        batch_op.drop_column("canonical_slug")
