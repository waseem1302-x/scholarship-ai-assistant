"""add complete-document evidence blocks and scoped routing decisions

Revision ID: 20260830_0049
Revises: 20260830_0048
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0049"
down_revision: str | None = "20260830_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OBJECTIVES = (
    "identity",
    "programmes",
    "programme_details",
    "routes",
    "eligibility",
    "eligibility_context",
    "documents_core",
    "documents_requirements",
    "documents_counts",
    "documents_format",
    "funding",
    "application_timeline",
)


def upgrade() -> None:
    op.create_table(
        "catalogue_evidence_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_key", sa.String(length=64), nullable=False),
        sa.Column("block_hash", sa.String(length=64), nullable=False),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("block_text", sa.Text(), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=True),
        sa.Column("section_key", sa.String(length=255), nullable=True),
        sa.Column("coordinate_json", sa.JSON(), nullable=False),
        sa.Column("topology_hints", sa.JSON(), nullable=False),
        sa.Column("language_hints", sa.JSON(), nullable=False),
        sa.Column("source_role", sa.String(length=32), nullable=False),
        sa.Column("builder_version", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["catalogue_candidate_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_artifact_id",
            "builder_version",
            "block_index",
            name="uq_catalogue_evidence_block_position",
        ),
        sa.UniqueConstraint("block_key", name="uq_catalogue_evidence_block_key"),
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_candidate_id",
        "catalogue_evidence_blocks",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_source_id",
        "catalogue_evidence_blocks",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_source_artifact_id",
        "catalogue_evidence_blocks",
        ["source_artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_block_key",
        "catalogue_evidence_blocks",
        ["block_key"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_block_hash",
        "catalogue_evidence_blocks",
        ["block_hash"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_source_content_hash",
        "catalogue_evidence_blocks",
        ["source_content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_candidate_artifact",
        "catalogue_evidence_blocks",
        ["candidate_id", "source_artifact_id", "block_index"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_blocks_content_hash",
        "catalogue_evidence_blocks",
        ["source_content_hash", "block_hash"],
        unique=False,
    )

    op.create_table(
        "catalogue_evidence_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("route_key", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_block_id", sa.Uuid(), nullable=False),
        sa.Column("coverage_cell_id", sa.Uuid(), nullable=True),
        sa.Column("scope_node_id", sa.Uuid(), nullable=True),
        sa.Column(
            "objective",
            sa.Enum(
                *_OBJECTIVES,
                name="catalogue_evidence_route_objective",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("relevance_reasons", sa.JSON(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("router_version", sa.String(length=100), nullable=False),
        sa.Column("coverage_input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_block_id"], ["catalogue_evidence_blocks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["coverage_cell_id"], ["catalogue_coverage_cells.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["scope_node_id"], ["catalogue_scope_nodes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_key", name="uq_catalogue_evidence_route_key"),
    )
    for column in (
        "route_key",
        "candidate_id",
        "evidence_block_id",
        "coverage_cell_id",
        "scope_node_id",
        "objective",
        "selected",
        "coverage_input_fingerprint",
    ):
        op.create_index(
            f"ix_catalogue_evidence_routes_{column}",
            "catalogue_evidence_routes",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_catalogue_evidence_routes_candidate_selected",
        "catalogue_evidence_routes",
        ["candidate_id", "selected", "objective"],
        unique=False,
    )
    op.create_index(
        "ix_catalogue_evidence_routes_block_scope",
        "catalogue_evidence_routes",
        ["evidence_block_id", "scope_node_id", "objective"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_evidence_routes_block_scope", table_name="catalogue_evidence_routes"
    )
    op.drop_index(
        "ix_catalogue_evidence_routes_candidate_selected", table_name="catalogue_evidence_routes"
    )
    for column in reversed(
        (
            "route_key",
            "candidate_id",
            "evidence_block_id",
            "coverage_cell_id",
            "scope_node_id",
            "objective",
            "selected",
            "coverage_input_fingerprint",
        )
    ):
        op.drop_index(
            f"ix_catalogue_evidence_routes_{column}",
            table_name="catalogue_evidence_routes",
        )
    op.drop_table("catalogue_evidence_routes")

    op.drop_index(
        "ix_catalogue_evidence_blocks_content_hash", table_name="catalogue_evidence_blocks"
    )
    op.drop_index(
        "ix_catalogue_evidence_blocks_candidate_artifact", table_name="catalogue_evidence_blocks"
    )
    for column in reversed(
        (
            "candidate_id",
            "source_id",
            "source_artifact_id",
            "block_key",
            "block_hash",
            "source_content_hash",
        )
    ):
        op.drop_index(
            f"ix_catalogue_evidence_blocks_{column}",
            table_name="catalogue_evidence_blocks",
        )
    op.drop_table("catalogue_evidence_blocks")
