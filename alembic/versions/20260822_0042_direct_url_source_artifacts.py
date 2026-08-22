"""Add direct URL intake metadata and immutable source artifacts.

Revision ID: 20260822_0042
Revises: 20260820_0041
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260822_0042"
down_revision = "20260820_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "input_kind",
                sa.Enum(
                    "seed_source",
                    "direct_url",
                    name="catalogue_ingestion_input_kind",
                    native_enum=False,
                    create_constraint=True,
                ),
                nullable=False,
                server_default="seed_source",
            )
        )
        batch_op.add_column(sa.Column("operator_url", sa.String(length=2048), nullable=True))
        batch_op.create_index(
            op.f("ix_catalogue_ingestion_runs_input_kind"), ["input_kind"]
        )

    with op.batch_alter_table("catalogue_candidates") as batch_op:
        batch_op.add_column(
            sa.Column(
                "identity_hint_is_asserted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.create_table(
        "catalogue_source_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(length=64), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("fetch_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("byte_count >= 0", name="ck_catalogue_artifact_bytes_nonnegative"),
        sa.CheckConstraint(
            "character_count >= 0", name="ck_catalogue_artifact_characters_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["catalogue_candidate_sources.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "content_hash", name="uq_catalogue_source_artifact_hash"
        ),
    )
    op.create_index(
        op.f("ix_catalogue_source_artifacts_source_id"),
        "catalogue_source_artifacts",
        ["source_id"],
    )
    op.create_index(
        "ix_catalogue_source_artifacts_hash_created",
        "catalogue_source_artifacts",
        ["content_hash", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_source_artifacts_hash_created",
        table_name="catalogue_source_artifacts",
    )
    op.drop_index(
        op.f("ix_catalogue_source_artifacts_source_id"),
        table_name="catalogue_source_artifacts",
    )
    op.drop_table("catalogue_source_artifacts")

    with op.batch_alter_table("catalogue_candidates") as batch_op:
        batch_op.drop_column("identity_hint_is_asserted")

    with op.batch_alter_table("catalogue_ingestion_runs") as batch_op:
        batch_op.drop_index(op.f("ix_catalogue_ingestion_runs_input_kind"))
        batch_op.drop_constraint("catalogue_ingestion_input_kind", type_="check")
        batch_op.drop_column("operator_url")
        batch_op.drop_column("input_kind")
