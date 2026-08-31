import hashlib
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.discovery import (
    DiscoveryObjective,
    DiscoveryObjectiveKind,
    DiscoveryPrioritySnapshot,
    DiscoveryQueryPlanner,
    DiscoveryTargetIdentitySnapshot,
)
from app.modules.catalogue_ingestion.discovery_binding import (
    CatalogueDiscoveryBindingService,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryPromotion,
    DiscoveryAttemptStatus,
    DiscoveryOfficialityStatus,
)
from app.modules.catalogue_ingestion.discovery_officiality import (
    CatalogueDiscoveryOfficialityService,
    ReviewedOwnerDomain,
    SourceAuthorityClass,
)
from app.modules.catalogue_ingestion.discovery_promotion import (
    REDIRECT_ALIAS_FAILURE_CODE,
    TARGET_MISMATCH_FAILURE_CODE,
    UNOFFICIAL_REDIRECT_FAILURE_CODE,
    DiscoveryPromotionStatus,
    verify_target_content,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryAssessmentInput,
    DiscoveryAttemptOutcome,
    DiscoveryRunLimits,
    DiscoveryStateError,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    IngestionMode,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.opportunities.evidence_models import SourceOwnerType
from app.modules.opportunities.models import Opportunity, Provider
from app.modules.opportunities.source_monitor import FetchedSource, SourceFetchError

SCHOLARSHIP_NAME = "Chinese Government Scholarship"
ROOT_URL = "https://csc.edu.cn/scholarships"
SOURCE_TEXT = (
    "The Chinese Government Scholarship provides tuition funding and a monthly stipend. "
    "Applicants can review eligibility and required documents on this page."
)


class FakeFetcher:
    def __init__(
        self,
        *,
        final_url: str = ROOT_URL,
        text: str = SOURCE_TEXT,
        error: str | None = None,
    ) -> None:
        self.final_url = final_url
        self.text = text
        self.error = error
        self.calls = 0

    def fetch(self, url: str) -> FetchedSource:
        self.calls += 1
        if self.error is not None:
            raise SourceFetchError(self.error)
        content_hash = hashlib.sha256(self.text.encode()).hexdigest()
        return FetchedSource(
            url=url,
            final_url=self.final_url,
            content_hash=content_hash,
            normalized_content_hash=content_hash,
            excerpt_text=self.text[:500],
            section_label="Scholarship overview",
            bytes_read=len(self.text.encode()),
            normalized_text=self.text,
            content_type="text/html",
        )


class ForbiddenDiscovery:
    def discover(self, seed, *, limit):
        del seed, limit
        raise AssertionError("Step 8 must not perform discovery")


class ForbiddenExtractor:
    name = "forbidden"
    model = "forbidden"

    def extract(self, *, source_url, source_text):
        del source_url, source_text
        raise AssertionError("Step 8 must not perform extraction")


def _settings() -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://example.openai.azure.com",
        catalogue_ai_model="unused-in-step-8",
        catalogue_ai_input_cost_per_million=Decimal("1"),
        catalogue_ai_output_cost_per_million=Decimal("2"),
    )


