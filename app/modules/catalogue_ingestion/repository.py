"""Bounded database access for ingestion workers and administrator views."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, inspect, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    CatalogueJobState,
    CatalogueResumableJob,
    ExtractionAttemptStatus,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.provider_attempts import (
    CatalogueProviderAttempt,
    ProviderAccountingState,
    ProviderAttemptState,
    ProviderFailureClass,
)
from app.modules.catalogue_ingestion.schemas import SeedCandidate

PROCESSABLE_STATUSES = {
    CandidateStatus.DISCOVERED,
    CandidateStatus.OFFICIAL_SOURCE_CANDIDATE,
    CandidateStatus.SOURCE_FETCHED,
    CandidateStatus.EXTRACTED,
}


def _as_utc(value: datetime) -> datetime:
    """Normalize database-returned timestamps before Python-side lease comparisons.

    PostgreSQL preserves timezone information, while SQLite (used by the fast test suite) returns
    ``DateTime(timezone=True)`` values as naive datetimes. Treating a naive value as UTC keeps the
    fencing checks identical across both backends.
    """

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _refresh_clean_columns(instance: object, row: object) -> None:
    """Refresh only clean ORM attributes after a locking read.

    A lease check must observe the database row, but ``populate_existing`` would overwrite a
    caller's uncommitted candidate/proposal changes.  Refreshing only attributes without pending
    history preserves those changes while still updating stale lease fields before fencing.
    """

    state = inspect(instance)
    for column in instance.__table__.columns:  # type: ignore[attr-defined]
        attribute = state.attrs[column.key]
        if not attribute.history.has_changes():
            setattr(instance, column.key, row[column.key])  # type: ignore[index]


_TERMINAL_RUN_STATUSES = {
    IngestionRunStatus.COMPLETED,
    IngestionRunStatus.COMPLETED_WITH_REVIEW,
    IngestionRunStatus.COMPLETED_WITH_FAILURES,
    IngestionRunStatus.FAILED,
    IngestionRunStatus.CANCELLED,
}
_REVIEW_OUTCOMES = {
    CandidateStatus.CONFLICT_DETECTED,
    CandidateStatus.DUPLICATE_CANDIDATE,
    CandidateStatus.NEEDS_REVIEW,
    CandidateStatus.READY_FOR_REVIEW,
}
_FAILURE_OUTCOMES = {
    CandidateStatus.VALIDATION_FAILED,
    CandidateStatus.REJECTED,
    CandidateStatus.SOURCE_CHANGED,
}
_PIPELINE_FAILURE_CODES = {
    "unexpected_pipeline_failure",
    "candidate_lease_lost",
    "run_lease_lost",
    "provider_configuration_drift",
}


class ProviderBudgetReservationError(RuntimeError):
    """A physical provider attempt cannot be reserved inside the run budget."""


class CatalogueLeaseLost(RuntimeError):
    """The caller no longer owns the current run/candidate fencing epoch."""


class CatalogueIngestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_run(self, run: CatalogueIngestionRun) -> None:
        self.session.add(run)
        self.session.flush()

    def get_run(self, run_id: uuid.UUID) -> CatalogueIngestionRun | None:
        return self.session.get(CatalogueIngestionRun, run_id)

    def acquire_run_lease(
        self,
        run_id: uuid.UUID,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> str:
        observed_at = now or datetime.now(UTC)
        run = self._run_for_update(run_id)
        if run is None:
            raise CatalogueLeaseLost("ingestion_run_missing")
        if run.status in _TERMINAL_RUN_STATUSES:
            raise CatalogueLeaseLost("ingestion_run_terminal")
        if (
            run.lease_token is None
            or run.lease_expires_at is None
            or _as_utc(run.lease_expires_at) < _as_utc(observed_at)
        ):
            run.lease_token = uuid.uuid4().hex
        run.lease_expires_at = observed_at + timedelta(seconds=lease_seconds)
        token = run.lease_token
        self.session.commit()
        assert token is not None
        return token

    def heartbeat_run_lease(
        self,
        run_id: uuid.UUID,
        *,
        lease_token: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> None:
        observed_at = now or datetime.now(UTC)
        run = self._run_for_update(run_id)
        if run is None or not self._run_lease_matches(run, lease_token, observed_at=observed_at):
            self.session.rollback()
            raise CatalogueLeaseLost("run_lease_lost")
        run.lease_expires_at = observed_at + timedelta(seconds=lease_seconds)
        self.session.commit()

    def release_run_lease(self, run_id: uuid.UUID, *, lease_token: str) -> bool:
        run = self._run_for_update(run_id)
        if run is None or run.lease_token != lease_token:
            self.session.rollback()
            return False
        run.lease_token = None
        run.lease_expires_at = None
        self.session.commit()
        return True

    def add_seed_candidates(
        self,
        run: CatalogueIngestionRun,
        seeds: list[SeedCandidate],
        *,
        start_index: int = 0,
        identity_hint_is_asserted: bool = True,
    ) -> int:
        created = 0
        keyed_seeds = [
            (index, seed, candidate_idempotency_key(seed, run_id=run.id))
            for index, seed in enumerate(seeds, start=start_index)
        ]
        existing: set[str] = set()
        for offset in range(0, len(keyed_seeds), 500):
            keys = [key for _, _, key in keyed_seeds[offset : offset + 500]]
            existing.update(
                self.session.scalars(
                    select(CatalogueCandidate.idempotency_key).where(
                        CatalogueCandidate.run_id == run.id,
                        CatalogueCandidate.idempotency_key.in_(keys),
                    )
                )
            )
        seen = set(existing)
        for index, seed, key in keyed_seeds:
            if key in seen:
                continue
            seen.add(key)
            self.session.add(
                CatalogueCandidate(
                    run_id=run.id,
                    seed_index=index,
                    idempotency_key=key,
                    seed_name=seed.name,
                    seed_provider=seed.provider,
                    seed_university=seed.university,
                    seed_country=seed.country,
                    seed_cycle=seed.cycle,
                    seed_intake_year=seed.intake_year,
                    seed_official_url=(
                        str(seed.possible_official_url) if seed.possible_official_url else None
                    ),
                    identity_hint_is_asserted=identity_hint_is_asserted,
                    seed_keywords=seed.keywords,
                )
            )
            created += 1
        self.session.commit()
        return created

    def claim_candidates(
        self,
        *,
        run_id: uuid.UUID,
        run_lease_token: str,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> list[CatalogueCandidate]:
        observed_at = now or datetime.now(UTC)
        self._assert_run_lease(run_id, run_lease_token, observed_at=observed_at)
        candidates = list(
            self.session.scalars(
                select(CatalogueCandidate)
                .where(
                    CatalogueCandidate.run_id == run_id,
                    CatalogueCandidate.status.in_(PROCESSABLE_STATUSES),
                    or_(
                        CatalogueCandidate.next_attempt_at.is_(None),
                        CatalogueCandidate.next_attempt_at <= observed_at,
                    ),
                    or_(
                        CatalogueCandidate.claimed_until.is_(None),
                        CatalogueCandidate.claimed_until < observed_at,
                    ),
                )
                .order_by(
                    CatalogueCandidate.attempt_count,
                    CatalogueCandidate.seed_index,
                )
                .limit(limit)
                .options(
                    selectinload(CatalogueCandidate.sources).selectinload(
                        CatalogueCandidateSource.artifacts
                    )
                )
                .execution_options(populate_existing=True)
                .with_for_update(skip_locked=True)
            )
        )
        claimed_until = observed_at + timedelta(seconds=lease_seconds)
        for candidate in candidates:
            candidate.claimed_by = worker_id
            candidate.claimed_until = claimed_until
            candidate.lease_token = uuid.uuid4().hex
            candidate.attempt_count += 1
        self.session.commit()
        return candidates

    def heartbeat_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        run_lease_token: str,
        worker_id: str,
        lease_token: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> None:
        observed_at = now or datetime.now(UTC)
        candidate = self._candidate_for_update(candidate_id)
        if candidate is None:
            self.session.rollback()
            raise CatalogueLeaseLost("candidate_missing")
        self._assert_run_lease(candidate.run_id, run_lease_token, observed_at=observed_at)
        if not self._candidate_lease_matches(
            candidate,
            worker_id=worker_id,
            lease_token=lease_token,
            observed_at=observed_at,
        ):
            self.session.rollback()
            raise CatalogueLeaseLost("candidate_lease_lost")
        candidate.claimed_until = observed_at + timedelta(seconds=lease_seconds)
        self.session.commit()

    def assert_candidate_lease(
        self,
        candidate_id: uuid.UUID,
        *,
        run_lease_token: str,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> CatalogueCandidate:
        observed_at = now or datetime.now(UTC)
        candidate = self._candidate_for_update(candidate_id)
        if candidate is None:
            raise CatalogueLeaseLost("candidate_missing")
        self._assert_run_lease(candidate.run_id, run_lease_token, observed_at=observed_at)
        if not self._candidate_lease_matches(
            candidate,
            worker_id=worker_id,
            lease_token=lease_token,
            observed_at=observed_at,
        ):
            raise CatalogueLeaseLost("candidate_lease_lost")
        return candidate

    def get_candidate(self, candidate_id: uuid.UUID) -> CatalogueCandidate | None:
        return self.session.scalar(
            select(CatalogueCandidate)
            .where(CatalogueCandidate.id == candidate_id)
            .options(
                selectinload(CatalogueCandidate.sources).selectinload(
                    CatalogueCandidateSource.artifacts
                )
            )
        )

    def get_candidate_for_update(self, candidate_id: uuid.UUID) -> CatalogueCandidate | None:
        with self.session.no_autoflush:
            return self.session.scalar(
                select(CatalogueCandidate)
                .where(CatalogueCandidate.id == candidate_id)
                .options(
                    selectinload(CatalogueCandidate.sources).selectinload(
                        CatalogueCandidateSource.artifacts
                    )
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )

    def release_candidate(
        self,
        candidate: CatalogueCandidate,
        *,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> bool:
        """Release the current candidate lease with an atomic fencing predicate.

        The conditional UPDATE executes with autoflush suppressed, so dirty candidate results are
        not written before ownership is proven. The UPDATE then holds the row lock until the
        caller's transaction commits, allowing the caller to flush its result safely.
        """

        expected_worker = worker_id if worker_id is not None else candidate.claimed_by
        expected_token = lease_token if lease_token is not None else candidate.lease_token
        if expected_worker is None and expected_token is None:
            candidate.claimed_until = None
            return True
        if expected_worker is None or expected_token is None:
            raise CatalogueLeaseLost("candidate_release_requires_complete_lease")
        with self.session.no_autoflush:
            result = self.session.execute(
                update(CatalogueCandidate)
                .where(
                    CatalogueCandidate.id == candidate.id,
                    CatalogueCandidate.claimed_by == expected_worker,
                    CatalogueCandidate.lease_token == expected_token,
                )
                .values(claimed_by=None, claimed_until=None, lease_token=None)
                .execution_options(synchronize_session=False)
            )
        if result.rowcount != 1:
            self.session.rollback()
            raise CatalogueLeaseLost("candidate_release_lease_lost")
        candidate.claimed_by = None
        candidate.claimed_until = None
        candidate.lease_token = None
        return True

    def start_or_resume_job(
        self,
        *,
        run_id: uuid.UUID,
        candidate_id: uuid.UUID,
        stage: str,
        job_key: str,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
        checkpoint: dict[str, object] | None = None,
    ) -> CatalogueResumableJob:
        self.assert_candidate_lease(
            candidate_id,
            run_lease_token=run_lease_token,
            worker_id=worker_id,
            lease_token=candidate_lease_token,
        )
        with self.session.no_autoflush:
            job = self.session.scalar(
                select(CatalogueResumableJob)
                .where(CatalogueResumableJob.job_key == job_key)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        if job is None:
            job = CatalogueResumableJob(
                run_id=run_id,
                candidate_id=candidate_id,
                job_key=job_key,
                stage=stage,
                state=CatalogueJobState.RUNNING,
                checkpoint=dict(checkpoint or {}),
                worker_id=worker_id,
                run_lease_token=run_lease_token,
                candidate_lease_token=candidate_lease_token,
                attempt_count=1,
            )
            self.session.add(job)
        elif job.state is not CatalogueJobState.SUCCEEDED:
            job.stage = stage
            job.state = CatalogueJobState.RUNNING
            job.worker_id = worker_id
            job.run_lease_token = run_lease_token
            job.candidate_lease_token = candidate_lease_token
            job.attempt_count += 1
            job.error_code = None
            job.error_detail = None
            job.completed_at = None
            if checkpoint is not None:
                job.checkpoint = dict(checkpoint)
        self.session.commit()
        return job

    def checkpoint_job(
        self,
        job_id: uuid.UUID,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
        checkpoint: dict[str, object],
    ) -> None:
        job = self._owned_job(
            job_id,
            worker_id=worker_id,
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate_lease_token,
        )
        job.checkpoint = dict(checkpoint)
        self.session.commit()

    def complete_job(
        self,
        job_id: uuid.UUID,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
        checkpoint: dict[str, object] | None = None,
    ) -> None:
        job = self._owned_job(
            job_id,
            worker_id=worker_id,
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate_lease_token,
        )
        job.state = CatalogueJobState.SUCCEEDED
        if checkpoint is not None:
            job.checkpoint = dict(checkpoint)
        job.completed_at = datetime.now(UTC)
        self.session.commit()

    def mark_job_lease_lost(self, job_id: uuid.UUID, *, error_code: str) -> None:
        with self.session.no_autoflush:
            job = self.session.scalar(
                select(CatalogueResumableJob)
                .where(CatalogueResumableJob.id == job_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        if job is None or job.state is CatalogueJobState.SUCCEEDED:
            self.session.rollback()
            return
        job.state = CatalogueJobState.LEASE_LOST
        job.error_code = error_code[:100]
        job.error_detail = "work stopped because the fencing lease was no longer current"
        job.completed_at = datetime.now(UTC)
        self.session.commit()

    def reusable_attempt(
        self,
        *,
        canonical_url: str,
        content_hash: str,
        schema_version: str,
        prompt_hash: str,
        provider: str,
        model: str,
    ) -> CatalogueExtractionAttempt | None:
        return self.session.scalar(
            select(CatalogueExtractionAttempt)
            .join(CatalogueCandidateSource)
            .where(
                CatalogueCandidateSource.canonical_url == canonical_url,
                CatalogueExtractionAttempt.content_hash == content_hash,
                CatalogueExtractionAttempt.schema_version == schema_version,
                CatalogueExtractionAttempt.prompt_hash == prompt_hash,
                CatalogueExtractionAttempt.provider == provider,
                CatalogueExtractionAttempt.model == model,
                CatalogueExtractionAttempt.status == ExtractionAttemptStatus.SUCCEEDED,
                CatalogueExtractionAttempt.output_json.is_not(None),
            )
            .order_by(CatalogueExtractionAttempt.created_at.desc())
        )

    def reserve_provider_attempt(
        self,
        *,
        run_id: uuid.UUID,
        run_lease_token: str,
        candidate_id: uuid.UUID,
        source_id: uuid.UUID | None,
        source_artifact_id: uuid.UUID | None,
        extraction_job_key: str,
        objective: str | None,
        objective_bundle: list[str],
        evidence_block_keys: list[str],
        provider: str,
        deployment: str | None,
        model: str,
        prompt_hash: str,
        schema_version: str,
        parser_version: str,
        normalizer_version: str,
        worker_id: str,
        lease_token: str,
        reserved_cost_upper: Decimal,
    ) -> CatalogueProviderAttempt:
        observed_at = datetime.now(UTC)
        run = self._run_for_update(run_id)
        candidate = self._candidate_for_update(candidate_id)
        if run is None:
            raise ProviderBudgetReservationError("ingestion_run_missing")
        if not self._run_lease_matches(run, run_lease_token, observed_at=observed_at):
            raise CatalogueLeaseLost("run_lease_lost")
        if (
            candidate is None
            or candidate.run_id != run_id
            or not self._candidate_lease_matches(
                candidate,
                worker_id=worker_id,
                lease_token=lease_token,
                observed_at=observed_at,
            )
        ):
            raise CatalogueLeaseLost("candidate_lease_lost")

        existing_call_count = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueProviderAttempt)
                .where(
                    CatalogueProviderAttempt.run_id == run_id,
                    ~and_(
                        CatalogueProviderAttempt.state == ProviderAttemptState.FAILED,
                        CatalogueProviderAttempt.failure_class
                        == ProviderFailureClass.PRE_DISPATCH_FAILURE,
                    ),
                )
            )
            or 0
        )
        if existing_call_count >= run.max_model_calls:
            raise ProviderBudgetReservationError("provider_call_budget_exhausted")
        current_upper = self.session.scalar(
            select(func.coalesce(func.sum(CatalogueProviderAttempt.cost_upper_bound), 0)).where(
                CatalogueProviderAttempt.run_id == run_id
            )
        )
        if Decimal(str(current_upper or 0)) + reserved_cost_upper > run.max_estimated_cost:
            raise ProviderBudgetReservationError("provider_cost_budget_exhausted")
        retry_ordinal = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueProviderAttempt)
                .where(CatalogueProviderAttempt.extraction_job_key == extraction_job_key)
            )
            or 0
        )
        attempt = CatalogueProviderAttempt(
            run_id=run_id,
            candidate_id=candidate_id,
            source_id=source_id,
            source_artifact_id=source_artifact_id,
            extraction_job_key=extraction_job_key,
            objective=objective,
            objective_bundle=objective_bundle,
            evidence_block_keys=evidence_block_keys,
            provider=provider,
            deployment=deployment,
            model=model,
            prompt_hash=prompt_hash,
            schema_version=schema_version,
            parser_version=parser_version,
            normalizer_version=normalizer_version,
            retry_ordinal=retry_ordinal,
            worker_id=worker_id,
            lease_token=lease_token,
            state=ProviderAttemptState.RESERVED,
            accounting_state=ProviderAccountingState.ESTIMATED,
            reserved_cost_upper=reserved_cost_upper,
            cost_lower_bound=Decimal("0"),
            cost_upper_bound=reserved_cost_upper,
            metadata_json={"run_lease_token": run_lease_token},
        )
        self.session.add(attempt)
        self.session.flush()
        self.refresh_provider_accounting(run)
        self.session.commit()
        return attempt

    def mark_provider_attempt_dispatching(
        self,
        attempt: CatalogueProviderAttempt,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
    ) -> None:
        self._assert_provider_attempt_ownership(
            attempt,
            worker_id=worker_id,
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate_lease_token,
        )
        attempt.state = ProviderAttemptState.DISPATCHING
        attempt.dispatch_started_at = datetime.now(UTC)
        self.session.commit()

    def complete_provider_attempt(
        self,
        attempt: CatalogueProviderAttempt,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
        input_tokens: int,
        output_tokens: int,
        exact_cost: Decimal,
        provider_request_id: str | None,
    ) -> None:
        self._assert_provider_attempt_ownership(
            attempt,
            worker_id=worker_id,
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate_lease_token,
        )
        attempt.state = ProviderAttemptState.SUCCEEDED
        attempt.dispatched_at = (
            attempt.dispatched_at or attempt.dispatch_started_at or datetime.now(UTC)
        )
        attempt.completed_at = datetime.now(UTC)
        attempt.failure_class = None
        attempt.error_code = None
        attempt.safe_error_detail = None
        attempt.accounting_state = ProviderAccountingState.EXACT
        attempt.cost_lower_bound = exact_cost
        attempt.cost_upper_bound = exact_cost
        attempt.input_tokens = input_tokens
        attempt.output_tokens = output_tokens
        attempt.provider_request_id = provider_request_id
        # Sessions deliberately disable autoflush for lease/fencing reads. Flush the
        # settled ledger row before deriving run-level accounting, otherwise the query
        # observes the prior reservation and callers can miss an actual-cost overflow.
        self.session.flush()
        run = self.session.get(CatalogueIngestionRun, attempt.run_id)
        if run is not None:
            self.refresh_provider_accounting(run)
        self.session.commit()

    def fail_provider_attempt(
        self,
        attempt: CatalogueProviderAttempt,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
        failure_class: ProviderFailureClass,
        error_code: str,
        safe_error_detail: str,
        provider_request_id: str | None,
        dispatch_occurred: bool,
        potentially_billable: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        exact_cost: Decimal | None = None,
    ) -> None:
        self._assert_provider_attempt_ownership(
            attempt,
            worker_id=worker_id,
            run_lease_token=run_lease_token,
            candidate_lease_token=candidate_lease_token,
        )
        attempt.state = ProviderAttemptState.FAILED
        attempt.failure_class = failure_class
        attempt.error_code = error_code[:100]
        attempt.safe_error_detail = safe_error_detail[:1000]
        attempt.provider_request_id = provider_request_id
        attempt.completed_at = datetime.now(UTC)
        if dispatch_occurred:
            attempt.dispatched_at = (
                attempt.dispatched_at or attempt.dispatch_started_at or datetime.now(UTC)
            )
        if exact_cost is not None:
            attempt.accounting_state = ProviderAccountingState.EXACT
            attempt.cost_lower_bound = exact_cost
            attempt.cost_upper_bound = exact_cost
            attempt.input_tokens = input_tokens
            attempt.output_tokens = output_tokens
        elif potentially_billable:
            attempt.accounting_state = ProviderAccountingState.UNKNOWN_POTENTIALLY_BILLABLE
            attempt.cost_lower_bound = Decimal("0")
            attempt.cost_upper_bound = attempt.reserved_cost_upper
        else:
            attempt.accounting_state = ProviderAccountingState.NOT_BILLABLE
            attempt.cost_lower_bound = Decimal("0")
            attempt.cost_upper_bound = Decimal("0")
        self.session.flush()
        run = self.session.get(CatalogueIngestionRun, attempt.run_id)
        if run is not None:
            self.refresh_provider_accounting(run)
        self.session.commit()

    def record_provider_attempt_lease_loss(
        self,
        attempt: CatalogueProviderAttempt,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        exact_cost: Decimal | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        with self.session.no_autoflush:
            current = self.session.scalar(
                select(CatalogueProviderAttempt)
                .where(CatalogueProviderAttempt.id == attempt.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        if current is None or current.state in {
            ProviderAttemptState.SUCCEEDED,
            ProviderAttemptState.FAILED,
        }:
            self.session.rollback()
            return
        current.state = ProviderAttemptState.FAILED
        current.failure_class = ProviderFailureClass.LEASE_LOSS
        current.error_code = "provider_lease_lost"
        current.safe_error_detail = "provider_result_discarded_after_fencing_lease_loss"
        current.provider_request_id = provider_request_id
        current.completed_at = datetime.now(UTC)
        current.dispatched_at = current.dispatched_at or current.dispatch_started_at
        if exact_cost is not None:
            current.accounting_state = ProviderAccountingState.EXACT
            current.cost_lower_bound = exact_cost
            current.cost_upper_bound = exact_cost
            current.input_tokens = input_tokens
            current.output_tokens = output_tokens
        else:
            current.accounting_state = ProviderAccountingState.UNKNOWN_POTENTIALLY_BILLABLE
            current.cost_lower_bound = Decimal("0")
            current.cost_upper_bound = current.reserved_cost_upper
        self.session.flush()
        run = self.session.get(CatalogueIngestionRun, current.run_id)
        if run is not None:
            self.refresh_provider_accounting(run)
        self.session.commit()

    def link_provider_attempt(
        self,
        provider_attempt_id: uuid.UUID,
        extraction_attempt_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        run_lease_token: str | None = None,
        candidate_lease_token: str | None = None,
    ) -> None:
        with self.session.no_autoflush:
            attempt = self.session.get(CatalogueProviderAttempt, provider_attempt_id)
        if attempt is None:
            return
        if worker_id and run_lease_token and candidate_lease_token:
            self._assert_provider_attempt_ownership(
                attempt,
                worker_id=worker_id,
                run_lease_token=run_lease_token,
                candidate_lease_token=candidate_lease_token,
            )
        attempt.extraction_attempt_id = extraction_attempt_id
        self.session.flush()

    def refresh_provider_accounting(self, run: CatalogueIngestionRun) -> None:
        count = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueProviderAttempt)
                .where(
                    CatalogueProviderAttempt.run_id == run.id,
                    ~and_(
                        CatalogueProviderAttempt.state == ProviderAttemptState.FAILED,
                        CatalogueProviderAttempt.failure_class
                        == ProviderFailureClass.PRE_DISPATCH_FAILURE,
                    ),
                )
            )
            or 0
        )
        input_tokens = (
            self.session.scalar(
                select(func.coalesce(func.sum(CatalogueProviderAttempt.input_tokens), 0)).where(
                    CatalogueProviderAttempt.run_id == run.id
                )
            )
            or 0
        )
        output_tokens = (
            self.session.scalar(
                select(func.coalesce(func.sum(CatalogueProviderAttempt.output_tokens), 0)).where(
                    CatalogueProviderAttempt.run_id == run.id
                )
            )
            or 0
        )
        lower = (
            self.session.scalar(
                select(func.coalesce(func.sum(CatalogueProviderAttempt.cost_lower_bound), 0)).where(
                    CatalogueProviderAttempt.run_id == run.id
                )
            )
            or 0
        )
        upper = (
            self.session.scalar(
                select(func.coalesce(func.sum(CatalogueProviderAttempt.cost_upper_bound), 0)).where(
                    CatalogueProviderAttempt.run_id == run.id
                )
            )
            or 0
        )
        uncertain = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueProviderAttempt)
                .where(
                    CatalogueProviderAttempt.run_id == run.id,
                    CatalogueProviderAttempt.accounting_state
                    == ProviderAccountingState.UNKNOWN_POTENTIALLY_BILLABLE,
                )
            )
            or 0
        )
        run.model_calls = int(count)
        run.input_tokens = int(input_tokens)
        run.output_tokens = int(output_tokens)
        run.estimated_cost = Decimal(str(upper))
        summary = dict(run.aggregate_summary or {})
        summary.update(
            {
                "provider_attempts": int(count),
                "provider_cost_lower_bound": str(Decimal(str(lower))),
                "provider_cost_upper_bound": str(Decimal(str(upper))),
                "provider_accounting_uncertain": int(uncertain),
            }
        )
        run.aggregate_summary = summary

    def list_runs(self, *, limit: int, offset: int) -> tuple[list[CatalogueIngestionRun], int]:
        items = list(
            self.session.scalars(
                select(CatalogueIngestionRun)
                .order_by(CatalogueIngestionRun.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        total = self.session.scalar(select(func.count()).select_from(CatalogueIngestionRun)) or 0
        return items, total

    def list_candidates(
        self,
        *,
        status: CandidateStatus | None,
        run_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[CatalogueCandidate], int]:
        filters = []
        if status is not None:
            filters.append(CatalogueCandidate.status == status)
        if run_id is not None:
            filters.append(CatalogueCandidate.run_id == run_id)
        base = select(CatalogueCandidate).where(*filters)
        items = list(
            self.session.scalars(
                base.options(
                    selectinload(CatalogueCandidate.sources).selectinload(
                        CatalogueCandidateSource.artifacts
                    )
                )
                .order_by(CatalogueCandidate.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        total = (
            self.session.scalar(
                select(func.count()).select_from(CatalogueCandidate).where(*filters)
            )
            or 0
        )
        return items, total

    def refresh_run_summary(self, run: CatalogueIngestionRun) -> None:
        counts = self.session.execute(
            select(CatalogueCandidate.status, func.count())
            .where(CatalogueCandidate.run_id == run.id)
            .group_by(CatalogueCandidate.status)
        ).all()
        pipeline_failures = (
            self.session.scalar(
                select(func.count())
                .select_from(CatalogueCandidate)
                .where(
                    CatalogueCandidate.run_id == run.id,
                    CatalogueCandidate.failure_code.in_(_PIPELINE_FAILURE_CODES),
                )
            )
            or 0
        )
        provider_summary = {
            key: value
            for key, value in (run.aggregate_summary or {}).items()
            if key.startswith("provider_")
        }
        run.aggregate_summary = {
            **{status.value: count for status, count in counts},
            "pipeline_failures": int(pipeline_failures),
            **provider_summary,
        }
        self.refresh_provider_accounting(run)
        if run.status is not IngestionRunStatus.RUNNING:
            return
        if any(status in PROCESSABLE_STATUSES and count for status, count in counts):
            return
        statuses = {status for status, count in counts if count}
        if pipeline_failures or statuses & _FAILURE_OUTCOMES:
            run.status = IngestionRunStatus.COMPLETED_WITH_FAILURES
        elif statuses & _REVIEW_OUTCOMES:
            run.status = IngestionRunStatus.COMPLETED_WITH_REVIEW
        else:
            run.status = IngestionRunStatus.COMPLETED
        run.completed_at = datetime.now(UTC)
        run.lease_token = None
        run.lease_expires_at = None

    def _run_for_update(self, run_id: uuid.UUID) -> CatalogueIngestionRun | None:
        with self.session.no_autoflush:
            row = (
                self.session.execute(
                    select(CatalogueIngestionRun.__table__)
                    .where(CatalogueIngestionRun.id == run_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            run = self.session.get(CatalogueIngestionRun, run_id)
            if run is None:
                return None
            _refresh_clean_columns(run, row)
            return run

    def _candidate_for_update(self, candidate_id: uuid.UUID) -> CatalogueCandidate | None:
        with self.session.no_autoflush:
            row = (
                self.session.execute(
                    select(CatalogueCandidate.__table__)
                    .where(CatalogueCandidate.id == candidate_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            candidate = self.session.get(CatalogueCandidate, candidate_id)
            if candidate is None:
                return None
            _refresh_clean_columns(candidate, row)
            return candidate

    def _assert_run_lease(
        self,
        run_id: uuid.UUID,
        lease_token: str,
        *,
        observed_at: datetime | None = None,
    ) -> CatalogueIngestionRun:
        run = self._run_for_update(run_id)
        if run is None or not self._run_lease_matches(
            run, lease_token, observed_at=observed_at or datetime.now(UTC)
        ):
            raise CatalogueLeaseLost("run_lease_lost")
        return run

    @staticmethod
    def _run_lease_matches(
        run: CatalogueIngestionRun,
        lease_token: str,
        *,
        observed_at: datetime,
    ) -> bool:
        return (
            run.lease_token == lease_token
            and run.lease_expires_at is not None
            and _as_utc(run.lease_expires_at) >= _as_utc(observed_at)
            and run.status not in _TERMINAL_RUN_STATUSES
        )

    @staticmethod
    def _candidate_lease_matches(
        candidate: CatalogueCandidate,
        *,
        worker_id: str,
        lease_token: str,
        observed_at: datetime,
    ) -> bool:
        return (
            candidate.claimed_by == worker_id
            and candidate.lease_token == lease_token
            and candidate.claimed_until is not None
            and _as_utc(candidate.claimed_until) >= _as_utc(observed_at)
        )

    def _assert_provider_attempt_ownership(
        self,
        attempt: CatalogueProviderAttempt,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
    ) -> None:
        observed_at = datetime.now(UTC)
        run = self._run_for_update(attempt.run_id)
        candidate = self._candidate_for_update(attempt.candidate_id)
        if (
            run is None
            or candidate is None
            or not self._run_lease_matches(run, run_lease_token, observed_at=observed_at)
            or not self._candidate_lease_matches(
                candidate,
                worker_id=worker_id,
                lease_token=candidate_lease_token,
                observed_at=observed_at,
            )
            or attempt.worker_id != worker_id
            or attempt.lease_token != candidate_lease_token
            or (attempt.metadata_json or {}).get("run_lease_token") != run_lease_token
        ):
            raise CatalogueLeaseLost("provider_attempt_lease_lost")

    def _owned_job(
        self,
        job_id: uuid.UUID,
        *,
        worker_id: str,
        run_lease_token: str,
        candidate_lease_token: str,
    ) -> CatalogueResumableJob:
        with self.session.no_autoflush:
            job = self.session.scalar(
                select(CatalogueResumableJob)
                .where(CatalogueResumableJob.id == job_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        if (
            job is None
            or job.worker_id != worker_id
            or job.run_lease_token != run_lease_token
            or job.candidate_lease_token != candidate_lease_token
        ):
            raise CatalogueLeaseLost("resumable_job_lease_lost")
        self.assert_candidate_lease(
            job.candidate_id,
            run_lease_token=run_lease_token,
            worker_id=worker_id,
            lease_token=candidate_lease_token,
        )
        return job


def candidate_idempotency_key(seed: SeedCandidate, *, run_id: uuid.UUID | None = None) -> str:
    normalized = "|".join(
        _normalize(value)
        for value in (
            str(run_id) if run_id is not None else None,
            seed.name,
            seed.provider,
            seed.university,
            seed.country,
            seed.cycle,
            str(seed.intake_year) if seed.intake_year is not None else None,
            str(seed.possible_official_url) if seed.possible_official_url else None,
        )
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def _normalize(value: str | None) -> str:
    return re.sub(r"\W+", " ", value or "").strip().casefold()
