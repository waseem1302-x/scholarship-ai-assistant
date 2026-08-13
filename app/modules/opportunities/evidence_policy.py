"""Shared evidence-source selection rules for opportunity consumers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from app.modules.opportunities.models import Source, SourceType, VerificationStatus


class EvidencePolicy:
    DISQUALIFYING_OFFICIAL_STATUSES: ClassVar[set[VerificationStatus]] = {
        VerificationStatus.ARCHIVED,
        VerificationStatus.CONFLICTING_INFORMATION,
        VerificationStatus.EXPIRED,
    }

    @classmethod
    def has_disqualifying_official_source(cls, sources: list[Source]) -> bool:
        return any(
            source.source_type is SourceType.OFFICIAL
            and source.verification_status in cls.DISQUALIFYING_OFFICIAL_STATUSES
            for source in sources
        )

    @classmethod
    def select_current_official_source(
        cls,
        sources: list[Source],
        *,
        require_fresh_days: int | None = None,
        reject_conflicts: bool = True,
        now: datetime | None = None,
    ) -> Source | None:
        if reject_conflicts and cls.has_disqualifying_official_source(sources):
            return None
        candidates = [
            source
            for source in sources
            if source.source_type is SourceType.OFFICIAL
            and source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
        ]
        if require_fresh_days is not None:
            candidates = [
                source
                for source in candidates
                if cls.source_is_fresh(source, freshness_days=require_fresh_days, now=now)
            ]
        return max(
            candidates,
            key=lambda source: source.last_verified_at or source.date_collected,
            default=None,
        )

    @classmethod
    def select_review_source(cls, sources: list[Source]) -> Source | None:
        current = cls.select_current_official_source(sources, reject_conflicts=False)
        if current is not None:
            return current
        official = [source for source in sources if source.source_type is SourceType.OFFICIAL]
        return max(
            official or sources,
            key=lambda source: source.last_verified_at or source.date_collected,
            default=None,
        )

    @classmethod
    def source_can_publish(cls, source: Source) -> bool:
        return (
            source.source_type is SourceType.OFFICIAL
            and source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
        )

    @staticmethod
    def source_is_fresh(
        source: Source,
        *,
        freshness_days: int,
        now: datetime | None = None,
    ) -> bool:
        verified_at = source.last_verified_at
        if verified_at is None:
            return False
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        return verified_at >= (now or datetime.now(UTC)) - timedelta(days=freshness_days)