def _candidate(db_session, provider: Provider) -> CatalogueCandidate:
    ingestion_run = CatalogueIngestionRun(
        source_label=f"promotion-{uuid.uuid4().hex}.json",
        source_fingerprint=uuid.uuid4().hex.ljust(64, "0"),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=1,
        max_pages_per_candidate=1,
        max_model_calls=0,
        max_input_characters=10_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("0"),
    )
    db_session.add(ingestion_run)
    db_session.flush()
    candidate = CatalogueCandidate(
        run_id=ingestion_run.id,
        seed_index=0,
        idempotency_key=uuid.uuid4().hex.ljust(64, "0"),
        seed_name=SCHOLARSHIP_NAME,
        seed_provider=provider.name,
        seed_country="China",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    db_session.commit()
    return candidate


def _objective(candidate: CatalogueCandidate, provider: Provider) -> DiscoveryObjective:
    return DiscoveryObjective(
        objective_kind=DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE,
        candidate_id=candidate.id,
        field_paths=("identity.official_source",),
        reason_codes=("OFFICIAL_SOURCE_MISSING",),
        criticality_tier=0,
        scholarship_name=SCHOLARSHIP_NAME,
        scholarship_aliases=("CSC Scholarship",),
        provider_name=provider.name,
        country="China",
        reviewed_domains=("csc.edu.cn",),
    )


def _create_discovery_run(db_session, objective: DiscoveryObjective):
    repository = CatalogueDiscoveryRepository(db_session)
    run = repository.create_run(
        objective=objective,
        priority=DiscoveryPrioritySnapshot(
            blocking_class=0,
            criticality_tier=0,
            conflict_or_stale_rank=1,
            current_cycle_rank=1,
            deterministic_tiebreak=uuid.uuid4().hex,
            reason_codes=objective.reason_codes,
        ),
        plans=DiscoveryQueryPlanner(max_queries=2).plan(objective),
        provider="fake",
        model="fake-web-search-v1",
        limits=DiscoveryRunLimits(
            max_queries=2,
            max_provider_calls=2,
            max_tool_calls=2,
            max_leads=10,
            max_response_bytes=50_000,
            max_estimated_cost=Decimal("1.00"),
        ),
        dry_run=False,
    )
    return repository, run


def _claim_observe_and_assess(
    db_session,
    repository: CatalogueDiscoveryRepository,
    run_id: uuid.UUID,
    provider: Provider,
    url: str,
):
    query = repository.claim_queries(
        run_id=run_id,
        worker_id="promotion-worker",
        limit=1,
        lease_seconds=60,
        max_attempts=2,
    )[0]
    attempt = repository.reserve_attempt(
        query_id=query.id,
        worker_id="promotion-worker",
        request_fingerprint=f"{query.ordinal + 1:x}" * 64,
        reserved_tool_calls=1,
        reserved_estimated_cost=Decimal("0.10"),
    )
    repository.settle_attempt(
        attempt.id,
        DiscoveryAttemptOutcome(
            status=DiscoveryAttemptStatus.SUCCEEDED,
            provider_response_id=f"promotion-response-{query.ordinal}",
            web_search_executed=True,
            tool_call_count=1,
            result_url_count=1,
            response_bytes=200,
            estimated_tool_cost=Decimal("0.01"),
        ),
    )
    lead, _ = repository.record_lead_observation(
        query_id=query.id,
        url=url,
        discovery_reason="Step 8 promotion proof lead",
    )
    assessment = CatalogueDiscoveryOfficialityService(db_session).assess_lead(
        run_id=run_id,
        lead_id=lead.id,
        reviewed_owner_domains=(
            ReviewedOwnerDomain(
                domain="csc.edu.cn",
                owner_type=SourceOwnerType.PROVIDER,
                owner_name_snapshot=provider.name,
                authority_class=SourceAuthorityClass.CANONICAL_OWNER,
                review_reason="Verified provider domain for Step 8 tests.",
                provider_id=provider.id,
            ),
        ),
    )
    assert assessment.officiality_status is DiscoveryOfficialityStatus.OFFICIAL
    reviewer = User(
        email=f"promotion-reviewer-{uuid.uuid4().hex}@example.test",
        password_hash="not-used",
        role=UserRole.ADMIN,
    )
    db_session.add(reviewer)
    db_session.commit()
    repository.review_lead(
        lead_id=lead.id,
        status="approved",
        reviewer_id=reviewer.id,
        reason="Official ownership assessment reviewed for promotion test.",
    )
    return query, lead, assessment


def _bound_context(db_session, *, root_url: str = ROOT_URL):
    provider = Provider(
        name=f"China Scholarship Council {uuid.uuid4().hex}",
        website_url="https://csc.edu.cn",
    )
    db_session.add(provider)
    db_session.commit()
    candidate = _candidate(db_session, provider)
    repository, run = _create_discovery_run(db_session, _objective(candidate, provider))
    _, lead, assessment = _claim_observe_and_assess(
        db_session, repository, run.id, provider, root_url
    )
    binding = CatalogueDiscoveryBindingService(db_session).bind_best_root(run_id=run.id)
    return provider, candidate, repository, run, lead, assessment, binding.source


def _service(db_session, fetcher: FakeFetcher) -> CatalogueIngestionService:
    return CatalogueIngestionService(
        db_session,
        _settings(),
        discovery=ForbiddenDiscovery(),
        fetcher=fetcher,
        extractor=ForbiddenExtractor(),
    )


def test_bound_root_is_fetched_promoted_once_without_extraction_or_creation(db_session) -> None:
    _, candidate, _, run, lead, assessment, source = _bound_context(db_session)
    fetcher = FakeFetcher()
    service = _service(db_session, fetcher)
    candidate_count = db_session.scalar(select(func.count()).select_from(CatalogueCandidate))

    first = service.process_bound_discovery_source(run.id, source.id)
    repeated = service.process_bound_discovery_source(run.id, source.id)

    assert first.status is DiscoveryPromotionStatus.PROMOTED
    assert repeated.status is DiscoveryPromotionStatus.REUSED
    assert first.promotion is not None
    assert first.promotion.id == repeated.promotion.id
    assert first.promotion.lead_id == lead.id
    assert first.promotion.assessment_id == assessment.id
    assert first.source.id == source.id
    assert first.source.status is CandidateSourceStatus.FETCHED
    assert first.source.is_official
    assert first.source.content_hash == hashlib.sha256(SOURCE_TEXT.encode()).hexdigest()
    assert candidate.status is CandidateStatus.SOURCE_FETCHED
    assert fetcher.calls == 1
    assert run.promotions == 1
    persisted_candidate_count = db_session.scalar(
        select(func.count()).select_from(CatalogueCandidate)
    )
    assert persisted_candidate_count == candidate_count
    assert db_session.scalar(select(func.count()).select_from(CatalogueExtractionAttempt)) == 0
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_existing_promotion_remains_reusable_after_assessment_supersession(db_session) -> None:
    provider, _, repository, run, lead, assessment, source = _bound_context(db_session)
    fetcher = FakeFetcher()
    service = _service(db_session, fetcher)
    first = service.process_bound_discovery_source(run.id, source.id)
    superseding = repository.append_assessment(
        run_id=run.id,
        lead_id=lead.id,
        assessment=DiscoveryAssessmentInput(
            assessment_context_hash="b" * 64,
            context_type=assessment.context_type,
            context_provider_id=provider.id,
            officiality_status=DiscoveryOfficialityStatus.UNRESOLVED,
            owner_type=SourceOwnerType.PROVIDER.value,
            owner_id=provider.id,
            canonical_domain="csc.edu.cn",
            reason_code="OWNER_REVIEW_REVOKED",
            reason_detail="A later review revoked the prior owner assessment.",
            classifier_version=assessment.classifier_version,
            supersedes_assessment_id=assessment.id,
        ),
    )

    repeated = service.process_bound_discovery_source(run.id, source.id)

    assert first.promotion is not None
    assert repeated.status is DiscoveryPromotionStatus.REUSED
    assert repeated.promotion.id == first.promotion.id
    assert fetcher.calls == 1
    db_session.execute(
        delete(CatalogueDiscoveryAssessment).where(
            CatalogueDiscoveryAssessment.id == superseding.id
        )
    )
    db_session.commit()


@pytest.mark.parametrize(
    "error",
    [
        "unsafe_source_url: private or reserved network target",
        "robots_unreachable",
        "source_authentication_required",
        "unsupported_source_content_type: image/png",
    ],
)
def test_safe_fetch_rejection_retains_binding_without_promotion(db_session, error) -> None:
    _, candidate, _, run, lead, _, source = _bound_context(db_session)
    fetcher = FakeFetcher(error=error)
    service = _service(db_session, fetcher)

    rejected = service.process_bound_discovery_source(run.id, source.id)
    repeated = service.process_bound_discovery_source(run.id, source.id)

    assert rejected.status is DiscoveryPromotionStatus.REJECTED
    assert repeated.status is DiscoveryPromotionStatus.REJECTED
    assert source.discovery_lead_id == lead.id
    assert source.status is CandidateSourceStatus.MANUAL_REVIEW
    assert candidate.status is CandidateStatus.NEEDS_REVIEW
    assert rejected.failure_code == error.split(":", 1)[0]
    assert fetcher.calls == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogueDiscoveryPromotion)) == 0


