"""Add durable Phase 4 match evaluation records.

Revision ID: 20260812_0008
Revises: 20260812_0007
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0008"
down_revision: str | None = "20260812_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("supersedes_evaluation_id", sa.Uuid(), nullable=True),
        sa.Column("matcher_version", sa.String(length=100), nullable=False),
        sa.Column(
            "evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("profile_snapshot_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["student_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["supersedes_evaluation_id"], ["match_evaluations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_evaluations_user_id", "match_evaluations", ["user_id"])
    op.create_index("ix_match_evaluations_profile_id", "match_evaluations", ["profile_id"])
    op.create_index(
        "ix_match_evaluations_supersedes_evaluation_id",
        "match_evaluations",
        ["supersedes_evaluation_id"],
    )
    op.create_index(
        "ix_match_evaluations_profile_snapshot_hash",
        "match_evaluations",
        ["profile_snapshot_hash"],
    )
    op.create_index("ix_match_evaluations_expires_at", "match_evaluations", ["expires_at"])
    op.create_index(
        "ix_match_evaluations_user_evaluated", "match_evaluations", ["user_id", "evaluated_at"]
    )

    op.create_table(
        "match_evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("opportunity_cycle_id", sa.Uuid(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_excerpt_id", sa.Uuid(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=True),
        sa.Column("score_label", sa.String(length=50), nullable=False),
        sa.Column("eligibility_status", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("evidence_completeness", sa.Integer(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("opportunity_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "match_score >= 0", name="ck_match_evaluation_results_score_non_negative"
        ),
        sa.CheckConstraint(
            "evidence_completeness BETWEEN 0 AND 100",
            name="ck_match_evaluation_results_completeness_range",
        ),
        sa.ForeignKeyConstraint(["evaluation_id"], ["match_evaluations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["opportunity_cycle_id"], ["opportunity_cycles.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_excerpt_id"], ["source_excerpts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_evaluation_results_evaluation_id",
        "match_evaluation_results",
        ["evaluation_id"],
    )
    op.create_index(
        "ix_match_evaluation_results_opportunity_id",
        "match_evaluation_results",
        ["opportunity_id"],
    )
    op.create_index(
        "ix_match_evaluation_results_evaluation_rank",
        "match_evaluation_results",
        ["evaluation_id", "rank"],
    )

    op.create_table(
        "match_rule_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_result_id", sa.Uuid(), nullable=False),
        sa.Column("eligibility_rule_id", sa.Uuid(), nullable=True),
        sa.Column("rule_name", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("profile_fields_json", sa.JSON(), nullable=False),
        sa.Column("comparison_json", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("next_actions_json", sa.JSON(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("source_excerpt_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('satisfied', 'failed', 'unknown')",
            name="ck_match_rule_outcomes_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["eligibility_rule_id"], ["eligibility_rules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_result_id"], ["match_evaluation_results.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_excerpt_id"], ["source_excerpts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_match_rule_outcomes_evaluation_result_id",
        "match_rule_outcomes",
        ["evaluation_result_id"],
    )
    op.create_index(
        "ix_match_rule_outcomes_result", "match_rule_outcomes", ["evaluation_result_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_match_rule_outcomes_result", table_name="match_rule_outcomes")
    op.drop_index("ix_match_rule_outcomes_evaluation_result_id", table_name="match_rule_outcomes")
    op.drop_table("match_rule_outcomes")
    op.drop_index(
        "ix_match_evaluation_results_evaluation_rank", table_name="match_evaluation_results"
    )
    op.drop_index(
        "ix_match_evaluation_results_opportunity_id", table_name="match_evaluation_results"
    )
    op.drop_index(
        "ix_match_evaluation_results_evaluation_id", table_name="match_evaluation_results"
    )
    op.drop_table("match_evaluation_results")
    op.drop_index("ix_match_evaluations_user_evaluated", table_name="match_evaluations")
    op.drop_index("ix_match_evaluations_expires_at", table_name="match_evaluations")
    op.drop_index("ix_match_evaluations_profile_snapshot_hash", table_name="match_evaluations")
    op.drop_index(
        "ix_match_evaluations_supersedes_evaluation_id", table_name="match_evaluations"
    )
    op.drop_index("ix_match_evaluations_profile_id", table_name="match_evaluations")
    op.drop_index("ix_match_evaluations_user_id", table_name="match_evaluations")
    op.drop_table("match_evaluations")
