"""Bounded database access for ingestion workers and administrator views."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
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
from app.modules.catalogue_ingestion.schemas import SeedCandidate

PROCESSABLE_STATUSES = {
    CandidateStatus.DISCOVERED,
    CandidateStatus.OFFICIAL_SOURCE_CANDIDATE,
    CandidateStatus.SOURCE_FETCHED,
    CandidateStatus.EXTRACTED,
}


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
    ) -> int:
        created = 0
        keyed_seeds = [
            (index, seed, candidate_idempotency_key(seed))
            for index, seed in enumerate(seeds, start=start_index)
        ]
        existing: set[str] = set()
        for offset in range(0, len(keyed_seeds), 500):
            keys = [key for _, _, key in keyed_seeds[offset : offset + 500]]
            existing.update(
                self.session.scalars(
                    select(CatalogueCandidate.idempotency_key).where(
                        CatalogueCandidate.idempotency_key.in_(keys)
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
            .options(selectinload(CatalogueCandidate.sources))
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
            .options(selectinload(CatalogueCandidate.sources))
        )

    def get_candidate_for_update(self, candidate_id: uuid.UUID) -> CatalogueCandidate | None:
        return self.session.scalar(
            select(CatalogueCandidate)
            .where(CatalogueCandidate.id == candidate_id)
            .options(selectinload(CatalogueCandidate.sources))
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
                base.options(selectinload(CatalogueCandidate.sources))
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
        if (
            not any(status in PROCESSABLE_STATUSES and count for status, count in counts)
            and run.status is IngestionRunStatus.RUNNING
        ):
            run.status = IngestionRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)


def candidate_idempotency_key(seed: SeedCandidate) -> str:
    normalized = "|".join(
        _normalize(value)
        for value in (
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