def test_cross_owner_redirect_is_not_promoted(db_session) -> None:
    _, candidate, _, run, _, _, source = _bound_context(db_session)
    fetcher = FakeFetcher(final_url="https://example.org/not-csc")

    result = _service(db_session, fetcher).process_bound_discovery_source(run.id, source.id)

    assert result.status is DiscoveryPromotionStatus.REJECTED
    assert result.failure_code == UNOFFICIAL_REDIRECT_FAILURE_CODE
    assert source.final_url == "https://example.org/not-csc"
    assert source.status is CandidateSourceStatus.MANUAL_REVIEW
    assert not source.is_official
    assert candidate.status is CandidateStatus.NEEDS_REVIEW
    assert db_session.scalar(select(func.count()).select_from(CatalogueDiscoveryPromotion)) == 0


def test_official_owner_page_without_target_identity_is_not_promoted(db_session) -> None:
    _, candidate, _, run, _, _, source = _bound_context(db_session)
    fetcher = FakeFetcher(
        text="Official provider contact information and general news for international visitors."
    )

    result = _service(db_session, fetcher).process_bound_discovery_source(run.id, source.id)

    assert result.status is DiscoveryPromotionStatus.REJECTED
    assert result.failure_code == TARGET_MISMATCH_FAILURE_CODE
    assert source.status is CandidateSourceStatus.MANUAL_REVIEW
    assert source.is_official
    assert source.content_hash is not None
    assert candidate.status is CandidateStatus.NEEDS_REVIEW
    assert db_session.scalar(select(func.count()).select_from(CatalogueDiscoveryPromotion)) == 0


