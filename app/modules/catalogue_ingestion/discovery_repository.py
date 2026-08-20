"""Transactional persistence and state transitions for catalogue discovery."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjective,
    DiscoveryPrioritySnapshot,
    DiscoveryQueryPlan,
    discovery_query_hash,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryAttempt,
    CatalogueDiscoveryLead,
    CatalogueDiscoveryObservation,
    CatalogueDiscoveryPromotion,
    CatalogueDiscoveryQuery,
    CatalogueDiscoveryRun,
    DiscoveryAttemptStatus,
    DiscoveryOfficialityStatus,
    DiscoveryQueryStatus,
    DiscoveryRunStatus,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
)
from app.modules.catalogue_ingestion.url_policy import (
    URLRejectionCode,
    normalize_discovery_lead_url,
)

RETRYABLE_QUERY_STATUSES = {
    DiscoveryQueryStatus.PROVIDER_RATE_LIMITED,
    DiscoveryQueryStatus.PROVIDER_FAILED,
}


class DiscoveryStateError(RuntimeError):
    pass


class DiscoveryBudgetExhausted(DiscoveryStateError):
    def __init__(self, attempt_id: uuid.UUID) -> None:
        super().__init__("catalogue_discovery_budget_exhausted")
        self.attempt_id = attempt_id


class DiscoveryURLRejected(DiscoveryStateError):
    def __init__(self, code: URLRejectionCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class DiscoveryRunLimits:
    max_queries: int
    max_provider_calls: int
    max_tool_calls: int
    max_leads: int
    max_response_bytes: int
    max_estimated_cost: Decimal

    def __post_init__(self) -> None:
        if self.max_queries < 1:
            raise ValueError("max_queries must be positive")
        if min(self.max_provider_calls, self.max_tool_calls, self.max_leads) < 0:
            raise ValueError("discovery count limits cannot be negative")
        if self.max_response_bytes < 1 or self.max_estimated_cost < 0:
            raise ValueError("discovery byte/cost limits are invalid")


@dataclass(frozen=True)
class DiscoveryAttemptOutcome:
    status: DiscoveryAttemptStatus
    provider_response_id: str | None = None
    http_status: int | None = None
    web_search_executed: bool | None = None
    tool_call_count: int = 0
    result_url_count: int = 0
    response_bytes: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_model_cost: Decimal = Decimal("0")
    estimated_tool_cost: Decimal = Decimal("0")
    latency_ms: int | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status in {
            DiscoveryAttemptStatus.IN_PROGRESS,
            DiscoveryAttemptStatus.BUDGET_REJECTED,
        }:
            raise ValueError("outcome must be a provider-attempt terminal state")
        numeric = (
            self.tool_call_count,
            self.result_url_count,
            self.response_bytes,
            self.estimated_model_cost,
            self.estimated_tool_cost,
        )
        if any(value < 0 for value in numeric):
            raise ValueError("attempt outcome counters and costs cannot be negative")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("attempt latency cannot be negative")
        if self.http_status is not None and not 100 <= self.http_status <= 599:
            raise ValueError("attempt HTTP status is invalid")
        if self.input_tokens is not None and self.input_tokens < 0:
            raise ValueError("attempt input tokens cannot be negative")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise ValueError("attempt output tokens cannot be negative")
        if self.provider_response_id is not None and len(self.provider_response_id) > 255:
            raise ValueError("provider response ID exceeds the persistence limit")
        if self.error_code is not None and len(self.error_code) > 100:
            raise ValueError("attempt error code exceeds the persistence limit")

    @property
    def estimated_total_cost(self) -> Decimal:
        return self.estimated_model_cost + self.estimated_tool_cost


@dataclass(frozen=True)
class DiscoveryAssessmentInput:
    assessment_context_hash: str
    context_type: str
    officiality_status: DiscoveryOfficialityStatus
    owner_type: str
    reason_code: str
    reason_detail: str
    classifier_version: str
    context_scholarship_id: uuid.UUID | None = None
    context_provider_id: uuid.UUID | None = None
    context_institution_id: uuid.UUID | None = None
    context_cycle_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    canonical_domain: str | None = None
    trust_tier: int | None = None
    supersedes_assessment_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if len(self.assessment_context_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.assessment_context_hash
        ):
            raise ValueError("assessment_context_hash must be a SHA-256 hex digest")
        bounded = {
            "context_type": (self.context_type, 64),
            "owner_type": (self.owner_type, 32),
            "reason_code": (self.reason_code, 100),
            "reason_detail": (self.reason_detail, 500),
            "classifier_version": (self.classifier_version, 100),
        }
        if any(not value or len(value) > limit for value, limit in bounded.values()):
            raise ValueError("assessment text fields must be non-empty and bounded")
        if self.canonical_domain is not None and len(self.canonical_domain) > 255:
            raise ValueError("assessment canonical domain exceeds the persistence limit")
        if self.trust_tier is not None and not 1 <= self.trust_tier <= 4:
            raise ValueError("assessment trust tier must be between 1 and 4")


@dataclass(frozen=True)
class DiscoverySourceBindingOutcome:
    source: CatalogueCandidateSource
    created: bool
    candidate_resumed: bool


class CatalogueDiscoveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self,
        *,
        objective: DiscoveryObjective,
        priority: DiscoveryPrioritySnapshot,
        plans: tuple[DiscoveryQueryPlan, ...],
        provider: str,
        model: str,
        limits: DiscoveryRunLimits,
        dry_run: bool = True,
    ) -> CatalogueDiscoveryRun:
        if not plans or len(plans) > limits.max_queries:
            raise ValueError("query plan must be non-empty and within the run limit")
        if tuple(plan.ordinal for plan in plans) != tuple(range(len(plans))):
            raise ValueError("query ordinals must be contiguous and zero-based")
        expected_context = objective.public_context()
        for plan in plans:
            if plan.public_context != expected_context:
                raise ValueError("query plan public context does not match the objective")
            if plan.allowed_domains != objective.reviewed_domains:
                raise ValueError("query plan domains do not match the reviewed objective domains")
            if plan.query_text != " ".join(plan.query_text.split()):
                raise ValueError("query plan text must be whitespace-normalized")
            if plan.query_hash != discovery_query_hash(objective, plan.query_text):
                raise ValueError("query plan hash does not match its objective and query")
        if len({plan.query_hash for plan in plans}) != len(plans):
            raise ValueError("query plan hashes must be unique within a run")
        if priority.criticality_tier != objective.criticality_tier:
            raise ValueError("objective and priority criticality tiers must match")
        if not provider.strip() or len(provider) > 100:
            raise ValueError("discovery provider name must be non-empty and bounded")
        if not model.strip() or len(model) > 255:
            raise ValueError("discovery model name must be non-empty and bounded")

        run = CatalogueDiscoveryRun(
            target_candidate_id=objective.candidate_id,
            target_identity_snapshot=objective.identity_snapshot().model_dump(mode="json"),
            objective_kind=objective.objective_kind.value,
            objective_scope=objective.scope_snapshot().model_dump(mode="json"),
            objective_field_paths=list(objective.field_paths),
            objective_reason_codes=list(objective.reason_codes),
            objective_criticality_tier=objective.criticality_tier,
            objective_priority_snapshot=priority.model_dump(mode="json"),
            planner_version=objective.planner_version,
            provider=provider,
            model=model,
            dry_run=dry_run,
            max_queries=limits.max_queries,
            max_provider_calls=limits.max_provider_calls,
            max_tool_calls=limits.max_tool_calls,
            max_leads=limits.max_leads,
            max_response_bytes=limits.max_response_bytes,
            max_estimated_cost=limits.max_estimated_cost,
        )
        self.session.add(run)
        self.session.flush()
        self.session.add_all(
            [
                CatalogueDiscoveryQuery(
                    run_id=run.id,
                    ordinal=plan.ordinal,
                    query_text=plan.query_text,
                    query_hash=plan.query_hash,
                    query_kind=plan.query_kind,
                    allowed_domains=list(plan.allowed_domains),
                    public_context=plan.public_context.model_dump(mode="json"),
                )
                for plan in plans
            ]
        )
        self.session.commit()
        return run

    def get_query(self, query_id: uuid.UUID) -> CatalogueDiscoveryQuery | None:
        return self.session.get(CatalogueDiscoveryQuery, query_id)

    def get_attempt(self, attempt_id: uuid.UUID) -> CatalogueDiscoveryAttempt | None:
        return self.session.get(CatalogueDiscoveryAttempt, attempt_id)

    def get_latest_successful_attempt(
        self,
        query_id: uuid.UUID,
    ) -> CatalogueDiscoveryAttempt | None:
        return self.session.scalar(
            select(CatalogueDiscoveryAttempt)
            .where(
                CatalogueDiscoveryAttempt.query_id == query_id,
                CatalogueDiscoveryAttempt.status == DiscoveryAttemptStatus.SUCCEEDED,
            )
            .order_by(CatalogueDiscoveryAttempt.attempt_number.desc())
            .limit(1)
        )

    def claim_queries(
        self,
        *,
        run_id: uuid.UUID,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        max_attempts: int,
        now: datetime | None = None,
    ) -> list[CatalogueDiscoveryQuery]:
        if limit < 1 or lease_seconds < 1 or max_attempts < 1:
            raise ValueError("claim limits must be positive")
        observed_at = now or datetime.now(UTC)
        run = self.session.get(CatalogueDiscoveryRun, run_id)
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        if run.status not in {DiscoveryRunStatus.PENDING, DiscoveryRunStatus.RUNNING}:
            raise DiscoveryStateError("catalogue_discovery_run_is_terminal")
        statement = (
            select(CatalogueDiscoveryQuery)
            .where(
                CatalogueDiscoveryQuery.run_id == run_id,
                CatalogueDiscoveryQuery.status.in_(
                    {DiscoveryQueryStatus.PLANNED, DiscoveryQueryStatus.CLAIMED}
                ),
                CatalogueDiscoveryQuery.attempt_count < max_attempts,
                or_(
                    CatalogueDiscoveryQuery.next_attempt_at.is_(None),
                    CatalogueDiscoveryQuery.next_attempt_at <= observed_at,
                ),
                or_(
                    CatalogueDiscoveryQuery.claimed_until.is_(None),
                    CatalogueDiscoveryQuery.claimed_until < observed_at,
                ),
            )
            .order_by(CatalogueDiscoveryQuery.ordinal)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        queries = list(self.session.scalars(statement))
        claimed_until = observed_at + timedelta(seconds=lease_seconds)
        for query in queries:
            query.status = DiscoveryQueryStatus.CLAIMED
            query.claimed_by = worker_id
            query.claimed_until = claimed_until

        if queries and run.status is DiscoveryRunStatus.PENDING:
            run.status = DiscoveryRunStatus.RUNNING
            run.started_at = observed_at
        self.session.commit()
        return queries

    def reserve_attempt(
        self,
        *,
        query_id: uuid.UUID,
        worker_id: str,
        request_fingerprint: str,
        reserved_tool_calls: int,
        reserved_estimated_cost: Decimal,
        now: datetime | None = None,
    ) -> CatalogueDiscoveryAttempt:
        if reserved_tool_calls < 1 or reserved_estimated_cost < 0:
            raise ValueError("attempt reservation must be bounded and non-negative")
        if len(request_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in request_fingerprint
        ):
            raise ValueError("request_fingerprint must be a SHA-256 hex digest")
        observed_at = now or datetime.now(UTC)
        query = self._query_for_update(query_id)
        if (
            query.status is not DiscoveryQueryStatus.CLAIMED
            or query.claimed_by != worker_id
            or query.claimed_until is None
            or query.claimed_until < observed_at
        ):
            raise DiscoveryStateError("discovery_query_not_claimed_by_worker")
        run = self._run_for_update(query.run_id)
        if run.status not in {
            DiscoveryRunStatus.PENDING,
            DiscoveryRunStatus.RUNNING,
            DiscoveryRunStatus.BUDGET_EXHAUSTED,
        }:
            raise DiscoveryStateError("catalogue_discovery_run_is_terminal")
        attempt_number = query.attempt_count + 1
        would_exceed = (
            run.status is DiscoveryRunStatus.BUDGET_EXHAUSTED
            or run.provider_calls_completed + run.provider_calls_reserved + 1
            > run.max_provider_calls
            or run.tool_calls_completed + run.tool_calls_reserved + reserved_tool_calls
            > run.max_tool_calls
            or run.estimated_cost_settled + run.estimated_cost_reserved + reserved_estimated_cost
            > run.max_estimated_cost
        )
        if would_exceed:
            attempt = CatalogueDiscoveryAttempt(
                query_id=query.id,
                attempt_number=attempt_number,
                status=DiscoveryAttemptStatus.BUDGET_REJECTED,
                request_fingerprint=request_fingerprint,
                provider=run.provider,
                model=run.model,
                error_code="run_budget_exhausted",
                started_at=observed_at,
                completed_at=observed_at,
            )
            self.session.add(attempt)
            query.attempt_count = attempt_number
            query.status = DiscoveryQueryStatus.BUDGET_EXHAUSTED
            query.failure_code = "run_budget_exhausted"
            self._release_query(query)
            run.status = DiscoveryRunStatus.BUDGET_EXHAUSTED
            run.failure_code = "run_budget_exhausted"
            self.session.commit()
            raise DiscoveryBudgetExhausted(attempt.id)

        run.provider_calls_reserved += 1
        run.tool_calls_reserved += reserved_tool_calls
        run.estimated_cost_reserved += reserved_estimated_cost
        attempt = CatalogueDiscoveryAttempt(
            query_id=query.id,
            attempt_number=attempt_number,
            status=DiscoveryAttemptStatus.IN_PROGRESS,
            request_fingerprint=request_fingerprint,
            provider=run.provider,
            model=run.model,
            reserved_tool_calls=reserved_tool_calls,
            reserved_estimated_cost=reserved_estimated_cost,
            started_at=observed_at,
        )
        self.session.add(attempt)
        query.attempt_count = attempt_number
        query.status = DiscoveryQueryStatus.CALLING_PROVIDER
        self.session.commit()
        return attempt

    def settle_attempt(
        self,
        attempt_id: uuid.UUID,
        outcome: DiscoveryAttemptOutcome,
        *,
        now: datetime | None = None,
    ) -> CatalogueDiscoveryAttempt:
        observed_at = now or datetime.now(UTC)
        attempt = self.session.scalar(
            select(CatalogueDiscoveryAttempt)
            .where(CatalogueDiscoveryAttempt.id == attempt_id)
            .with_for_update()
        )
        if attempt is None:
            raise DiscoveryStateError("catalogue_discovery_attempt_not_found")
        if attempt.status is not DiscoveryAttemptStatus.IN_PROGRESS:
            raise DiscoveryStateError("discovery_attempt_already_terminal")
        query = self._query_for_update(attempt.query_id)
        run = self._run_for_update(query.run_id)
        self._settle_locked(attempt, query, run, outcome, observed_at=observed_at)
        self.session.commit()
        return attempt

    def abandon_expired_attempt(
        self,
        query_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> CatalogueDiscoveryAttempt:
        observed_at = now or datetime.now(UTC)
        query = self._query_for_update(query_id)
        if (
            query.status is not DiscoveryQueryStatus.CALLING_PROVIDER
            or query.claimed_until is None
            or query.claimed_until >= observed_at
        ):
            raise DiscoveryStateError("discovery_query_attempt_not_expired")
        attempt = self.session.scalar(
            select(CatalogueDiscoveryAttempt)
            .where(
                CatalogueDiscoveryAttempt.query_id == query.id,
                CatalogueDiscoveryAttempt.status == DiscoveryAttemptStatus.IN_PROGRESS,
            )
            .order_by(CatalogueDiscoveryAttempt.attempt_number.desc())
            .limit(1)
            .with_for_update()
        )
        if attempt is None:
            raise DiscoveryStateError("in_progress_discovery_attempt_not_found")
        run = self._run_for_update(query.run_id)
        outcome = DiscoveryAttemptOutcome(
            status=DiscoveryAttemptStatus.ABANDONED,
            tool_call_count=attempt.reserved_tool_calls,
            estimated_tool_cost=attempt.reserved_estimated_cost,
            error_code="worker_lease_expired",
        )
        self._settle_locked(attempt, query, run, outcome, observed_at=observed_at)
        query.status = DiscoveryQueryStatus.PLANNED
        query.next_attempt_at = observed_at
        self.session.commit()
        return attempt

    def schedule_retry(
        self,
        query_id: uuid.UUID,
        *,
        next_attempt_at: datetime,
        max_attempts: int,
    ) -> CatalogueDiscoveryQuery:
        query = self._query_for_update(query_id)
        if query.status not in RETRYABLE_QUERY_STATUSES:
            raise DiscoveryStateError("discovery_query_status_not_retryable")
        if query.attempt_count >= max_attempts:
            raise DiscoveryStateError("discovery_query_attempt_limit_reached")
        query.status = DiscoveryQueryStatus.PLANNED
        query.next_attempt_at = next_attempt_at
        query.failure_code = None
        self._release_query(query)
        self.session.commit()
        return query

    def record_lead_observation(
        self,
        *,
        query_id: uuid.UUID,
        url: str,
        discovery_reason: str,
        provider_rank: int | None = None,
        provider_source_type: str | None = None,
        minimal_title: str | None = None,
        observed_at: datetime | None = None,
    ) -> tuple[CatalogueDiscoveryLead, CatalogueDiscoveryObservation]:
        normalization = normalize_discovery_lead_url(url)
        if normalization.normalized is None:
            assert normalization.rejection_code is not None
            raise DiscoveryURLRejected(normalization.rejection_code)
        normalized_url = normalization.normalized.value
        host = normalization.normalized.host
        if not discovery_reason or len(discovery_reason) > 255:
            raise ValueError("discovery reason must be non-empty and bounded")
        if provider_rank is not None and provider_rank < 1:
            raise ValueError("provider rank must be positive when supplied")
        if provider_source_type is not None and (
            not provider_source_type or len(provider_source_type) > 64
        ):
            raise ValueError("provider source type must be non-empty and bounded when supplied")
        if minimal_title is not None and len(minimal_title) > 500:
            raise ValueError("discovery title exceeds the persistence limit")
        timestamp = observed_at or datetime.now(UTC)
        fingerprint = hashlib.sha256(normalized_url.encode()).hexdigest()
        query = self._query_for_update(query_id)
        if query.status not in {
            DiscoveryQueryStatus.RESPONSE_RECEIVED,
            DiscoveryQueryStatus.LEADS_RECORDED,
        }:
            raise DiscoveryStateError("discovery_query_has_no_accepted_response")
        run = self._run_for_update(query.run_id)
        lead = self.session.scalar(
            select(CatalogueDiscoveryLead).where(
                CatalogueDiscoveryLead.url_fingerprint == fingerprint
            )
        )
        if lead is None:
            try:
                with self.session.begin_nested():
                    lead = CatalogueDiscoveryLead(
                        normalized_url=normalized_url,
                        url_fingerprint=fingerprint,
                        host=host,
                        first_seen_at=timestamp,
                        last_seen_at=timestamp,
                    )
                    self.session.add(lead)
                    self.session.flush()
            except IntegrityError:
                lead = self.session.scalar(
                    select(CatalogueDiscoveryLead).where(
                        CatalogueDiscoveryLead.url_fingerprint == fingerprint
                    )
                )
                if lead is None:
                    raise
        assert lead is not None
        if lead.normalized_url != normalized_url:
            raise DiscoveryStateError("catalogue_discovery_url_fingerprint_collision")
        observation = self.session.scalar(
            select(CatalogueDiscoveryObservation).where(
                CatalogueDiscoveryObservation.query_id == query.id,
                CatalogueDiscoveryObservation.lead_id == lead.id,
            )
        )
        if observation is not None:
            lead.last_seen_at = timestamp
            self.session.commit()
            return lead, observation

        lead_already_in_run = self.session.scalar(
            select(
                exists().where(
                    CatalogueDiscoveryObservation.lead_id == lead.id,
                    CatalogueDiscoveryObservation.query_id == CatalogueDiscoveryQuery.id,
                    CatalogueDiscoveryQuery.run_id == run.id,
                )
            )
        )
        if not lead_already_in_run and run.unique_leads >= run.max_leads:
            query.status = DiscoveryQueryStatus.BUDGET_EXHAUSTED
            query.failure_code = "lead_budget_exhausted"
            run.status = DiscoveryRunStatus.BUDGET_EXHAUSTED
            run.failure_code = "lead_budget_exhausted"
            self.session.commit()
            raise DiscoveryStateError("catalogue_discovery_lead_budget_exhausted")

        lead.last_seen_at = timestamp
        observation = CatalogueDiscoveryObservation(
            query_id=query.id,
            lead_id=lead.id,
            provider_rank=provider_rank,
            provider_source_type=provider_source_type,
            minimal_title=minimal_title,
            discovery_reason=discovery_reason,
            observed_at=timestamp,
        )
        self.session.add(observation)
        run.raw_leads_seen += 1
        if not lead_already_in_run:
            run.unique_leads += 1
        query.status = DiscoveryQueryStatus.LEADS_RECORDED
        self.session.commit()
        return lead, observation

    def append_assessment(
        self,
        *,
        run_id: uuid.UUID,
        lead_id: uuid.UUID,
        assessment: DiscoveryAssessmentInput,
    ) -> CatalogueDiscoveryAssessment:
        if self.session.get(CatalogueDiscoveryRun, run_id) is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        if not self._lead_was_observed_in_run(run_id=run_id, lead_id=lead_id):
            raise DiscoveryStateError("assessment_lead_was_not_observed_in_run")
        existing = self.session.scalar(
            select(CatalogueDiscoveryAssessment).where(
                CatalogueDiscoveryAssessment.lead_id == lead_id,
                CatalogueDiscoveryAssessment.assessment_context_hash
                == assessment.assessment_context_hash,
                CatalogueDiscoveryAssessment.classifier_version == assessment.classifier_version,
            )
        )
        if existing is not None:
            self.session.commit()
            return existing
        if assessment.supersedes_assessment_id is not None:
            superseded = self.session.get(
                CatalogueDiscoveryAssessment, assessment.supersedes_assessment_id
            )
            if superseded is None or superseded.lead_id != lead_id:
                raise DiscoveryStateError("superseded_assessment_must_reference_same_lead")
        try:
            with self.session.begin_nested():
                record = CatalogueDiscoveryAssessment(
                    run_id=run_id,
                    lead_id=lead_id,
                    **assessment.__dict__,
                )
                self.session.add(record)
                self.session.flush()
        except IntegrityError:
            record = self.session.scalar(
                select(CatalogueDiscoveryAssessment).where(
                    CatalogueDiscoveryAssessment.lead_id == lead_id,
                    CatalogueDiscoveryAssessment.assessment_context_hash
                    == assessment.assessment_context_hash,
                    CatalogueDiscoveryAssessment.classifier_version
                    == assessment.classifier_version,
                )
            )
            if record is None:
                raise
        self.session.commit()
        return record

    def bind_candidate_source(
        self,
        *,
        run_id: uuid.UUID,
        lead_id: uuid.UUID,
        assessment_id: uuid.UUID,
        now: datetime | None = None,
    ) -> DiscoverySourceBindingOutcome:
        observed_at = now or datetime.now(UTC)
        run = self._run_for_update(run_id)
        if run.target_candidate_id is None:
            raise DiscoveryStateError("binding_requires_explicit_target_candidate")
        if run.dry_run:
            raise DiscoveryStateError("binding_disabled_for_dry_run")
        if not self._lead_was_observed_in_run(run_id=run.id, lead_id=lead_id):
            raise DiscoveryStateError("binding_lead_was_not_observed_in_run")

        assessment = self.session.get(CatalogueDiscoveryAssessment, assessment_id)
        if (
            assessment is None
            or assessment.lead_id != lead_id
            or assessment.officiality_status is not DiscoveryOfficialityStatus.OFFICIAL
            or assessment.trust_tier is None
        ):
            raise DiscoveryStateError("binding_requires_acceptable_official_assessment")
        if self.session.scalar(
            select(
                exists().where(
                    CatalogueDiscoveryAssessment.supersedes_assessment_id == assessment.id
                )
            )
        ):
            raise DiscoveryStateError("binding_assessment_was_superseded")
        lead = self.session.get(CatalogueDiscoveryLead, lead_id)
        if lead is None or not lead.active:
            raise DiscoveryStateError("binding_requires_active_discovery_lead")
        candidate = self.session.scalar(
            select(CatalogueCandidate)
            .where(CatalogueCandidate.id == run.target_candidate_id)
            .with_for_update()
        )
        if candidate is None:
            raise DiscoveryStateError("binding_target_candidate_not_found")

        existing = self.session.scalar(
            select(CatalogueCandidateSource).where(
                CatalogueCandidateSource.candidate_id == candidate.id,
                CatalogueCandidateSource.discovery_lead_id == lead.id,
            )
        )
        if existing is not None:
            if existing.canonical_url != lead.normalized_url:
                raise DiscoveryStateError("binding_existing_source_url_mismatch")
            self.session.commit()
            return DiscoverySourceBindingOutcome(
                source=existing,
                created=False,
                candidate_resumed=False,
            )

        classification_reason = f"{assessment.reason_code}: {assessment.reason_detail}"[:500]
        source = self.session.scalar(
            select(CatalogueCandidateSource).where(
                CatalogueCandidateSource.candidate_id == candidate.id,
                CatalogueCandidateSource.canonical_url == lead.normalized_url,
            )
        )
        created = source is None
        if source is not None and (
            source.discovery_lead_id is not None
            or source.status is not CandidateSourceStatus.DISCOVERED
        ):
            raise DiscoveryStateError("binding_canonical_url_already_owned")
        candidate_resumed = self._prepare_candidate_for_binding(
            candidate,
            observed_at=observed_at,
        )
        if source is not None:
            source.discovery_lead_id = lead.id
            source.url = lead.normalized_url
            source.is_official = True
            source.trust_tier = assessment.trust_tier
            source.classification_reason = classification_reason
        else:
            try:
                with self.session.begin_nested():
                    source = CatalogueCandidateSource(
                        candidate_id=candidate.id,
                        discovery_lead_id=lead.id,
                        url=lead.normalized_url,
                        canonical_url=lead.normalized_url,
                        status=CandidateSourceStatus.DISCOVERED,
                        is_official=True,
                        trust_tier=assessment.trust_tier,
                        classification_reason=classification_reason,
                    )
                    self.session.add(source)
                    self.session.flush()
            except IntegrityError:
                source = self.session.scalar(
                    select(CatalogueCandidateSource).where(
                        CatalogueCandidateSource.candidate_id == candidate.id,
                        CatalogueCandidateSource.discovery_lead_id == lead.id,
                    )
                )
                if source is None:
                    self.session.rollback()
                    raise
                created = False
        self.session.commit()
        return DiscoverySourceBindingOutcome(
            source=source,
            created=created,
            candidate_resumed=candidate_resumed,
        )

    def record_promotion(
        self,
        *,
        run_id: uuid.UUID,
        lead_id: uuid.UUID,
        assessment_id: uuid.UUID,
        candidate_id: uuid.UUID,
        candidate_source_id: uuid.UUID,
        promotion_kind: str = "official_root_source",
        reason_code: str = "fetched_official_root",
    ) -> CatalogueDiscoveryPromotion:
        run = self._run_for_update(run_id)
        if run.target_candidate_id != candidate_id:
            raise DiscoveryStateError("promotion_candidate_is_not_run_target")
        if not self._lead_was_observed_in_run(run_id=run_id, lead_id=lead_id):
            raise DiscoveryStateError("promotion_lead_was_not_observed_in_run")
        existing = self.session.scalar(
            select(CatalogueDiscoveryPromotion).where(
                CatalogueDiscoveryPromotion.candidate_id == candidate_id,
                CatalogueDiscoveryPromotion.lead_id == lead_id,
            )
        )
        if existing is not None:
            self.session.commit()
            return existing
        assessment = self.session.get(CatalogueDiscoveryAssessment, assessment_id)
        source = self.session.get(CatalogueCandidateSource, candidate_source_id)
        if (
            assessment is None
            or assessment.lead_id != lead_id
            or assessment.officiality_status is not DiscoveryOfficialityStatus.OFFICIAL
        ):
            raise DiscoveryStateError("promotion_requires_official_matching_assessment")
        if (
            source is None
            or source.candidate_id != candidate_id
            or source.discovery_lead_id != lead_id
            or source.status is not CandidateSourceStatus.FETCHED
            or not source.is_official
        ):
            raise DiscoveryStateError("promotion_requires_fetched_matching_candidate_source")
        try:
            with self.session.begin_nested():
                promotion = CatalogueDiscoveryPromotion(
                    run_id=run_id,
                    lead_id=lead_id,
                    assessment_id=assessment_id,
                    candidate_id=candidate_id,
                    candidate_source_id=candidate_source_id,
                    promotion_kind=promotion_kind,
                    reason_code=reason_code,
                )
                self.session.add(promotion)
                self.session.flush()
        except IntegrityError:
            promotion = self.session.scalar(
                select(CatalogueDiscoveryPromotion).where(
                    CatalogueDiscoveryPromotion.candidate_id == candidate_id,
                    CatalogueDiscoveryPromotion.lead_id == lead_id,
                )
            )
            if promotion is None:
                raise
            self.session.commit()
            return promotion
        run.promotions += 1
        self.session.commit()
        return promotion

    def complete_query(
        self,
        query_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> CatalogueDiscoveryQuery:
        completed_at = now or datetime.now(UTC)
        query = self._query_for_update(query_id)
        if query.status not in {
            DiscoveryQueryStatus.RESPONSE_RECEIVED,
            DiscoveryQueryStatus.LEADS_RECORDED,
        }:
            raise DiscoveryStateError("discovery_query_cannot_complete_from_current_status")
        query.status = DiscoveryQueryStatus.COMPLETED
        query.completed_at = completed_at
        query.failure_code = None
        self._release_query(query)
        run = self._run_for_update(query.run_id)
        self._refresh_run_status(run, completed_at=completed_at)
        self.session.commit()
        return query

    def _query_for_update(self, query_id: uuid.UUID) -> CatalogueDiscoveryQuery:
        query = self.session.scalar(
            select(CatalogueDiscoveryQuery)
            .where(CatalogueDiscoveryQuery.id == query_id)
            .with_for_update()
        )
        if query is None:
            raise DiscoveryStateError("catalogue_discovery_query_not_found")
        return query

    @staticmethod
    def _prepare_candidate_for_binding(
        candidate: CatalogueCandidate,
        *,
        observed_at: datetime,
    ) -> bool:
        if candidate.opportunity_id is not None:
            raise DiscoveryStateError("binding_candidate_already_has_opportunity")
        if any(
            (
                candidate.proposed_payload is not None,
                bool(candidate.validation_errors),
                bool(candidate.conflicts),
                bool(candidate.duplicate_opportunity_ids),
            )
        ):
            raise DiscoveryStateError("binding_candidate_has_review_or_resolution_state")
        if (
            candidate.claimed_by is not None
            and candidate.claimed_until is not None
            and candidate.claimed_until >= observed_at
        ):
            raise DiscoveryStateError("binding_candidate_is_actively_claimed")

        if candidate.status is CandidateStatus.DISCOVERED:
            if candidate.claimed_by is not None or candidate.claimed_until is not None:
                candidate.claimed_by = None
                candidate.claimed_until = None
            return False
        if (
            candidate.status is CandidateStatus.NEEDS_REVIEW
            and candidate.failure_code == "official_source_not_found"
        ):
            candidate.status = CandidateStatus.DISCOVERED
            candidate.failure_code = None
            candidate.failure_reason = None
            candidate.next_attempt_at = observed_at
            candidate.claimed_by = None
            candidate.claimed_until = None
            return True
        raise DiscoveryStateError("binding_candidate_lifecycle_incompatible")

    def _run_for_update(self, run_id: uuid.UUID) -> CatalogueDiscoveryRun:
        run = self.session.scalar(
            select(CatalogueDiscoveryRun)
            .where(CatalogueDiscoveryRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        return run

    def _lead_was_observed_in_run(self, *, run_id: uuid.UUID, lead_id: uuid.UUID) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        CatalogueDiscoveryObservation.lead_id == lead_id,
                        CatalogueDiscoveryObservation.query_id == CatalogueDiscoveryQuery.id,
                        CatalogueDiscoveryQuery.run_id == run_id,
                    )
                )
            )
        )

    def _settle_locked(
        self,
        attempt: CatalogueDiscoveryAttempt,
        query: CatalogueDiscoveryQuery,
        run: CatalogueDiscoveryRun,
        outcome: DiscoveryAttemptOutcome,
        *,
        observed_at: datetime,
    ) -> None:
        actual_cost = outcome.estimated_total_cost
        exceeded_reservation = (
            outcome.tool_call_count > attempt.reserved_tool_calls
            or actual_cost > attempt.reserved_estimated_cost
            or outcome.response_bytes > run.max_response_bytes
        )
        terminal_status = (
            DiscoveryAttemptStatus.RESPONSE_INVALID if exceeded_reservation else outcome.status
        )
        error_code = "provider_reservation_exceeded" if exceeded_reservation else outcome.error_code

        run.provider_calls_reserved -= 1
        run.provider_calls_completed += 1
        run.tool_calls_reserved -= attempt.reserved_tool_calls
        run.tool_calls_completed += outcome.tool_call_count
        run.estimated_cost_reserved -= attempt.reserved_estimated_cost
        run.estimated_cost_settled += actual_cost
        if exceeded_reservation:
            run.status = DiscoveryRunStatus.FAILED
            run.failure_code = "provider_reservation_exceeded"
        elif terminal_status is DiscoveryAttemptStatus.CAPABILITY_UNAVAILABLE:
            run.status = DiscoveryRunStatus.CAPABILITY_UNAVAILABLE
            run.failure_code = outcome.error_code or "provider_capability_unavailable"
        elif run.estimated_cost_settled > run.max_estimated_cost:
            run.status = DiscoveryRunStatus.BUDGET_EXHAUSTED
            run.failure_code = "actual_cost_budget_exhausted"

        attempt.status = terminal_status
        attempt.provider_response_id = outcome.provider_response_id
        attempt.http_status = outcome.http_status
        attempt.web_search_executed = outcome.web_search_executed
        attempt.tool_call_count = outcome.tool_call_count
        attempt.result_url_count = outcome.result_url_count
        attempt.response_bytes = outcome.response_bytes
        attempt.input_tokens = outcome.input_tokens
        attempt.output_tokens = outcome.output_tokens
        attempt.estimated_model_cost = outcome.estimated_model_cost
        attempt.estimated_tool_cost = outcome.estimated_tool_cost
        attempt.estimated_total_cost = actual_cost
        attempt.latency_ms = outcome.latency_ms
        attempt.error_code = error_code
        attempt.completed_at = observed_at

        query.provider_call_count += 1
        query.tool_call_count += outcome.tool_call_count
        query.response_bytes += outcome.response_bytes
        query.latency_ms += outcome.latency_ms or 0
        query.estimated_cost += actual_cost
        query.failure_code = error_code
        query.status = _query_status_for_attempt(terminal_status)
        if terminal_status is DiscoveryAttemptStatus.SUCCEEDED:
            query.failure_code = None
        self._release_query(query)

    @staticmethod
    def _release_query(query: CatalogueDiscoveryQuery) -> None:
        query.claimed_by = None
        query.claimed_until = None

    def _refresh_run_status(
        self,
        run: CatalogueDiscoveryRun,
        *,
        completed_at: datetime,
    ) -> None:
        if run.status in {
            DiscoveryRunStatus.BUDGET_EXHAUSTED,
            DiscoveryRunStatus.CAPABILITY_UNAVAILABLE,
            DiscoveryRunStatus.FAILED,
        }:
            return
        self.session.flush()
        statuses = set(
            self.session.scalars(
                select(CatalogueDiscoveryQuery.status).where(
                    CatalogueDiscoveryQuery.run_id == run.id
                )
            )
        )
        active = {
            DiscoveryQueryStatus.PLANNED,
            DiscoveryQueryStatus.CLAIMED,
            DiscoveryQueryStatus.CALLING_PROVIDER,
            DiscoveryQueryStatus.RESPONSE_RECEIVED,
            DiscoveryQueryStatus.LEADS_RECORDED,
        }
        if statuses.intersection(active):
            return
        failures = statuses - {DiscoveryQueryStatus.COMPLETED, DiscoveryQueryStatus.CANCELLED}
        run.status = DiscoveryRunStatus.PARTIAL if failures else DiscoveryRunStatus.COMPLETED
        run.completed_at = completed_at


def _query_status_for_attempt(status: DiscoveryAttemptStatus) -> DiscoveryQueryStatus:
    return {
        DiscoveryAttemptStatus.SUCCEEDED: DiscoveryQueryStatus.RESPONSE_RECEIVED,
        DiscoveryAttemptStatus.RATE_LIMITED: DiscoveryQueryStatus.PROVIDER_RATE_LIMITED,
        DiscoveryAttemptStatus.TIMEOUT: DiscoveryQueryStatus.PROVIDER_FAILED,
        DiscoveryAttemptStatus.PROVIDER_FAILED: DiscoveryQueryStatus.PROVIDER_FAILED,
        DiscoveryAttemptStatus.RESPONSE_INVALID: DiscoveryQueryStatus.RESPONSE_INVALID,
        DiscoveryAttemptStatus.TOOL_NOT_EXECUTED: DiscoveryQueryStatus.TOOL_NOT_EXECUTED,
        DiscoveryAttemptStatus.CAPABILITY_UNAVAILABLE: (
            DiscoveryQueryStatus.CAPABILITY_UNAVAILABLE
        ),
        DiscoveryAttemptStatus.ABANDONED: DiscoveryQueryStatus.PROVIDER_FAILED,
    }[status]
