"""Durable, owner-scoped records of deterministic match evaluations."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, utc_now


class MatchEvaluation(Base):
    """A privacy-limited point-in-time record of one user's match run.

    The profile snapshot contains only matching inputs. It is retained for a limited
    period so results can be explained after a profile, source, or policy change.
    """

    __tablename__ = "match_evaluations"
    __table_args__ = (
        Index("ix_match_evaluations_user_evaluated", "user_id", "evaluated_at"),
        Index("ix_match_evaluations_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="SET NULL"), index=True
    )
    supersedes_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("match_evaluations.id", ondelete="SET NULL"), index=True
    )
    matcher_version: Mapped[str] = mapped_column(String(100))
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    profile_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    profile_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)

    user: Mapped[User] = relationship()
    results: Mapped[list["MatchEvaluationResult"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class MatchEvaluationResult(Base):
    """One opportunity's frozen result within a match evaluation."""

    __tablename__ = "match_evaluation_results"
    __table_args__ = (
        CheckConstraint(
            "match_score >= 0",
            name="ck_match_evaluation_results_score_non_negative",
        ),
        CheckConstraint(
            "evidence_completeness BETWEEN 0 AND 100",
            name="ck_match_evaluation_results_completeness_range",
        ),
        Index(
            "ix_match_evaluation_results_evaluation_rank",
            "evaluation_id",
            "rank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("match_evaluations.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )
    opportunity_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_cycles.id", ondelete="SET NULL")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    source_excerpt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_excerpts.id", ondelete="SET NULL")
    )
    rank: Mapped[int] = mapped_column(Integer)
    match_score: Mapped[int] = mapped_column(Integer)
    fit_score: Mapped[int | None] = mapped_column(Integer)
    score_label: Mapped[str] = mapped_column(String(50))
    eligibility_status: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[str] = mapped_column(String(20))
    evidence_completeness: Mapped[int] = mapped_column(Integer)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    opportunity_snapshot_json: Mapped[dict[str, object]] = mapped_column(JSON)
    source_snapshot_json: Mapped[dict[str, object] | None] = mapped_column(JSON)

    evaluation: Mapped[MatchEvaluation] = relationship(back_populates="results")
    rule_outcomes: Mapped[list["MatchRuleOutcome"]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )


class MatchRuleOutcome(Base):
    """A machine-readable outcome for every rule considered in a result."""

    __tablename__ = "match_rule_outcomes"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('satisfied', 'failed', 'unknown')",
            name="ck_match_rule_outcomes_outcome",
        ),
        Index("ix_match_rule_outcomes_result", "evaluation_result_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evaluation_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("match_evaluation_results.id", ondelete="CASCADE"),
        index=True,
    )
    eligibility_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("eligibility_rules.id", ondelete="SET NULL")
    )
    rule_name: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(100))
    profile_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    comparison_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20))
    next_actions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    source_excerpt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_excerpts.id", ondelete="SET NULL")
    )

    result: Mapped[MatchEvaluationResult] = relationship(back_populates="rule_outcomes")