def test_dry_run_cannot_fetch_even_if_a_binding_already_exists(db_session) -> None:
    _, _, _, run, _, _, source = _bound_context(db_session)
    run.dry_run = True
    db_session.commit()
    fetcher = FakeFetcher()

    with pytest.raises(DiscoveryStateError, match="fetch_disabled_for_dry_run"):
        _service(db_session, fetcher).process_bound_discovery_source(run.id, source.id)

    assert fetcher.calls == 0
    assert db_session.scalar(select(func.count()).select_from(CatalogueDiscoveryPromotion)) == 0


def test_hook_rejects_a_source_that_was_not_discovery_bound(db_session) -> None:
    _, candidate, _, run, _, _, _ = _bound_context(db_session)
    unbound_source = CatalogueCandidateSource(
        candidate_id=candidate.id,
        url="https://csc.edu.cn/unbound",
        canonical_url="https://csc.edu.cn/unbound",
        status=CandidateSourceStatus.DISCOVERED,
        is_official=True,
        trust_tier=1,
        classification_reason="manual source without discovery provenance",
    )
    db_session.add(unbound_source)
    db_session.commit()
    fetcher = FakeFetcher()

    with pytest.raises(DiscoveryStateError, match="requires_prebound"):
        _service(db_session, fetcher).process_bound_discovery_source(
            run.id,
            unbound_source.id,
        )

    assert fetcher.calls == 0


