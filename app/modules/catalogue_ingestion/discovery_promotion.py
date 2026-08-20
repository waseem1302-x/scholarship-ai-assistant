"""Authoritative safe-fetch promotion for a pre-bound discovery root."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.discovery import DiscoveryTargetIdentitySnapshot
from app.modules.catalogue_ingestion.discovery_binding import CatalogueDiscoveryBindingService
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryPromotion,
    CatalogueDiscoveryRun,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryStateError,
)
from app.modules.catalogue_ingestion.metrics import CatalogueMetrics
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
)
from app.modules.catalogue_ingestion.sources import OfficialSourceClassifier, SourceClassification
from app.modules.opportunities.graph_models import Institution
from app.modules.opportunities.models import Provider
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.source_monitor import (
    FetchedSource,
    SourceFetcher,
    SourceFetchError,
)

REDIRECT_ALIAS_FAILURE_CODE = "redirect_converged_to_existing_source"
TARGET_MISMATCH_FAILURE_CODE = "discovery_target_identity_mismatch"
UNOFFICIAL_REDIRECT_FAILURE_CODE = "redirected_to_unofficial_source"

GENERIC_IDENTITY_TOKENS = frozenset(
    {
        "award",
        "awards",
        "fellowship",
        "fellowships",
        "program",
        "programme",
        "programmes",
        "programs",
        "scheme",
        "scholarship",
        "scholarships",
        "the",
    }
)


class DiscoveryPromotionStatus(StrEnum):
    PROMOTED = "promoted"
    REUSED = "reused"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TargetContentVerification:
    accepted: bool
    matched_label: str | None
    reason_code: str


@dataclass(frozen=True)
class DiscoveryPromotionResult:
    status: DiscoveryPromotionStatus
    source: CatalogueCandidateSource
    promotion: CatalogueDiscoveryPromotion | None
    failure_code: str | None
    fetch_performed: bool


class CatalogueDiscoveryPromotionService:
    """Fetch and promote one Step 7 binding without entering extraction."""

    def __init__(
        self,
        session: Session,
        *,
        fetcher: SourceFetcher,
        classifier: OfficialSourceClassifier,
        reviewed_official_domains: set[str],
        metrics: CatalogueMetrics,
    ) -> None:
        self.session = session
        self.fetcher = fetcher
        self.classifier = classifier
        self.reviewed_official_domains = reviewed_official_domains
        self.metrics = metrics
        self.discovery = CatalogueDiscoveryRepository(session)
        self.opportunities = OpportunityRepository(session)

    def process(
        self,
        *,
        run_id: uuid.UUID,
        candidate_source_id: uuid.UUID,
    ) -> DiscoveryPromotionResult:
        run = self.session.scalar(
            select(CatalogueDiscoveryRun)
            .where(CatalogueDiscoveryRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        if run.dry_run:
            raise DiscoveryStateError("promotion_fetch_disabled_for_dry_run")
        if run.target_candidate_id is None:
            raise DiscoveryStateError("promotion_requires_explicit_target_candidate")

        candidate = self.session.scalar(
            select(CatalogueCandidate)
            .where(CatalogueCandidate.id == run.target_candidate_id)
            .with_for_update()
        )
        if candidate is None:
            raise DiscoveryStateError("promotion_target_candidate_not_found")
        bound_source = self.session.scalar(
            select(CatalogueCandidateSource)
            .where(
                CatalogueCandidateSource.id == candidate_source_id,
                CatalogueCandidateSource.candidate_id == candidate.id,
            )
            .with_for_update()
        )
        if bound_source is None or bound_source.discovery_lead_id is None:
            raise DiscoveryStateError("promotion_requires_prebound_candidate_source")
        existing = self.session.scalar(
            select(CatalogueDiscoveryPromotion).where(
                CatalogueDiscoveryPromotion.candidate_id == candidate.id,
                CatalogueDiscoveryPromotion.lead_id == bound_source.discovery_lead_id,
            )
        )
        if existing is not None:
            effective_source = self.session.get(
                CatalogueCandidateSource, existing.candidate_source_id
            )
            if effective_source is None:
                raise DiscoveryStateError("promotion_effective_source_not_found")
            self.session.commit()
            return DiscoveryPromotionResult(
                status=DiscoveryPromotionStatus.REUSED,
                source=effective_source,
                promotion=existing,
                failure_code=None,
                fetch_performed=False,
            )

        selection = CatalogueDiscoveryBindingService(self.session).select_root(
            run_id=run.id,
            lead_id=bound_source.discovery_lead_id,
        )

        if bound_source.status in {
            CandidateSourceStatus.FAILED,
            CandidateSourceStatus.MANUAL_REVIEW,
        }:
            self.session.commit()
            return DiscoveryPromotionResult(
                status=DiscoveryPromotionStatus.REJECTED,
                source=bound_source,
                promotion=None,
                failure_code=bound_source.failure_code,
                fetch_performed=False,
            )
        if bound_source.status is not CandidateSourceStatus.DISCOVERED:
            raise DiscoveryStateError("promotion_source_lifecycle_incompatible")
        if candidate.status is not CandidateStatus.DISCOVERED:
            raise DiscoveryStateError("promotion_candidate_lifecycle_incompatible")

        assessment = self.session.get(CatalogueDiscoveryAssessment, selection.assessment_id)
        if assessment is None:
            raise DiscoveryStateError("promotion_assessment_not_found")
        try:
            fetched = self.fetcher.fetch(bound_source.url)
        except SourceFetchError as exc:
            self.metrics.add("source_fetch_failure")
            return self._reject(
                candidate,
                bound_source,
                failure_code=_safe_failure_code(str(exc)),
                failure_reason=str(exc),
            )
        self.metrics.add("source_fetch_success")

        final_classification = self._classify_final_owner(fetched.final_url, assessment)
        if not final_classification.is_official or not _url_matches_reviewed_owner(
            fetched.final_url, assessment.canonical_domain
        ):
            _apply_fetched_metadata(
                bound_source,
                fetched,
                classification=final_classification,
                observed_at=datetime.now(UTC),
            )
            return self._reject(
                candidate,
                bound_source,
                failure_code=UNOFFICIAL_REDIRECT_FAILURE_CODE,
                failure_reason="Final URL did not retain the reviewed contextual owner domain.",
            )

        target = DiscoveryTargetIdentitySnapshot.model_validate(run.target_identity_snapshot)
        verification = verify_target_content(target, fetched)
        if not verification.accepted:
            _apply_fetched_metadata(
                bound_source,
                fetched,
                classification=final_classification,
                observed_at=datetime.now(UTC),
            )
            return self._reject(
                candidate,
                bound_source,
                failure_code=TARGET_MISMATCH_FAILURE_CODE,
                failure_reason="Fetched content did not identify the expected discovery target.",
            )

        effective_source = self._reconcile_final_source(
            candidate=candidate,
            bound_source=bound_source,
            fetched=fetched,
            classification=final_classification,
        )
        candidate.status = CandidateStatus.SOURCE_FETCHED
        candidate.failure_code = None
        candidate.failure_reason = None
        candidate.next_attempt_at = None
        candidate.claimed_by = None
        candidate.claimed_until = None
        promotion = self.discovery.record_promotion(
            run_id=run.id,
            lead_id=selection.lead_id,
            assessment_id=selection.assessment_id,
            candidate_id=candidate.id,
            candidate_source_id=effective_source.id,
        )
        return DiscoveryPromotionResult(
            status=DiscoveryPromotionStatus.PROMOTED,
            source=effective_source,
            promotion=promotion,
            failure_code=None,
            fetch_performed=True,
        )

    def _classify_final_owner(
        self,
        final_url: str,
        assessment: CatalogueDiscoveryAssessment,
    ) -> SourceClassification:
        provider = (
            self.session.get(Provider, assessment.context_provider_id)
            if assessment.context_provider_id is not None
            else None
        )
        institution = (
            self.session.get(Institution, assessment.context_institution_id)
            if assessment.context_institution_id is not None
            else None
        )
        return self.classifier.classify(
            final_url,
            provider_website_url=provider.website_url if provider else None,
            university_website_url=institution.official_website if institution else None,
            reviewed_official_domains=self.reviewed_official_domains,
        )

    def _reconcile_final_source(
        self,
        *,
        candidate: CatalogueCandidate,
        bound_source: CatalogueCandidateSource,
        fetched: FetchedSource,
        classification: SourceClassification,
    ) -> CatalogueCandidateSource:
        observed_at = datetime.now(UTC)
        final_canonical_url = self.opportunities.canonicalize_url(fetched.final_url)
        effective_source = self.session.scalar(
            select(CatalogueCandidateSource)
            .where(
                CatalogueCandidateSource.candidate_id == candidate.id,
                CatalogueCandidateSource.canonical_url == final_canonical_url,
                CatalogueCandidateSource.id != bound_source.id,
            )
            .with_for_update()
        )
        if effective_source is None:
            try:
                with self.session.begin_nested():
                    bound_source.canonical_url = final_canonical_url
                    _apply_fetched_metadata(
                        bound_source,
                        fetched,
                        classification=classification,
                        observed_at=observed_at,
                    )
                    self.session.flush()
            except IntegrityError:
                effective_source = self.session.scalar(
                    select(CatalogueCandidateSource)
                    .where(
                        CatalogueCandidateSource.candidate_id == candidate.id,
                        CatalogueCandidateSource.canonical_url == final_canonical_url,
                        CatalogueCandidateSource.id != bound_source.id,
                    )
                    .with_for_update()
                )
                if effective_source is None:
                    raise
            else:
                return bound_source

        _apply_fetched_metadata(
            effective_source,
            fetched,
            classification=classification,
            observed_at=observed_at,
        )
        bound_source.final_url = fetched.final_url
        bound_source.status = CandidateSourceStatus.MANUAL_REVIEW
        bound_source.failure_code = REDIRECT_ALIAS_FAILURE_CODE
        bound_source.failure_reason = (
            f"Final URL converged to candidate source {effective_source.id}."
        )
        return effective_source

    def _reject(
        self,
        candidate: CatalogueCandidate,
        source: CatalogueCandidateSource,
        *,
        failure_code: str,
        failure_reason: str,
    ) -> DiscoveryPromotionResult:
        source.status = CandidateSourceStatus.MANUAL_REVIEW
        source.failure_code = failure_code[:100]
        source.failure_reason = failure_reason[:1000]
        candidate.status = CandidateStatus.NEEDS_REVIEW
        candidate.failure_code = failure_code[:100]
        candidate.failure_reason = failure_reason[:1000]
        candidate.next_attempt_at = None
        candidate.claimed_by = None
        candidate.claimed_until = None
        self.session.commit()
        return DiscoveryPromotionResult(
            status=DiscoveryPromotionStatus.REJECTED,
            source=source,
            promotion=None,
            failure_code=source.failure_code,
            fetch_performed=True,
        )


def verify_target_content(
    target: DiscoveryTargetIdentitySnapshot,
    fetched: FetchedSource,
) -> TargetContentVerification:
    text = fetched.normalized_text or fetched.excerpt_text or ""
    if not text.strip():
        return TargetContentVerification(False, None, "target_content_missing")

    scholarship_labels = tuple(
        label
        for label in (target.scholarship_name, *target.scholarship_aliases)
        if label is not None
    )
    fallback_labels = tuple(
        label
        for label in (target.programme_name, target.provider_name, target.institution_name)
        if label is not None
    )
    labels = scholarship_labels or fallback_labels
    for label in labels:
        if _identity_label_matches_text(label, text):
            return TargetContentVerification(True, label, "target_identity_matched")
    return TargetContentVerification(False, None, "target_identity_not_found")


def _identity_label_matches_text(label: str, text: str) -> bool:
    text_tokens = set(_identity_tokens(text))
    label_tokens = _identity_tokens(label)
    distinctive = tuple(token for token in label_tokens if token not in GENERIC_IDENTITY_TOKENS)
    required = distinctive or label_tokens
    return bool(required) and set(required) <= text_tokens


def _identity_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _url_matches_reviewed_owner(url: str, canonical_domain: str | None) -> bool:
    host = (urlsplit(url).hostname or "").casefold().strip(".")
    domain = (canonical_domain or "").casefold().strip(".")
    return bool(host and domain and (host == domain or host.endswith(f".{domain}")))


def _apply_fetched_metadata(
    source: CatalogueCandidateSource,
    fetched: FetchedSource,
    *,
    classification: SourceClassification,
    observed_at: datetime,
) -> None:
    source.final_url = fetched.final_url
    source.status = CandidateSourceStatus.FETCHED
    source.is_official = classification.is_official
    source.trust_tier = classification.trust_tier
    source.classification_reason = f"final redirect revalidation: {classification.reason}"[:500]
    source.content_type = fetched.content_type
    source.content_hash = fetched.normalized_content_hash or fetched.content_hash
    source.relevant_excerpt = fetched.excerpt_text
    source.bytes_read = fetched.bytes_read
    source.fetched_at = observed_at
    source.failure_code = None
    source.failure_reason = None


def _safe_failure_code(message: str) -> str:
    return message.split(":", 1)[0].strip().replace(" ", "_")[:100] or "source_fetch_failed"
