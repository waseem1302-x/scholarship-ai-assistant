"""Versioned, backend-owned publication-readiness policy.

Publication requires complete facts *and* exact field-level evidence from fresh,
hash-backed, ownership-resolved official sources.  Confidence is intentionally
not part of this policy: it can prioritize review, but it cannot prove a fact.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.opportunities.evidence_models import (
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    OfficialityStatus,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.lifecycle import SOURCE_FRESHNESS_DAYS
from app.modules.opportunities.models import (
    DuplicateSuggestion,
    DuplicateSuggestionStatus,
    FundingClassification,
    FundingCoverageStatus,
    IndependenceStatus,
    Opportunity,
    PublicationFactState,
    Source,
    SourceType,
    VerificationStatus,
)

PUBLICATION_READINESS_POLICY_VERSION = "publication-readiness.v1"
PUBLICATION_COMPLETE_STATES = frozenset({"complete_core", "complete_graph"})


class PublicationReadinessReason(BaseModel):
    field_path: str
    reason_code: str
    message: str
    source_id: uuid.UUID | None = None


class PublicationFieldResult(BaseModel):
    field_path: str
    state: PublicationFactState
    supported: bool
    source_ids: list[uuid.UUID] = Field(default_factory=list)


class PublicationReadiness(BaseModel):
    ready: bool
    blocking_reasons: list[PublicationReadinessReason]
    warnings: list[PublicationReadinessReason]
    supported_required_count: int
    required_count: int
    evaluated_at: datetime
    policy_version: str
    valid_until: datetime | None = None
    field_results: list[PublicationFieldResult] = Field(default_factory=list)


class _EvidenceRow:
    def __init__(self, evidence: FieldEvidence, snapshot: SourceSnapshot, source: Source) -> None:
        self.evidence = evidence
        self.snapshot = snapshot
        self.source = source


class PublicationReadinessPolicy:
    """Evaluate the mandatory catalogue contract from database truth."""

    REQUIRED_DIMENSIONS = (
        "identity_family",
        "provider_country",
        "degree_route_scope",
        "cycle",
        "deadline",
        "application",
        "tuition",
        "stipend",
        "funding_classification",
        "nationality_geography",
        "academic_requirement",
        "language_tests",
        "required_documents",
        "official_artifacts",
        "conflicts_duplicates",
    )
    LEGITIMATE_SEMANTIC_STATES: ClassVar[set[PublicationFactState]] = {
        PublicationFactState.ROLLING,
        PublicationFactState.VARIES_BY_COUNTRY,
        PublicationFactState.NOT_YET_ANNOUNCED,
        PublicationFactState.NOT_APPLICABLE,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self,
        opportunity: Opportunity,
        *,
        prospective_source_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> PublicationReadiness:
        evaluated_at = self._as_utc(now or datetime.now(UTC))
        evidence_rows = self._evidence_rows(opportunity.id)
        blockers: list[PublicationReadinessReason] = []
        warnings: list[PublicationReadinessReason] = []
        results: list[PublicationFieldResult] = []

        def block(
            field_path: str,
            reason_code: str,
            message: str,
            source_id: uuid.UUID | None = None,
        ) -> None:
            blockers.append(
                PublicationReadinessReason(
                    field_path=field_path,
                    reason_code=reason_code,
                    message=message,
                    source_id=source_id,
                )
            )

        def check(
            field_path: str,
            *,
            value_ok: bool,
            aliases: tuple[str, ...],
            missing_code: str,
            missing_message: str,
            state: PublicationFactState = PublicationFactState.SUPPORTED,
            extra_aliases: tuple[tuple[str, ...], ...] = (),
        ) -> None:
            if not value_ok:
                block(field_path, missing_code, missing_message)
                results.append(
                    PublicationFieldResult(
                        field_path=field_path,
                        state=PublicationFactState.UNKNOWN,
                        supported=False,
                    )
                )
                return
            source_ids: set[uuid.UUID] = set()
            groups = (aliases, *extra_aliases)
            for group in groups:
                valid = self._valid_evidence(
                    evidence_rows,
                    group,
                    prospective_source_id=prospective_source_id,
                    now=evaluated_at,
                )
                if not valid:
                    matching = self._matching_evidence(evidence_rows, group)
                    source_id = matching[0].source.id if matching else None
                    block(
                        field_path,
                        "evidence_invalid" if matching else "evidence_missing",
                        (
                            f"{field_path} evidence is not exact, passed, fresh, and official."
                            if matching
                            else f"{field_path} has no field-level official evidence."
                        ),
                        source_id,
                    )
                    results.append(
                        PublicationFieldResult(
                            field_path=field_path,
                            state=state,
                            supported=False,
                            source_ids=sorted(source_ids, key=str),
                        )
                    )
                    return
                source_ids.update(row.source.id for row in valid)
            results.append(
                PublicationFieldResult(
                    field_path=field_path,
                    state=state,
                    supported=True,
                    source_ids=sorted(source_ids, key=str),
                )
            )

        family_present = self._nonempty(opportunity.programme_family_id)
        check(
            "identity_family",
            value_ok=self._nonempty(opportunity.name) and family_present,
            aliases=("name", "identity.name"),
            missing_code="identity_family_missing",
            missing_message="Scholarship identity and programme family are required.",
        )
        check(
            "provider_country",
            value_ok=self._nonempty(opportunity.provider.name)
            and self._nonempty(opportunity.country),
            aliases=("provider_name", "provider.name", "identity.provider_name"),
            extra_aliases=(("country", "identity.country"),),
            missing_code="provider_country_missing",
            missing_message="Provider and destination country are required.",
        )
        route_present = bool(
            self._nonempty(opportunity.canonical_slug)
            or self._nonempty(opportunity.programme_family_id)
        )
        check(
            "degree_route_scope",
            value_ok=bool(opportunity.degree_level) and route_present,
            aliases=("degree_level", "study.degree_level"),
            extra_aliases=(("route", "route_scope", "programme_family_id", "scope.route"),),
            missing_code="route_scope_missing",
            missing_message="Degree and route scope are required.",
        )

        cycle_state = self._cycle_state(opportunity)
        check(
            "cycle",
            value_ok=cycle_state is not PublicationFactState.UNKNOWN,
            aliases=("cycle", "cycle_id", "intake_year", "status", "cycle.status"),
            missing_code="cycle_unknown",
            missing_message="A current cycle or evidenced cycle semantic state is required.",
            state=cycle_state,
        )
        deadline_state = self._deadline_state(opportunity)
        check(
            "deadline",
            value_ok=deadline_state is not PublicationFactState.UNKNOWN,
            aliases=(
                "application_deadline",
                "deadline_at",
                "deadline",
                "is_rolling",
                "deadline_state",
            ),
            missing_code="deadline_unknown",
            missing_message="A deadline, rolling state, or scoped deadline rule is required.",
            state=deadline_state,
        )
        check(
            "application",
            value_ok=self._nonempty(opportunity.application_url)
            and self._nonempty(opportunity.application_method),
            aliases=("application_url", "application.application_url", "url"),
            extra_aliases=(("application_method", "application.application_method", "method"),),
            missing_code=(
                "application_url_missing"
                if not self._nonempty(opportunity.application_url)
                else "application_method_missing"
            ),
            missing_message="Official application URL and method are required.",
        )
        tuition_known = opportunity.tuition_coverage_status is not FundingCoverageStatus.UNKNOWN
        check(
            "tuition",
            value_ok=tuition_known
            and bool(
                self._nonempty(opportunity.tuition_coverage)
                or self._nonempty(opportunity.funding_policy)
            ),
            aliases=("tuition_coverage_status", "funding.tuition.status", "coverage_status"),
            extra_aliases=(("tuition_coverage", "funding_policy", "description"),),
            missing_code="tuition_unknown",
            missing_message="Tuition coverage status and official wording are required.",
        )
        stipend_known = opportunity.stipend_coverage_status is not FundingCoverageStatus.UNKNOWN
        stipend_amount_valid = opportunity.monthly_stipend_amount is None or bool(
            self._nonempty(opportunity.monthly_stipend_currency)
        )
        stipend_extra = (
            (("monthly_stipend_amount", "funding.stipend.amount", "amount"),)
            if opportunity.monthly_stipend_amount is not None
            else ()
        )
        check(
            "stipend",
            value_ok=stipend_known and stipend_amount_valid,
            aliases=("stipend_coverage_status", "funding.stipend.status", "coverage_status"),
            extra_aliases=stipend_extra,
            missing_code="stipend_unknown",
            missing_message="Stipend status and amount/currency when present are required.",
        )
        expected_classification = self._recompute_funding_classification(opportunity)
        check(
            "funding_classification",
            value_ok=expected_classification is not FundingClassification.UNKNOWN
            and opportunity.funding_classification is expected_classification,
            aliases=("funding_classification", "funding_policy", "funding.classification"),
            missing_code="funding_classification_mismatch",
            missing_message="Funding classification must be recomputed from supported components.",
        )
        check(
            "nationality_geography",
            value_ok=self._nonempty(opportunity.nationality_eligibility),
            aliases=("nationality_eligibility", "eligibility.nationality_eligibility"),
            missing_code="nationality_missing",
            missing_message="Nationality or geography eligibility coverage is required.",
        )
        check(
            "academic_requirement",
            value_ok=self._nonempty(opportunity.minimum_academic_requirement),
            aliases=("minimum_academic_requirement", "eligibility.minimum_academic_requirement"),
            missing_code="academic_requirement_missing",
            missing_message="Academic requirement or an evidenced variation state is required.",
        )
        language_present = bool(
            self._nonempty(opportunity.english_language_requirement)
            or self._nonempty(opportunity.standardized_test_requirement)
        )
        check(
            "language_tests",
            value_ok=language_present,
            aliases=(
                "english_language_requirement",
                "standardized_test_requirement",
                "eligibility.english_language_requirement",
                "eligibility.standardized_test_requirement",
            ),
            missing_code="language_tests_missing",
            missing_message="Language/test requirements or exceptions are required.",
        )
        check(
            "required_documents",
            value_ok=bool(opportunity.required_documents),
            aliases=("required_documents", "document_key", "documents", "name"),
            missing_code="documents_missing",
            missing_message="Required-document coverage for the route is required.",
        )

        eligible_sources = [
            source
            for source in opportunity.sources
            if self._source_is_eligible(
                source,
                prospective_source_id=prospective_source_id,
                now=evaluated_at,
            )
            and any(
                snapshot.source_id == source.id and snapshot.content_hash == source.content_hash
                for row in evidence_rows
                for snapshot in (row.snapshot,)
            )
        ]
        if not eligible_sources:
            block(
                "official_artifacts",
                self._source_failure_code(opportunity.sources, evaluated_at),
                "A fresh, active, owned, hash-backed official artifact is required.",
            )
        results.append(
            PublicationFieldResult(
                field_path="official_artifacts",
                state=(
                    PublicationFactState.SUPPORTED
                    if eligible_sources
                    else PublicationFactState.UNKNOWN
                ),
                supported=bool(eligible_sources),
                source_ids=sorted((source.id for source in eligible_sources), key=str),
            )
        )

        conflict_rows = [
            row
            for row in evidence_rows
            if row.evidence.support_type is EvidenceSupportType.CONTRADICTS
            and row.evidence.validator_status is EvidenceValidatorStatus.PASSED
        ]
        conflicting_source = next(
            (
                source
                for source in opportunity.sources
                if source.verification_status is VerificationStatus.CONFLICTING_INFORMATION
                and source.id != prospective_source_id
            ),
            None,
        )
        pending_duplicate = self.session.scalar(
            select(DuplicateSuggestion).where(
                or_(
                    DuplicateSuggestion.opportunity_id == opportunity.id,
                    DuplicateSuggestion.matched_opportunity_id == opportunity.id,
                ),
                DuplicateSuggestion.status == DuplicateSuggestionStatus.PENDING,
            )
        )
        independence_ok = (
            opportunity.independence_status is IndependenceStatus.CONFIRMED_INDEPENDENT
        )
        conflict_ok = not conflict_rows and conflicting_source is None and pending_duplicate is None
        if not independence_ok:
            block(
                "conflicts_duplicates",
                "independence_unresolved",
                "Route independence must be confirmed before publication.",
            )
        if conflict_rows:
            block(
                "conflicts_duplicates",
                "evidence_conflict",
                "Contradictory passed field evidence must be resolved.",
                conflict_rows[0].source.id,
            )
        if conflicting_source is not None:
            block(
                "conflicts_duplicates",
                "official_source_conflict",
                "An official source is marked as conflicting.",
                conflicting_source.id,
            )
        if pending_duplicate is not None:
            block(
                "conflicts_duplicates",
                "duplicate_pending",
                "A pending duplicate suggestion must be resolved.",
            )
        results.append(
            PublicationFieldResult(
                field_path="conflicts_duplicates",
                state=(
                    PublicationFactState.SUPPORTED
                    if independence_ok and conflict_ok
                    else PublicationFactState.UNKNOWN
                ),
                supported=independence_ok and conflict_ok,
            )
        )

        if opportunity.field_eligibility is None:
            warnings.append(
                PublicationReadinessReason(
                    field_path="field_eligibility",
                    reason_code="optional_field_eligibility_missing",
                    message="Field-of-study guidance is absent.",
                )
            )

        if self._contains_admin_only_unknown(opportunity):
            block(
                "public_serialization",
                "admin_only_unknown_placeholder",
                "Admin-only unknown placeholders cannot be emitted by public serializers.",
            )

        supported_count = sum(result.supported for result in results)
        expiry_candidates = [
            self._source_valid_until(source, prospective_source_id, evaluated_at)
            for source in eligible_sources
        ]
        valid_until = min(expiry_candidates) if expiry_candidates else None
        return PublicationReadiness(
            ready=not blockers and supported_count == len(self.REQUIRED_DIMENSIONS),
            blocking_reasons=blockers,
            warnings=warnings,
            supported_required_count=supported_count,
            required_count=len(self.REQUIRED_DIMENSIONS),
            evaluated_at=evaluated_at,
            policy_version=PUBLICATION_READINESS_POLICY_VERSION,
            valid_until=valid_until,
            field_results=results,
        )

    def _evidence_rows(self, opportunity_id: uuid.UUID) -> list[_EvidenceRow]:
        rows = self.session.execute(
            select(FieldEvidence, SourceSnapshot, Source)
            .join(SourceSnapshot, SourceSnapshot.id == FieldEvidence.source_snapshot_id)
            .join(Source, Source.id == SourceSnapshot.source_id)
            .where(
                FieldEvidence.entity_id == opportunity_id,
                FieldEvidence.entity_type.in_(["opportunity", "scholarship"]),
                Source.opportunity_id == opportunity_id,
            )
        ).all()
        return [_EvidenceRow(evidence, snapshot, source) for evidence, snapshot, source in rows]

    def _valid_evidence(
        self,
        rows: Iterable[_EvidenceRow],
        aliases: tuple[str, ...],
        *,
        prospective_source_id: uuid.UUID | None,
        now: datetime,
    ) -> list[_EvidenceRow]:
        return [
            row
            for row in self._matching_evidence(rows, aliases)
            if row.evidence.support_type is EvidenceSupportType.EXPLICIT
            and row.evidence.validator_status is EvidenceValidatorStatus.PASSED
            and row.snapshot.content_hash == row.source.content_hash
            and 0
            <= row.evidence.excerpt_start
            <= row.evidence.excerpt_end
            <= len(row.snapshot.normalized_text)
            and row.snapshot.normalized_text[row.evidence.excerpt_start : row.evidence.excerpt_end]
            == row.evidence.excerpt
            and self._source_is_eligible(
                row.source,
                prospective_source_id=prospective_source_id,
                now=now,
            )
        ]

    @classmethod
    def _matching_evidence(
        cls, rows: Iterable[_EvidenceRow], aliases: tuple[str, ...]
    ) -> list[_EvidenceRow]:
        return [row for row in rows if cls._path_matches(row.evidence.field_path, aliases)]

    @staticmethod
    def _path_matches(path: str, aliases: tuple[str, ...]) -> bool:
        normalized = path.strip().casefold()
        return any(
            normalized == alias.casefold() or normalized.endswith(f".{alias.casefold()}")
            for alias in aliases
        )

    @classmethod
    def _source_is_eligible(
        cls,
        source: Source,
        *,
        prospective_source_id: uuid.UUID | None,
        now: datetime,
    ) -> bool:
        prospectively_verified = source.id == prospective_source_id
        verified_at = now if prospectively_verified else source.last_verified_at
        return bool(
            source.is_active
            and source.source_type is SourceType.OFFICIAL
            and source.officiality_status
            in {OfficialityStatus.OFFICIAL, OfficialityStatus.SUPPORTING_OFFICIAL}
            and source.source_owner_type is not SourceOwnerType.UNKNOWN
            and source.content_hash
            and (
                prospectively_verified
                or source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
            )
            and verified_at is not None
            and cls._as_utc(verified_at) >= now - timedelta(days=SOURCE_FRESHNESS_DAYS)
        )

    @classmethod
    def _source_failure_code(cls, sources: list[Source], now: datetime) -> str:
        if not sources:
            return "official_source_missing"
        if any(
            source.verification_status is VerificationStatus.CONFLICTING_INFORMATION
            for source in sources
        ):
            return "official_source_conflict"
        if any(
            source.last_verified_at is not None
            and cls._as_utc(source.last_verified_at) < now - timedelta(days=SOURCE_FRESHNESS_DAYS)
            for source in sources
        ):
            return "source_stale"
        if any(
            source.officiality_status is OfficialityStatus.UNRESOLVED
            or source.source_owner_type is SourceOwnerType.UNKNOWN
            for source in sources
        ):
            return "official_ownership_unresolved"
        if any(not source.content_hash for source in sources):
            return "source_hash_missing"
        return "official_artifact_invalid"

    @staticmethod
    def _cycle_state(opportunity: Opportunity) -> PublicationFactState:
        current = PublicationReadinessPolicy._effective_cycle(opportunity)
        raw_state = current.status if current is not None else None
        if raw_state:
            try:
                state = PublicationFactState(raw_state)
            except ValueError:
                state = PublicationFactState.SUPPORTED
            if state is not PublicationFactState.UNKNOWN:
                return state
        if opportunity.cycle_id or opportunity.intake_year or current is not None:
            return PublicationFactState.SUPPORTED
        return PublicationFactState.UNKNOWN

    @classmethod
    def _deadline_state(cls, opportunity: Opportunity) -> PublicationFactState:
        current = cls._effective_cycle(opportunity)
        if opportunity.application_deadline or (
            current is not None and current.application_deadline is not None
        ):
            return PublicationFactState.SUPPORTED
        if opportunity.catalogue_is_rolling or (current is not None and current.is_rolling):
            return PublicationFactState.ROLLING
        if current and current.status:
            try:
                state = PublicationFactState(current.status)
            except ValueError:
                return PublicationFactState.UNKNOWN
            if state in cls.LEGITIMATE_SEMANTIC_STATES:
                return state
        return PublicationFactState.UNKNOWN

    @staticmethod
    def _effective_cycle(opportunity: Opportunity) -> Any | None:
        if not opportunity.cycles:
            return None
        current = next((cycle for cycle in opportunity.cycles if cycle.is_current), None)
        if current is not None:
            return current
        active = [cycle for cycle in opportunity.cycles if not cycle.is_archived]
        return max(active or opportunity.cycles, key=lambda cycle: cycle.created_at)

    @staticmethod
    def _recompute_funding_classification(opportunity: Opportunity) -> FundingClassification:
        components = (
            opportunity.tuition_coverage_status,
            opportunity.stipend_coverage_status,
            opportunity.accommodation_coverage_status,
            opportunity.travel_coverage_status,
            opportunity.insurance_coverage_status,
            opportunity.fees_coverage_status,
        )
        if (
            opportunity.tuition_coverage_status is FundingCoverageStatus.CONFIRMED
            and opportunity.stipend_coverage_status is FundingCoverageStatus.CONFIRMED
            and bool(opportunity.funding_policy)
        ):
            return FundingClassification.FULLY_FUNDED
        if any(component is not FundingCoverageStatus.UNKNOWN for component in components):
            return FundingClassification.PARTIAL
        return FundingClassification.UNKNOWN

    @staticmethod
    def _nonempty(value: Any) -> bool:
        if value is None:
            return False
        normalized = str(value).strip().casefold()
        return bool(normalized) and normalized not in {
            "unknown",
            "not stated",
            "unknown — verify from official source",
            "unknown - verify from official source",
        }

    @staticmethod
    def _contains_admin_only_unknown(opportunity: Opportunity) -> bool:
        values: list[Any] = [
            opportunity.field_eligibility,
            opportunity.nationality_eligibility,
            opportunity.funding_policy,
            opportunity.tuition_coverage,
            opportunity.accommodation_coverage,
            opportunity.travel_allowance,
            opportunity.health_insurance,
            opportunity.application_fee_info,
            opportunity.english_language_requirement,
            opportunity.standardized_test_requirement,
            opportunity.minimum_academic_requirement,
            opportunity.application_method,
            opportunity.notes,
            *opportunity.required_documents,
            *opportunity.eligibility_warnings,
            *(source.relevant_excerpt for source in opportunity.sources),
        ]
        return any(
            isinstance(value, str) and "unknown — verify from official source" in value.casefold()
            for value in values
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _source_valid_until(
        cls,
        source: Source,
        prospective_source_id: uuid.UUID | None,
        now: datetime,
    ) -> datetime:
        verified_at = (
            now if source.id == prospective_source_id else cls._as_utc(source.last_verified_at)
        )
        return verified_at + timedelta(days=SOURCE_FRESHNESS_DAYS)


__all__ = [
    "PUBLICATION_COMPLETE_STATES",
    "PUBLICATION_READINESS_POLICY_VERSION",
    "PublicationFieldResult",
    "PublicationReadiness",
    "PublicationReadinessPolicy",
    "PublicationReadinessReason",
]