def test_same_owner_redirect_updates_the_bound_source_canonical_url(db_session) -> None:
    _, _, _, run, _, _, source = _bound_context(
        db_session,
        root_url="https://csc.edu.cn/old-root",
    )
    final_url = "https://csc.edu.cn/current-root"

    result = _service(
        db_session,
        FakeFetcher(final_url=final_url),
    ).process_bound_discovery_source(run.id, source.id)

    assert result.status is DiscoveryPromotionStatus.PROMOTED
    assert result.source.id == source.id
    assert source.url == "https://csc.edu.cn/old-root"
    assert source.final_url == final_url
    assert source.canonical_url == final_url
    assert source.status is CandidateSourceStatus.FETCHED


def test_redirect_convergence_uses_one_effective_fetched_source(db_session) -> None:
    provider, candidate, repository, run, first_lead, _, bound_source = _bound_context(
        db_session,
        root_url="https://csc.edu.cn/old",
    )
    final_url = "https://csc.edu.cn/current"
    _, second_lead, _ = _claim_observe_and_assess(
        db_session, repository, run.id, provider, final_url
    )
    existing_source = CatalogueCandidateSource(
        candidate_id=candidate.id,
        discovery_lead_id=second_lead.id,
        url=final_url,
        canonical_url=final_url,
        status=CandidateSourceStatus.DISCOVERED,
        is_official=True,
        trust_tier=1,
        classification_reason="second reviewed discovery binding",
    )
    db_session.add(existing_source)
    db_session.commit()
    fetcher = FakeFetcher(final_url=final_url)
    service = _service(db_session, fetcher)

    first = service.process_bound_discovery_source(run.id, bound_source.id)
    repeated = service.process_bound_discovery_source(run.id, bound_source.id)

    assert first.status is DiscoveryPromotionStatus.PROMOTED
    assert repeated.status is DiscoveryPromotionStatus.REUSED
    assert first.source.id == existing_source.id
    assert first.promotion is not None
    assert first.promotion.lead_id == first_lead.id
    assert first.promotion.candidate_source_id == existing_source.id
    assert existing_source.status is CandidateSourceStatus.FETCHED
    assert existing_source.canonical_url == final_url
    assert bound_source.discovery_lead_id == first_lead.id
    assert bound_source.status is CandidateSourceStatus.MANUAL_REVIEW
    assert bound_source.failure_code == REDIRECT_ALIAS_FAILURE_CODE
    assert bound_source.final_url == final_url
    assert fetcher.calls == 1
    fetched_sources = db_session.scalar(
        select(func.count())
        .select_from(CatalogueCandidateSource)
        .where(CatalogueCandidateSource.status == CandidateSourceStatus.FETCHED)
    )
    assert fetched_sources == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogueExtractionAttempt)) == 0


@pytest.mark.parametrize(
    ("target", "text", "expected"),
    [
        (
            DiscoveryTargetIdentitySnapshot(scholarship_name="MEXT Scholarship"),
            "Apply for the Japanese Government MEXT Scholarship through the embassy route.",
            True,
        ),
        (
            DiscoveryTargetIdentitySnapshot(
                scholarship_name=SCHOLARSHIP_NAME,
                scholarship_aliases=("CSC Scholarship",),
            ),
            "CSC Scholarship application guidance and university routes.",
            True,
        ),
        (
            DiscoveryTargetIdentitySnapshot(scholarship_name="MEXT Scholarship"),
            "General international funding opportunities and university news.",
            False,
        ),
    ],
)
def test_target_content_verification_is_deterministic(target, text, expected) -> None:
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    fetched = FetchedSource(
        url=ROOT_URL,
        final_url=ROOT_URL,
        content_hash=content_hash,
        excerpt_text=text,
        section_label="Overview",
        bytes_read=len(text.encode()),
        normalized_text=text,
        normalized_content_hash=content_hash,
    )

    result = verify_target_content(target, fetched)

    assert result.accepted is expected
