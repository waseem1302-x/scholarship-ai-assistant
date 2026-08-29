"""Bounded database access for ingestion workers and administrator views."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
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


class ProviderBudgetReservationError(RuntimeError):
    """A physical provider attempt cannot be reserved inside the run budget."""


class CatalogueIngestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_run(self, run: CatalogueIngestionRun) -> None:
        self.session.add(run)
        self.session.flush()

    def get_run(self, run_id: uuid.UUID) -> CatalogueIngestionRun | None:
        return self.session.get(CatalogueIngestionRun, run_id)

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
        worker_id: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> list[CatalogueCandidate]:
        observed_at = now or datetime.now(UTC)
        statement = (
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
            .order_by(CatalogueCandidate.seed_index)
            .limit(limit)
            .options(
                selectinload(CatalogueCandidate.sources).selectinload(
                    CatalogueCandidateSource.artifacts
                )
            )
            .with_for_update(skip_locked=True)
        )
        candidates = list(self.session.scalars(statement))
        claimed_until = observed_at + timedelta(seconds=lease_seconds)
        for candidate in candidates:
            candidate.claimed_by = worker_id
            candidate.claimed_until = claimed_until
            candidate.attempt_count += 1
        self.session.commit()
        return candidates

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
        return self.session.scalar(
            select(CatalogueCandidate)
            .where(CatalogueCandidate.id == candidate_id)
            .options(
                selectinload(CatalogueCandidate.sources).selectinload(
                    CatalogueCandidateSource.artifacts
                )
            )
            .with_for_update()
        )

    def release_candidate(self, candidate: CatalogueCandidate) -> None:
        candidate.claimed_by = None
        candidate.claimed_until = None

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
        worker_id: str | None,
        lease_token: str | None,
        reserved_cost_upper: Decimal,
    ) -> CatalogueProviderAttempt:
        """Reserve one physical attempt atomically against call and upper-cost budgets."""

        run = self.session.scalar(
            select(CatalogueIngestionRun)
            .where(CatalogueIngestionRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise ProviderBudgetReservationError("ingestion_run_missing")

        existing_call_count = self.session.scalar(
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
        ) or 0
        if existing_call_count >= run.max_model_calls:
            raise ProviderBudgetReservationError("provider_call_budget_exhausted")

        current_upper = self.session.scalar(
            select(func.coalesce(func.sum(CatalogueProviderAttempt.cost_upper_bound), 0)).where(
                CatalogueProviderAttempt.run_id == run_id
            )
        )
        current_upper_decimal = Decimal(str(current_upper or 0))
        if current_upper_decimal + reserved_cost_upper > run.max_estimated_cost:
            raise ProviderBudgetReservationError("provider_cost_budget_exhausted")

        retry_ordinal = self.session.scalar(
            select(func.count())
            .select_from(CatalogueProviderAttempt)
            .where(CatalogueProviderAttempt.extraction_job_key == extraction_job_key)
        ) or 0
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
        )
        self.session.add(attempt)
        self.session.flush()
        self.refresh_provider_accounting(run)
        self.session.commit()
        return attempt

    def mark_provider_attempt_dispatching(self, attempt: CatalogueProviderAttempt) -> None:
        attempt.state = ProviderAttemptState.DISPATCHING
        attempt.dispatch_started_at = datetime.now(UTC)
        self.session.commit()

    def complete_provider_attempt(
        self,
        attempt: CatalogueProviderAttempt,
        *,
        input_tokens: int,
        output_tokens: int,
        exact_cost: Decimal,
        provider_request_id: str | None,
    ) -> None:
        attempt.state = ProviderAttemptState.SUCCEEDED
        attempt.dispatched_at = attempt.dispatched_at or attempt.dispatch_started_at or datetime.now(UTC)
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
        run = self.session.get(CatalogueIngestionRun, attempt.run_id)
        if run is not None:
            self.refresh_provider_accounting(run)
        self.session.commit()

    def fail_provider_attempt(
        self,
        attempt: CatalogueProviderAttempt,
        *,
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
        attempt.state = ProviderAttemptState.FAILED
        attempt.failure_class = failure_class
        attempt.error_code = error_code[:100]
        attempt.safe_error_detail = safe_error_detail[:1000]
        attempt.provider_request_id = provider_request_id
        attempt.completed_at = datetime.now(UTC)
        if dispatch_occurred:
            attempt.dispatched_at = attempt.dispatched_at or attempt.dispatch_started_at or datetime.now(UTC)
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
        run = self.session.get(CatalogueIngestionRun, attempt.run_id)
        if run is not None:
            self.refresh_provider_accounting(run)
        self.session.commit()

    def link_provider_attempt(
        self,
        provider_attempt_id: uuid.UUID,
        extraction_attempt_id: uuid.UUID,
    ) -> None:
        attempt = self.session.get(CatalogueProviderAttempt, provider_attempt_id)
        if attempt is None:
            return
        attempt.extraction_attempt_id = extraction_attempt_id
        self.session.flush()

    def refresh_provider_accounting(self, run: CatalogueIngestionRun) -> None:
        count = self.session.scalar(
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
        ) or 0
        input_tokens = self.session.scalar(
            select(func.coalesce(func.sum(CatalogueProviderAttempt.input_tokens), 0)).where(
                CatalogueProviderAttempt.run_id == run.id
            )
        ) or 0
        output_tokens = self.session.scalar(
            select(func.coalesce(func.sum(CatalogueProviderAttempt.output_tokens), 0)).where(
                CatalogueProviderAttempt.run_id == run.id
            )
        ) or 0
        lower = self.session.scalar(
            select(func.coalesce(func.sum(CatalogueProviderAttempt.cost_lower_bound), 0)).where(
                CatalogueProviderAttempt.run_id == run.id
            )
        ) or 0
        upper = self.session.scalar(
            select(func.coalesce(func.sum(CatalogueProviderAttempt.cost_upper_bound), 0)).where(
                CatalogueProviderAttempt.run_id == run.id
            )
        ) or 0
        uncertain = self.session.scalar(
            select(func.count())
            .select_from(CatalogueProviderAttempt)
            .where(
                CatalogueProviderAttempt.run_id == run.id,
                CatalogueProviderAttempt.accounting_state
                == ProviderAccountingState.UNKNOWN_POTENTIALLY_BILLABLE,
            )
        ) or 0

        run.model_calls = int(count)
        run.input_tokens = int(input_tokens)
        run.output_tokens = int(output_tokens)
        # Legacy ``estimated_cost`` remains a conservative projection for existing API clients.
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
        provider_summary = {
            key: value
            for key, value in (run.aggregate_summary or {}).items()
            if key.startswith("provider_")
        }
        run.aggregate_summary = {
            **{status.value: count for status, count in counts},
            **provider_summary,
        }
        self.refresh_provider_accounting(run)
        if (
            not any(status in PROCESSABLE_STATUSES and count for status, count in counts)
            and run.status is IngestionRunStatus.RUNNING
        ):
            run.status = IngestionRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)


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
