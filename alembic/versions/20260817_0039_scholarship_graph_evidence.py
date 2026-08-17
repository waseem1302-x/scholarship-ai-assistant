"""Add evidence provenance and scoped scholarship facts.

Revision ID: 20260817_0039
Revises: 20260817_0038
Create Date: 2026-08-17

PR2 adapts the graph evidence contract to the repository's existing ``sources``
and ``eligibility_rules`` identities instead of creating parallel tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260817_0039"
down_revision = "20260817_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_OWNER_TYPES = (
    "provider",
    "government",
    "institution",
    "programme",
    "unknown",
)
OFFICIALITY_STATUSES = (
    "official",
    "supporting_official",
    "third_party",
    "unresolved",
)
EVIDENCE_SUPPORT_TYPES = (
    "explicit",
    "partial",
    "contradicts",
    "unknown",
)
EVIDENCE_VALIDATOR_STATUSES = (
    "pending",
    "passed",
    "failed",
)


def _scope_columns(*, scholarship_column: str = "scholarship_id") -> tuple[sa.Column, ...]:
    return (
        sa.Column(scholarship_column, sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=True),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("programme_id", sa.Uuid(), nullable=True),
    )


def _scope_constraints(table_name: str, *, scholarship_column: str = "scholarship_id") -> tuple:
    return (
        sa.CheckConstraint(
            "track_id IS NULL OR cycle_id IS NOT NULL",
            name=f"ck_{table_name}_track_requires_cycle",
        ),
        sa.CheckConstraint(
            "programme_id IS NULL OR institution_id IS NOT NULL",
            name=f"ck_{table_name}_programme_requires_institution",
        ),
        sa.ForeignKeyConstraint(
            [scholarship_column],
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
    )


def _timestamp_version_columns() -> tuple[sa.Column, sa.Column, sa.Column]:
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


def _create_scope_indexes(table_name: str) -> None:
    for column_name in (
        "scholarship_id",
        "cycle_id",
        "track_id",
        "institution_id",
        "programme_id",
    ):
        op.create_index(
            f"ix_{table_name}_{column_name}",
            table_name,
            [column_name],
            unique=False,
        )
    op.create_index(
        f"ix_{table_name}_scope",
        table_name,
        ["scholarship_id", "cycle_id", "track_id", "institution_id", "programme_id"],
        unique=False,
    )


def upgrade() -> None:
    # Reuse the existing public source identity and add graph-specific ownership
    # and officiality metadata. Existing rows remain valid through conservative
    # defaults and nullable enrichment fields.
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(sa.Column("normalized_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("domain", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source_owner_type",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(sa.Column("source_owner_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "officiality_status",
                sa.String(length=32),
                nullable=False,
                server_default="unresolved",
            )
        )
        batch_op.add_column(sa.Column("officiality_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("robots_status", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("content_type", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.create_unique_constraint(
            "uq_sources_opportunity_normalized_url",
            ["opportunity_id", "normalized_url"],
        )
        batch_op.create_check_constraint(
            "source_owner_type",
            "source_owner_type IN ("
            + ", ".join(f"'{value}'" for value in SOURCE_OWNER_TYPES)
            + ")",
        )
        batch_op.create_check_constraint(
            "officiality_status",
            "officiality_status IN ("
            + ", ".join(f"'{value}'" for value in OFFICIALITY_STATUSES)
            + ")",
        )

    for column_name in (
        "normalized_url",
        "domain",
        "source_owner_type",
        "source_owner_id",
        "officiality_status",
        "is_active",
    ):
        op.create_index(
            f"ix_sources_{column_name}",
            "sources",
            [column_name],
            unique=False,
        )
    op.create_index(
        "ix_sources_owner",
        "sources",
        ["source_owner_type", "source_owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_sources_officiality_active",
        "sources",
        ["officiality_status", "is_active"],
        unique=False,
    )

    # Extend the pre-existing eligibility_rules table with the shared graph
    # scope. opportunity_id remains the canonical scholarship FK.
    with op.batch_alter_table("eligibility_rules") as batch_op:
        batch_op.add_column(sa.Column("cycle_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("track_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("institution_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("programme_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_eligibility_rules_cycle_id_opportunity_cycles",
            "opportunity_cycles",
            ["cycle_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_eligibility_rules_track_id_application_tracks",
            "application_tracks",
            ["track_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_eligibility_rules_institution_id_institutions",
            "institutions",
            ["institution_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_eligibility_rules_programme_id_academic_programmes",
            "academic_programmes",
            ["programme_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_check_constraint(
            "ck_eligibility_rules_track_requires_cycle",
            "track_id IS NULL OR cycle_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_eligibility_rules_programme_requires_institution",
            "programme_id IS NULL OR institution_id IS NOT NULL",
        )

    for column_name in ("cycle_id", "track_id", "institution_id", "programme_id"):
        op.create_index(
            f"ix_eligibility_rules_{column_name}",
            "eligibility_rules",
            [column_name],
            unique=False,
        )
    op.create_index(
        "ix_eligibility_rules_graph_scope",
        "eligibility_rules",
        ["opportunity_id", "cycle_id", "track_id", "institution_id", "programme_id"],
        unique=False,
    )

    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("storage_reference", sa.String(length=2048), nullable=True),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("byte_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("character_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetch_metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_snapshot_http_status",
        ),
        sa.CheckConstraint(
            "byte_count >= 0",
            name="ck_snapshot_byte_count_non_negative",
        ),
        sa.CheckConstraint(
            "character_count >= 0",
            name="ck_snapshot_character_count_non_negative",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "content_hash",
            name="uq_source_snapshots_source_hash",
        ),
    )
    op.create_index(
        "ix_source_snapshots_source_id",
        "source_snapshots",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "ix_source_snapshots_source_fetched",
        "source_snapshots",
        ["source_id", "fetched_at"],
        unique=False,
    )

    op.create_table(
        "field_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_start", sa.Integer(), nullable=False),
        sa.Column("excerpt_end", sa.Integer(), nullable=False),
        sa.Column(
            "support_type",
            sa.Enum(
                *EVIDENCE_SUPPORT_TYPES,
                name="evidence_support_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "validator_status",
            sa.Enum(
                *EVIDENCE_VALIDATOR_STATUSES,
                name="evidence_validator_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "excerpt_start >= 0",
            name="ck_field_evidence_start_non_negative",
        ),
        sa.CheckConstraint(
            "excerpt_end >= excerpt_start",
            name="ck_field_evidence_end_after_start",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "field_path",
            "source_snapshot_id",
            "excerpt_start",
            "excerpt_end",
            "support_type",
            name="uq_field_evidence_claim_span",
        ),
    )
    op.create_index("ix_field_evidence_entity_id", "field_evidence", ["entity_id"], unique=False)
    op.create_index(
        "ix_field_evidence_source_snapshot_id",
        "field_evidence",
        ["source_snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_field_evidence_support_type",
        "field_evidence",
        ["support_type"],
        unique=False,
    )
    op.create_index(
        "ix_field_evidence_validator_status",
        "field_evidence",
        ["validator_status"],
        unique=False,
    )
    op.create_index(
        "ix_field_evidence_entity_field",
        "field_evidence",
        ["entity_type", "entity_id", "field_path"],
        unique=False,
    )
    op.create_index(
        "ix_field_evidence_validation",
        "field_evidence",
        ["support_type", "validator_status", "source_snapshot_id"],
        unique=False,
    )

    op.create_table(
        "scoped_deadlines",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_scope_columns(),
        sa.Column("deadline_type", sa.String(length=64), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamp_version_columns(),
        *_scope_constraints("scoped_deadlines"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_scope_indexes("scoped_deadlines")
    op.create_index(
        "ix_scoped_deadlines_deadline_type",
        "scoped_deadlines",
        ["deadline_type"],
        unique=False,
    )

    op.create_table(
        "funding_components",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_scope_columns(),
        sa.Column("component_type", sa.String(length=64), nullable=False),
        sa.Column("coverage_status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_timestamp_version_columns(),
        *_scope_constraints("funding_components"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_scope_indexes("funding_components")
    op.create_index(
        "ix_funding_components_component_type",
        "funding_components",
        ["component_type"],
        unique=False,
    )
    op.create_index(
        "ix_funding_components_coverage_status",
        "funding_components",
        ["coverage_status"],
        unique=False,
    )

    op.create_table(
        "required_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_scope_columns(),
        sa.Column("document_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamp_version_columns(),
        *_scope_constraints("required_documents"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_scope_indexes("required_documents")
    op.create_index(
        "ix_required_documents_document_key",
        "required_documents",
        ["document_key"],
        unique=False,
    )

    op.create_table(
        "application_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_scope_columns(),
        sa.Column("step_code", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("application_url", sa.String(length=2048), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        *_timestamp_version_columns(),
        *_scope_constraints("application_steps"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_scope_indexes("application_steps")
    op.create_index(
        "ix_application_steps_step_code",
        "application_steps",
        ["step_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("application_steps")
    op.drop_table("required_documents")
    op.drop_table("funding_components")
    op.drop_table("scoped_deadlines")
    op.drop_table("field_evidence")
    op.drop_table("source_snapshots")

    op.drop_index("ix_eligibility_rules_graph_scope", table_name="eligibility_rules")
    for column_name in ("programme_id", "institution_id", "track_id", "cycle_id"):
        op.drop_index(f"ix_eligibility_rules_{column_name}", table_name="eligibility_rules")
    with op.batch_alter_table("eligibility_rules") as batch_op:
        batch_op.drop_constraint(
            "ck_eligibility_rules_programme_requires_institution",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_eligibility_rules_track_requires_cycle",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_eligibility_rules_programme_id_academic_programmes",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_eligibility_rules_institution_id_institutions",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_eligibility_rules_track_id_application_tracks",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_eligibility_rules_cycle_id_opportunity_cycles",
            type_="foreignkey",
        )
        batch_op.drop_column("programme_id")
        batch_op.drop_column("institution_id")
        batch_op.drop_column("track_id")
        batch_op.drop_column("cycle_id")

    op.drop_index("ix_sources_officiality_active", table_name="sources")
    op.drop_index("ix_sources_owner", table_name="sources")
    for column_name in (
        "is_active",
        "officiality_status",
        "source_owner_id",
        "source_owner_type",
        "domain",
        "normalized_url",
    ):
        op.drop_index(f"ix_sources_{column_name}", table_name="sources")
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_constraint("officiality_status", type_="check")
        batch_op.drop_constraint("source_owner_type", type_="check")
        batch_op.drop_constraint("uq_sources_opportunity_normalized_url", type_="unique")
        batch_op.drop_column("is_active")
        batch_op.drop_column("consecutive_failures")
        batch_op.drop_column("last_success_at")
        batch_op.drop_column("last_fetched_at")
        batch_op.drop_column("content_type")
        batch_op.drop_column("robots_status")
        batch_op.drop_column("officiality_reason")
        batch_op.drop_column("officiality_status")
        batch_op.drop_column("source_owner_id")
        batch_op.drop_column("source_owner_type")
        batch_op.drop_column("domain")
        batch_op.drop_column("normalized_url")
