"""add generic catalogue topology and scoped coverage

Revision ID: 20260830_0047
Revises: 20260830_0046
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260830_0047"
down_revision: str | None = "20260830_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "catalogue_scope_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "node_type",
            _enum(
                "catalogue_scope_node_type",
                "scholarship_family",
                "cycle",
                "country",
                "institution",
                "route",
                "programme",
                "degree_level",
                "subject",
                "award_variant",
                "application_channel",
            ),
            nullable=False,
        ),
        sa.Column("canonical_key", sa.String(length=255), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column("lifecycle_key", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column(
            "discovery_confidence",
            _enum(
                "catalogue_scope_discovery_confidence",
                "asserted",
                "high",
                "medium",
                "compatibility",
                "unresolved",
            ),
            nullable=False,
        ),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("expected_child_counts", sa.JSON(), nullable=False),
        sa.Column("expectation_provenance", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["catalogue_candidate_sources.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "node_type",
            "canonical_key",
            "lifecycle_key",
            name="uq_catalogue_scope_node_identity",
        ),
    )
    for column in ("candidate_id", "node_type", "source_id", "source_artifact_id"):
        op.create_index(op.f(f"ix_catalogue_scope_nodes_{column}"), "catalogue_scope_nodes", [column])
    op.create_index(
        "ix_catalogue_scope_nodes_candidate_type",
        "catalogue_scope_nodes",
        ["candidate_id", "node_type", "canonical_key"],
    )

    op.create_table(
        "catalogue_scope_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("parent_node_id", sa.Uuid(), nullable=False),
        sa.Column("child_node_id", sa.Uuid(), nullable=False),
        sa.Column(
            "relationship_type",
            _enum(
                "catalogue_scope_edge_type",
                "contains",
                "parent_child",
                "applies_to",
                "inherits_to",
            ),
            nullable=False,
        ),
        sa.Column("objective_keys", sa.JSON(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("evidence_start", sa.Integer(), nullable=True),
        sa.Column("evidence_end", sa.Integer(), nullable=True),
        sa.Column(
            "confidence",
            _enum(
                "catalogue_scope_edge_confidence",
                "asserted",
                "high",
                "medium",
                "compatibility",
                "unresolved",
            ),
            nullable=False,
        ),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("parent_node_id != child_node_id", name="ck_catalogue_scope_edges_not_self"),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_node_id"], ["catalogue_scope_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["child_node_id"], ["catalogue_scope_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "parent_node_id",
            "child_node_id",
            "relationship_type",
            name="uq_catalogue_scope_edge_identity",
        ),
    )
    for column in (
        "candidate_id",
        "parent_node_id",
        "child_node_id",
        "relationship_type",
        "source_artifact_id",
    ):
        op.create_index(op.f(f"ix_catalogue_scope_edges_{column}"), "catalogue_scope_edges", [column])
    op.create_index(
        "ix_catalogue_scope_edges_candidate_relationship",
        "catalogue_scope_edges",
        ["candidate_id", "relationship_type"],
    )

    op.create_table(
        "catalogue_source_scope_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("scope_node_id", sa.Uuid(), nullable=False),
        sa.Column(
            "relationship_type",
            _enum(
                "catalogue_source_scope_relationship",
                "authoritative_for",
                "supports",
                "enumerates",
                "applies_to",
            ),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            _enum(
                "catalogue_source_scope_confidence",
                "asserted",
                "high",
                "medium",
                "compatibility",
                "unresolved",
            ),
            nullable=False,
        ),
        sa.Column("applicability_is_explicit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("evidence_start", sa.Integer(), nullable=True),
        sa.Column("evidence_end", sa.Integer(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["catalogue_candidate_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["catalogue_source_artifacts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["scope_node_id"], ["catalogue_scope_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "scope_node_id",
            "relationship_type",
            "source_artifact_id",
            name="uq_catalogue_source_scope_link_identity",
        ),
    )
    for column in (
        "candidate_id",
        "source_id",
        "source_artifact_id",
        "scope_node_id",
        "relationship_type",
    ):
        op.create_index(
            op.f(f"ix_catalogue_source_scope_links_{column}"),
            "catalogue_source_scope_links",
            [column],
        )
    op.create_index(
        "ix_catalogue_source_scope_links_candidate_scope",
        "catalogue_source_scope_links",
        ["candidate_id", "scope_node_id"],
    )

    op.create_table(
        "catalogue_coverage_cells",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "objective",
            _enum(
                "catalogue_coverage_objective",
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
            ),
            nullable=False,
        ),
        sa.Column("scope_node_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            _enum(
                "catalogue_scoped_coverage_state",
                "unknown",
                "not_yet_acquired",
                "blocked",
                "not_stated",
                "not_applicable",
                "partial",
                "complete",
                "conflicting",
                "quarantined",
                "failed",
            ),
            nullable=False,
        ),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supporting_claim_ids", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("expected_item_count", sa.Integer(), nullable=True),
        sa.Column("resolved_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("missing_frontier_reasons", sa.JSON(), nullable=False),
        sa.Column("evaluator_version", sa.String(length=100), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scope_node_id"], ["catalogue_scope_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "objective",
            "scope_node_id",
            name="uq_catalogue_coverage_cell_identity",
        ),
    )
    for column in ("candidate_id", "objective", "scope_node_id", "state", "input_fingerprint"):
        op.create_index(
            op.f(f"ix_catalogue_coverage_cells_{column}"),
            "catalogue_coverage_cells",
            [column],
        )
    op.create_index(
        "ix_catalogue_coverage_cells_candidate_state",
        "catalogue_coverage_cells",
        ["candidate_id", "state", "objective"],
    )


def downgrade() -> None:
    op.drop_table("catalogue_coverage_cells")
    op.drop_table("catalogue_source_scope_links")
    op.drop_table("catalogue_scope_edges")
    op.drop_table("catalogue_scope_nodes")
