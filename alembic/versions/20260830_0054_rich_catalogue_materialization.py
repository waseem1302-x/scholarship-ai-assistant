"""add scholarship-scoped programmes, events, resources, and claim provenance links

Revision ID: 20260830_0054
Revises: 20260830_0053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0054"
down_revision: str | None = "20260830_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "scholarship_programmes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("programme_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("programme_type", sa.String(length=100), nullable=True),
        sa.Column("degree_levels", sa.JSON(), nullable=False),
        sa.Column("fields_of_study", sa.JSON(), nullable=False),
        sa.Column("duration", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("application_route_keys", sa.JSON(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["scholarship_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["opportunity_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["application_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_key", name="uq_scholarship_programmes_identity"),
    )
    for column in ("scholarship_id", "cycle_id", "track_id", "institution_id", "identity_key", "programme_key", "programme_type"):
        op.create_index(op.f(f"ix_scholarship_programmes_{column}"), "scholarship_programmes", [column], unique=False)
    op.create_index("ix_scholarship_programmes_scope", "scholarship_programmes", ["scholarship_id", "cycle_id", "programme_key"], unique=False)

    op.create_table(
        "opportunity_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("programme_id", sa.Uuid(), nullable=True),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_text", sa.String(length=500), nullable=True),
        sa.Column("precision", sa.String(length=32), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["scholarship_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["opportunity_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["application_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["scholarship_programmes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_key", name="uq_opportunity_events_identity"),
    )
    for column in ("scholarship_id", "cycle_id", "track_id", "institution_id", "programme_id", "identity_key", "event_key", "event_type"):
        op.create_index(op.f(f"ix_opportunity_events_{column}"), "opportunity_events", [column], unique=False)
    op.create_index("ix_opportunity_events_scope", "opportunity_events", ["scholarship_id", "cycle_id", "event_type"], unique=False)

    op.create_table(
        "opportunity_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scholarship_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("programme_id", sa.Uuid(), nullable=True),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("resource_key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["scholarship_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["opportunity_cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["application_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["scholarship_programmes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_key", name="uq_opportunity_resources_identity"),
    )
    for column in ("scholarship_id", "cycle_id", "track_id", "institution_id", "programme_id", "identity_key", "resource_key", "resource_type"):
        op.create_index(op.f(f"ix_opportunity_resources_{column}"), "opportunity_resources", [column], unique=False)
    op.create_index("ix_opportunity_resources_scope", "opportunity_resources", ["scholarship_id", "cycle_id", "resource_type"], unique=False)

    op.create_table(
        "catalogue_materialized_claim_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_hash", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=False),
        sa.Column("field_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["catalogue_candidate_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_evidence_id"], ["field_evidence.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_hash", "claim_id", "entity_id", "field_path", name="uq_catalogue_materialized_claim_link_identity"),
    )
    for column in ("candidate_id", "review_id", "proposal_hash", "claim_id", "entity_type", "entity_id", "field_evidence_id"):
        op.create_index(op.f(f"ix_catalogue_materialized_claim_links_{column}"), "catalogue_materialized_claim_links", [column], unique=False)
    op.create_index("ix_catalogue_materialized_claim_links_candidate", "catalogue_materialized_claim_links", ["candidate_id", "proposal_hash"], unique=False)
    op.create_index("ix_catalogue_materialized_claim_links_entity", "catalogue_materialized_claim_links", ["entity_type", "entity_id"], unique=False)


def downgrade() -> None:
    op.drop_table("catalogue_materialized_claim_links")
    op.drop_table("opportunity_resources")
    op.drop_table("opportunity_events")
    op.drop_table("scholarship_programmes")
