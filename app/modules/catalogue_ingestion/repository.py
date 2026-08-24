"""Bounded database access for ingestion workers and administrator views."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    CatalogueSourceArtifact,
    CatalogueSourceRoutingDecision,
    ExtractionAttemptStatus,
    IngestionRunRetryClass,
    IngestionRunStage,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.schemas import SeedCandidate

PROCESSABLE_STATUSES = {
    CandidateStatus.DISCOVERED,
    CandidateStatus.OFFICIAL_SOURCE_CANDIDATE,
    CandidateStatus.SOURCE_FETCHED,
    CandidateStatus.EXTRACTED,
}

RUNNABLE_STATUSES = {
    IngestionRunStatus.PENDING,
    IngestionRunStatus.RUNNING,
}


class CatalogueIngestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_run(self, run: CatalogueIngestionRun) -> None:
        self.session.add(run)
        self.session.flush()

    def routing_decision(
        self, *, artifact: CatalogueSourceArtifact, classifier_version: str
    ) -> CatalogueSourceRoutingDecision | None:
        return self.session.scalar(
            select(CatalogueSourceRoutingDecision).where(
                CatalogueSourceRoutingDecision.artifact_id == artifact.id,
                CatalogueSourceRoutingDecision.classifier_version == classifier_version,
            )
        )

    def get_or_create_run(self, run: CatalogueIngestionRun) -> tuple[CatalogueIngestionRun, bool]:
        """Create one logical run per idempotency key, including concurrent enqueues."""

        existing = self.session.scalar(
            select(CatalogueIngestionRun).where(
                CatalogueIngestionRun.idempotency_key == run.idempotency_key
            )
        )
        if existing is not None:
            return existing, False
        try:
            with self.session.begin_nested():
                self.session.add(run)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(CatalogueIngestionRun).where(
                    CatalogueIngestionRun.idempotency_key == run.idempotency_key
                )
            )
            if existing is None:
                raise
            return existing, False
        return run, True

    def get_run(self, run_id: uuid.UUID) -> CatalogueIngestionRun | None:
        return self.session.get(CatalogueIngestionRun, run_id)

    def claim_runs(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> list[CatalogueIngestionRun]:
        """Claim due work with a fresh opaque fencing token per run."""

        observed_at = now or datetime.now(UTC)
        statement = (
            select(CatalogueIngestionRun)
            .where(
                CatalogueIngestionRun.status.in_(RUNNABLE_STATUSES),
                or_(
                    CatalogueIngestionRun.next_attempt_at.is_(None),
                    CatalogueIngestionRun.next_attempt_at <= observed_at,
                ),
                or_(
                    CatalogueIngestionRun.claimed_until.is_(None),
                    CatalogueIngestionRun.claimed_until < observed_at,
                ),
            )
            .order_by(CatalogueIngestionRun.created_at, CatalogueIngestionRun.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        runs = list(self.session.scalars(statement))
        claimed_until = observed_at + timedelta(seconds=lease_seconds)
        for run in runs:
            run.status = IngestionRunStatus.RUNNING
            run.stage = IngestionRunStage.ACQUIRING
            run.claimed_by = worker_id
            run.claimed_at = observed_at
            run.claimed_until = claimed_until
            run.lease_token = uuid.uuid4().hex
            run.attempt_count += 1
            run.failure_code = None
            run.last_error_reason = None
            run.retry_class = None
            run.started_at = run.started_at or observed_at
        self.session.commit()
        return runs

    def claim_run(
        self,
        run_id: uuid.UUID,
        *,
        worker_id: str,
        lease_seconds: int,
        now: datetime | None = None,
        allow_budget_resume: bool = False,
    ) -> CatalogueIngestionRun | None:
        """Claim one requested run for the CLI/test resume path."""

        observed_at = now or datetime.now(UTC)
        statuses = set(RUNNABLE_STATUSES)
        if allow_budget_resume:
            statuses.add(IngestionRunStatus.BUDGET_EXHAUSTED)
        run = self.session.scalar(
            select(CatalogueIngestionRun)
            .where(
                CatalogueIngestionRun.id == run_id,
                CatalogueIngestionRun.status.in_(statuses),
                or_(
                    CatalogueIngestionRun.next_attempt_at.is_(None),
                    CatalogueIngestionRun.next_attempt_at <= observed_at,
                ),
                or_(
                    CatalogueIngestionRun.claimed_until.is_(None),
                    CatalogueIngestionRun.claimed_until < observed_at,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        if run is None:
            return None
        run.status = IngestionRunStatus.RUNNING
        run.stage = IngestionRunStage.ACQUIRING
        run.claimed_by = worker_id
        run.claimed_at = observed_at
        run.claimed_until = observed_at + timedelta(seconds=lease_seconds)
        run.lease_token = uuid.uuid4().hex
        run.attempt_count += 1
        run.failure_code = None
        run.last_error_reason = None
        run.retry_class = None
        run.started_at = run.started_at or observed_at
        self.session.commit()
        return run

    def renew_run_claim(
        self,
        run_id: uuid.UUID,
        *,
        lease_token: str,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        observed_at = now or datetime.now(UTC)
        result = self.session.execute(
            update(CatalogueIngestionRun)
            .where(
                CatalogueIngestionRun.id == run_id,
                CatalogueIngestionRun.status == IngestionRunStatus.RUNNING,
                CatalogueIngestionRun.lease_token == lease_token,
            )
            .values(claimed_until=observed_at + timedelta(seconds=lease_seconds))
        )
        self.session.commit()
        return result.rowcount == 1

    def complete_run_claim(self, run_id: uuid.UUID, *, lease_token: str) -> bool:
        completed_at = datetime.now(UTC)
        result = self.session.execute(
            update(CatalogueIngestionRun)
            .where(
                CatalogueIngestionRun.id == run_id,
                CatalogueIngestionRun.status == IngestionRunStatus.RUNNING,
                CatalogueIngestionRun.lease_token == lease_token,
            )
            .values(
                status=IngestionRunStatus.COMPLETED,
                stage=IngestionRunStage.COMPLETE,
                completed_at=completed_at,
                claimed_by=None,
                claimed_at=None,
                claimed_until=None,
                lease_token=None,
                next_attempt_at=None,
            )
        )
        self.session.commit()
        return result.rowcount == 1

    def budget_exhausted_run_claim(self, run_id: uuid.UUID, *, lease_token: str) -> bool:
        result = self.session.execute(
            update(CatalogueIngestionRun)
            .where(
                CatalogueIngestionRun.id == run_id,
                CatalogueIngestionRun.status == IngestionRunStatus.RUNNING,
                CatalogueIngestionRun.lease_token == lease_token,
            )
            .values(
                status=IngestionRunStatus.BUDGET_EXHAUSTED,
                stage=IngestionRunStage.RESOLVING,
                failure_code="run_budget_exhausted",
                claimed_by=None,
                claimed_at=None,
                claimed_until=None,
                lease_token=None,
            )
        )
        self.session.commit()
        return result.rowcount == 1

    def fail_run_claim(
        self,
        run_id: uuid.UUID,
        *,
        lease_token: str,
        error_code: str,
        error_reason: str,
        retry_class: IngestionRunRetryClass,
        retry_delay_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        observed_at = now or datetime.now(UTC)
        run = self.session.scalar(
            select(CatalogueIngestionRun)
            .where(
                CatalogueIngestionRun.id == run_id,
                CatalogueIngestionRun.status == IngestionRunStatus.RUNNING,
                CatalogueIngestionRun.lease_token == lease_token,
            )
            .with_for_update()
        )
        if run is None:
            return False
        terminal = retry_class is IngestionRunRetryClass.PERMANENT or (
            run.attempt_count >= run.max_attempts
        )
        run.failure_code = error_code[:100]
        run.last_error_reason = error_reason[:2000]
        run.retry_class = retry_class
        run.claimed_by = None
        run.claimed_at = None
        run.claimed_until = None
        run.lease_token = None
        if terminal:
            run.status = IngestionRunStatus.DEAD_LETTER
            run.stage = IngestionRunStage.DEAD_LETTER
            run.dead_lettered_at = observed_at
            run.completed_at = observed_at
            run.next_attempt_at = None
        else:
            run.status = IngestionRunStatus.PENDING
            run.stage = IngestionRunStage.QUEUED
            run.next_attempt_at = observed_at + timedelta(seconds=retry_delay_seconds)
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
        run.aggregate_summary = {status.value: count for status, count in counts}


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
