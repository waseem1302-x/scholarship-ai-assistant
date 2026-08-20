"""Add the durable catalogue discovery foundation.

Revision ID: 20260820_0041
Revises: 20260817_0040
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260820_0041"
down_revision = "20260817_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _timestamp(*, nullable: bool = False) -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "catalogue_discovery_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("target_identity_snapshot", sa.JSON(), nullable=False),
        sa.Column("objective_kind", sa.String(length=64), nullable=False),
        sa.Column("objective_scope", sa.JSON(), nullable=False),
        sa.Column("objective_field_paths", sa.JSON(), nullable=False),
        sa.Column("objective_reason_codes", sa.JSON(), nullable=False),
        sa.Column("objective_criticality_tier", sa.Integer(), nullable=False),
        sa.Column("objective_priority_snapshot", sa.JSON(), nullable=False),
        sa.Column("planner_version", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            _enum(
                "catalogue_discovery_run_status",
                "pending",
                "running",
                "completed",
                "partial",
                "budget_exhausted",
                "capability_unavailable",
                "failed",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_queries", sa.Integer(), nullable=False),
        sa.Column("max_provider_calls", sa.Integer(), nullable=False),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False),
        sa.Column("max_leads", sa.Integer(), nullable=False),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False),
        sa.Column("max_estimated_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("provider_calls_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_calls_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_reserved", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("estimated_cost_settled", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("raw_leads_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_leads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("promotions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("aggregate_summary", sa.JSON(), nullable=False, server_default="{}"),
        _timestamp(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("max_queries > 0", name="max_queries_positive"),
        sa.CheckConstraint("max_provider_calls >= 0", name="max_provider_calls_nonnegative"),
        sa.CheckConstraint("max_tool_calls >= 0", name="max_tool_calls_nonnegative"),
        sa.CheckConstraint("max_leads >= 0", name="max_leads_nonnegative"),
        sa.CheckConstraint("max_response_bytes > 0", name="max_response_bytes_positive"),
        sa.CheckConstraint("max_estimated_cost >= 0", name="max_cost_nonnegative"),
        sa.CheckConstraint("provider_calls_reserved >= 0", name="provider_reserved_nonnegative"),
        sa.CheckConstraint("provider_calls_completed >= 0", name="provider_completed_nonnegative"),
        sa.CheckConstraint("tool_calls_reserved >= 0", name="tool_reserved_nonnegative"),
        sa.CheckConstraint("tool_calls_completed >= 0", name="tool_completed_nonnegative"),
        sa.CheckConstraint("estimated_cost_reserved >= 0", name="cost_reserved_nonnegative"),
        sa.CheckConstraint("estimated_cost_settled >= 0", name="cost_settled_nonnegative"),
        sa.CheckConstraint("raw_leads_seen >= 0", name="raw_leads_seen_nonnegative"),
        sa.CheckConstraint("unique_leads >= 0", name="unique_leads_nonnegative"),
        sa.CheckConstraint("promotions >= 0", name="promotions_nonnegative"),
        sa.ForeignKeyConstraint(
            ["target_candidate_id"], ["catalogue_candidates.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalogue_discovery_runs_status_created",
        "catalogue_discovery_runs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_catalogue_discovery_runs_target_created",
        "catalogue_discovery_runs",
        ["target_candidate_id", "created_at"],
    )
    op.create_index(
        op.f("ix_catalogue_discovery_runs_objective_kind"),
        "catalogue_discovery_runs",
        ["objective_kind"],
    )
    op.create_index(
        op.f("ix_catalogue_discovery_runs_status"), "catalogue_discovery_runs", ["status"]
    )
    op.create_index(
        op.f("ix_catalogue_discovery_runs_target_candidate_id"),
        "catalogue_discovery_runs",
        ["target_candidate_id"],
    )

    op.create_table(
        "catalogue_discovery_queries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("query_text", sa.String(length=1000), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("query_kind", sa.String(length=64), nullable=False),
        sa.Column("allowed_domains", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("public_context", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "catalogue_discovery_query_status",
                "planned",
                "claimed",
                "calling_provider",
                "response_received",
                "leads_recorded",
                "completed",
                "provider_rate_limited",
                "provider_failed",
                "tool_not_executed",
                "response_invalid",
                "budget_exhausted",
                "capability_unavailable",
                "cancelled",
            ),
            nullable=False,
            server_default="planned",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        _timestamp(),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        sa.CheckConstraint("provider_call_count >= 0", name="provider_calls_nonnegative"),
        sa.CheckConstraint("tool_call_count >= 0", name="tool_calls_nonnegative"),
        sa.CheckConstraint("response_bytes >= 0", name="response_bytes_nonnegative"),
        sa.CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        sa.CheckConstraint("estimated_cost >= 0", name="estimated_cost_nonnegative"),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_discovery_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_catalogue_discovery_query_ordinal"),
        sa.UniqueConstraint("run_id", "query_hash", name="uq_catalogue_discovery_query_hash"),
    )
    op.create_index(
        "ix_catalogue_discovery_queries_claim",
        "catalogue_discovery_queries",
        ["status", "next_attempt_at", "claimed_until", "ordinal"],
    )
    for column in ("run_id", "status", "next_attempt_at", "claimed_until"):
        op.create_index(
            op.f(f"ix_catalogue_discovery_queries_{column}"),
            "catalogue_discovery_queries",
            [column],
        )

    op.create_table(
        "catalogue_discovery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "catalogue_discovery_attempt_status",
                "in_progress",
                "succeeded",
                "rate_limited",
                "timeout",
                "provider_failed",
                "response_invalid",
                "tool_not_executed",
                "capability_unavailable",
                "budget_rejected",
                "abandoned",
            ),
            nullable=False,
        ),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("reserved_tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("provider_response_id", sa.String(length=255), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("web_search_executed", sa.Boolean(), nullable=True),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_url_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_model_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("estimated_tool_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("estimated_total_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        sa.CheckConstraint("reserved_tool_calls >= 0", name="reserved_tool_calls_nonnegative"),
        sa.CheckConstraint("reserved_estimated_cost >= 0", name="reserved_cost_nonnegative"),
        sa.CheckConstraint("tool_call_count >= 0", name="attempt_tool_calls_nonnegative"),
        sa.CheckConstraint("result_url_count >= 0", name="result_urls_nonnegative"),
        sa.CheckConstraint("response_bytes >= 0", name="attempt_response_bytes_nonnegative"),
        sa.CheckConstraint("estimated_model_cost >= 0", name="model_cost_nonnegative"),
        sa.CheckConstraint("estimated_tool_cost >= 0", name="tool_cost_nonnegative"),
        sa.CheckConstraint("estimated_total_cost >= 0", name="total_cost_nonnegative"),
        sa.CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="http_status_valid",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="input_tokens_nonnegative"
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="output_tokens_nonnegative"
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="attempt_latency_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["catalogue_discovery_queries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "query_id", "attempt_number", name="uq_catalogue_discovery_attempt_number"
        ),
    )
    op.create_index(
        "ix_catalogue_discovery_attempts_status_started",
        "catalogue_discovery_attempts",
        ["status", "started_at"],
    )
    op.create_index(
        op.f("ix_catalogue_discovery_attempts_query_id"),
        "catalogue_discovery_attempts",
        ["query_id"],
    )
    op.create_index(
        op.f("ix_catalogue_discovery_attempts_status"),
        "catalogue_discovery_attempts",
        ["status"],
    )

    op.create_table(
        "catalogue_discovery_leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("url_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _timestamp(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url_fingerprint", name="uq_catalogue_discovery_lead_fingerprint"),
        sa.UniqueConstraint("normalized_url", name="uq_catalogue_discovery_lead_url"),
    )
    op.create_index(
        "ix_catalogue_discovery_leads_host_active",
        "catalogue_discovery_leads",
        ["host", "active"],
    )
    op.create_index(
        op.f("ix_catalogue_discovery_leads_host"), "catalogue_discovery_leads", ["host"]
    )

    with op.batch_alter_table("catalogue_candidate_sources") as batch_op:
        batch_op.add_column(sa.Column("discovery_lead_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_candidate_sources_discovery_lead",
            "catalogue_discovery_leads",
            ["discovery_lead_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_catalogue_candidate_source_discovery_lead",
            ["candidate_id", "discovery_lead_id"],
        )
        batch_op.create_index(
            op.f("ix_catalogue_candidate_sources_discovery_lead_id"),
            ["discovery_lead_id"],
        )

    op.create_table(
        "catalogue_discovery_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("provider_rank", sa.Integer(), nullable=True),
        sa.Column("provider_source_type", sa.String(length=64), nullable=True),
        sa.Column("minimal_title", sa.String(length=500), nullable=True),
        sa.Column("discovery_reason", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_rank IS NULL OR provider_rank > 0", name="provider_rank_positive"
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["catalogue_discovery_queries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["catalogue_discovery_leads.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "query_id", "lead_id", name="uq_catalogue_discovery_observation_query_lead"
        ),
    )
    for column in ("query_id", "lead_id"):
        op.create_index(
            op.f(f"ix_catalogue_discovery_observations_{column}"),
            "catalogue_discovery_observations",
            [column],
        )

    op.create_table(
        "catalogue_discovery_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_context_hash", sa.String(length=64), nullable=False),
        sa.Column("context_type", sa.String(length=64), nullable=False),
        sa.Column("context_scholarship_id", sa.Uuid(), nullable=True),
        sa.Column("context_provider_id", sa.Uuid(), nullable=True),
        sa.Column("context_institution_id", sa.Uuid(), nullable=True),
        sa.Column("context_cycle_id", sa.Uuid(), nullable=True),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_domain", sa.String(length=255), nullable=True),
        sa.Column(
            "officiality_status",
            _enum(
                "catalogue_discovery_officiality_status",
                "official",
                "supporting_official",
                "third_party",
                "unresolved",
                "rejected_url_policy",
            ),
            nullable=False,
        ),
        sa.Column("trust_tier", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("reason_detail", sa.String(length=500), nullable=False),
        sa.Column("classifier_version", sa.String(length=100), nullable=False),
        sa.Column("supersedes_assessment_id", sa.Uuid(), nullable=True),
        _timestamp(),
        sa.CheckConstraint(
            "trust_tier IS NULL OR (trust_tier >= 1 AND trust_tier <= 4)",
            name="trust_tier_valid",
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["catalogue_discovery_leads.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_discovery_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["context_scholarship_id"], ["opportunities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["context_provider_id"], ["providers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["context_institution_id"], ["institutions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["context_cycle_id"], ["opportunity_cycles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_assessment_id"],
            ["catalogue_discovery_assessments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lead_id",
            "assessment_context_hash",
            "classifier_version",
            name="uq_catalogue_discovery_assessment_context",
        ),
    )
    for column in (
        "lead_id",
        "run_id",
        "context_scholarship_id",
        "context_provider_id",
        "context_institution_id",
        "context_cycle_id",
        "officiality_status",
        "supersedes_assessment_id",
    ):
        op.create_index(
            op.f(f"ix_catalogue_discovery_assessments_{column}"),
            "catalogue_discovery_assessments",
            [column],
        )
    op.create_index(
        "ix_catalogue_discovery_assessments_run_created",
        "catalogue_discovery_assessments",
        ["run_id", "created_at"],
    )

    op.create_table(
        "catalogue_discovery_promotions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_source_id", sa.Uuid(), nullable=True),
        sa.Column("promotion_kind", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        _timestamp(),
        sa.ForeignKeyConstraint(["run_id"], ["catalogue_discovery_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lead_id"], ["catalogue_discovery_leads.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["catalogue_discovery_assessments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["catalogue_candidates.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["candidate_source_id"], ["catalogue_candidate_sources.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "lead_id", name="uq_catalogue_discovery_promotion_candidate_lead"
        ),
    )
    for column in ("run_id", "lead_id", "assessment_id", "candidate_id", "candidate_source_id"):
        op.create_index(
            op.f(f"ix_catalogue_discovery_promotions_{column}"),
            "catalogue_discovery_promotions",
            [column],
        )
    op.create_index(
        "ix_catalogue_discovery_promotions_run_created",
        "catalogue_discovery_promotions",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_catalogue_discovery_promotions_run_created",
        table_name="catalogue_discovery_promotions",
    )
    for column in reversed(
        ("run_id", "lead_id", "assessment_id", "candidate_id", "candidate_source_id")
    ):
        op.drop_index(
            op.f(f"ix_catalogue_discovery_promotions_{column}"),
            table_name="catalogue_discovery_promotions",
        )
    op.drop_table("catalogue_discovery_promotions")

    op.drop_index(
        "ix_catalogue_discovery_assessments_run_created",
        table_name="catalogue_discovery_assessments",
    )
    for column in reversed(
        (
            "lead_id",
            "run_id",
            "context_scholarship_id",
            "context_provider_id",
            "context_institution_id",
            "context_cycle_id",
            "officiality_status",
            "supersedes_assessment_id",
        )
    ):
        op.drop_index(
            op.f(f"ix_catalogue_discovery_assessments_{column}"),
            table_name="catalogue_discovery_assessments",
        )
    op.drop_table("catalogue_discovery_assessments")

    for column in reversed(("query_id", "lead_id")):
        op.drop_index(
            op.f(f"ix_catalogue_discovery_observations_{column}"),
            table_name="catalogue_discovery_observations",
        )
    op.drop_table("catalogue_discovery_observations")

    with op.batch_alter_table("catalogue_candidate_sources") as batch_op:
        batch_op.drop_index(op.f("ix_catalogue_candidate_sources_discovery_lead_id"))
        batch_op.drop_constraint("uq_catalogue_candidate_source_discovery_lead", type_="unique")
        batch_op.drop_constraint(
            "fk_candidate_sources_discovery_lead",
            type_="foreignkey",
        )
        batch_op.drop_column("discovery_lead_id")

    op.drop_index(op.f("ix_catalogue_discovery_leads_host"), table_name="catalogue_discovery_leads")
    op.drop_index(
        "ix_catalogue_discovery_leads_host_active", table_name="catalogue_discovery_leads"
    )
    op.drop_table("catalogue_discovery_leads")

    op.drop_index(
        op.f("ix_catalogue_discovery_attempts_status"),
        table_name="catalogue_discovery_attempts",
    )
    op.drop_index(
        op.f("ix_catalogue_discovery_attempts_query_id"),
        table_name="catalogue_discovery_attempts",
    )
    op.drop_index(
        "ix_catalogue_discovery_attempts_status_started",
        table_name="catalogue_discovery_attempts",
    )
    op.drop_table("catalogue_discovery_attempts")

    for column in reversed(("run_id", "status", "next_attempt_at", "claimed_until")):
        op.drop_index(
            op.f(f"ix_catalogue_discovery_queries_{column}"),
            table_name="catalogue_discovery_queries",
        )
    op.drop_index("ix_catalogue_discovery_queries_claim", table_name="catalogue_discovery_queries")
    op.drop_table("catalogue_discovery_queries")

    op.drop_index(
        op.f("ix_catalogue_discovery_runs_target_candidate_id"),
        table_name="catalogue_discovery_runs",
    )
    op.drop_index(op.f("ix_catalogue_discovery_runs_status"), table_name="catalogue_discovery_runs")
    op.drop_index(
        op.f("ix_catalogue_discovery_runs_objective_kind"),
        table_name="catalogue_discovery_runs",
    )
    op.drop_index(
        "ix_catalogue_discovery_runs_target_created", table_name="catalogue_discovery_runs"
    )
    op.drop_index(
        "ix_catalogue_discovery_runs_status_created", table_name="catalogue_discovery_runs"
    )
    op.drop_table("catalogue_discovery_runs")
