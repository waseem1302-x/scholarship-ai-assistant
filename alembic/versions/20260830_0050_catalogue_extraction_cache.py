"""add content-addressed extraction cache and decision ledger

Revision ID: 20260830_0050
Revises: 20260830_0049
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0050"
down_revision: str | None = "20260830_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalogue_extraction_cache_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("origin_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("origin_source_id", sa.Uuid(), nullable=True),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("normalized_content_hash", sa.String(length=64), nullable=False),
        sa.Column("authority_context_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_block_set_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_block_keys", sa.JSON(), nullable=False),
        sa.Column("scope_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("objective_bundle", sa.JSON(), nullable=False),
        sa.Column("objective_bundle_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("normalizer_version", sa.String(length=100), nullable=False),
        sa.Column("resolver_version", sa.String(length=100), nullable=False),
        sa.Column("validator_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("capability_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("cache_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["origin_candidate_id"], ["catalogue_candidates.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["origin_source_id"], ["catalogue_candidate_sources.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key", name="uq_catalogue_extraction_cache_key"),
    )
    for column in (
        "cache_key",
        "origin_candidate_id",
        "origin_source_id",
        "source_artifact_id",
        "normalized_content_hash",
        "authority_context_hash",
        "evidence_block_set_hash",
        "scope_fingerprint",
        "objective_bundle_hash",
        "prompt_hash",
        "schema_version",
        "provider",
        "capability_identity_hash",
    ):
        op.create_index(
            f"ix_catalogue_extraction_cache_entries_{column}",
            "catalogue_extraction_cache_entries",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_catalogue_extraction_cache_content_authority",
        "catalogue_extraction_cache_entries",
        ["normalized_content_hash", "authority_context_hash"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_extraction_cache_versions",
        "catalogue_extraction_cache_entries",
        [
            "prompt_hash",
            "schema_version",
            "parser_version",
            "normalizer_version",
            "resolver_version",
        ],
        unique=False,
    )

    op.create_table(
        "catalogue_extraction_cache_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["catalogue_ingestion_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "run_id",
        "candidate_id",
        "source_artifact_id",
        "cache_key",
        "decision",
    ):
        op.create_index(
            f"ix_catalogue_extraction_cache_events_{column}",
            "catalogue_extraction_cache_events",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_catalogue_extraction_cache_events_candidate_decision",
        "catalogue_extraction_cache_events",
        ["candidate_id", "decision", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_extraction_cache_events_key_created",
        "catalogue_extraction_cache_events",
        ["cache_key", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_extraction_cache_events_key_created",
        table_name="catalogue_extraction_cache_events",
    )
    op.drop_index(
        "ix_catalogue_extraction_cache_events_candidate_decision",
        table_name="catalogue_extraction_cache_events",
    )
    for column in reversed(
        ("run_id", "candidate_id", "source_artifact_id", "cache_key", "decision")
    ):
        op.drop_index(
            f"ix_catalogue_extraction_cache_events_{column}",
            table_name="catalogue_extraction_cache_events",
        )
    op.drop_table("catalogue_extraction_cache_events")

    op.drop_index(
        "ix_catalogue_extraction_cache_versions",
        table_name="catalogue_extraction_cache_entries",
    )
    op.drop_index(
        "ix_catalogue_extraction_cache_content_authority",
        table_name="catalogue_extraction_cache_entries",
    )
    for column in reversed(
        (
            "cache_key",
            "origin_candidate_id",
            "origin_source_id",
            "source_artifact_id",
            "normalized_content_hash",
            "authority_context_hash",
            "evidence_block_set_hash",
            "scope_fingerprint",
            "objective_bundle_hash",
            "prompt_hash",
            "schema_version",
            "provider",
            "capability_identity_hash",
        )
    ):
        op.drop_index(
            f"ix_catalogue_extraction_cache_entries_{column}",
            table_name="catalogue_extraction_cache_entries",
        )
    op.drop_table("catalogue_extraction_cache_entries")
