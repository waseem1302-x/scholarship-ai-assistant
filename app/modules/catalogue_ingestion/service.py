"""Fail-closed orchestration from seed candidate to the existing human review boundary."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.models import AuditLog, User
from app.modules.catalogue_ingestion.crawler import (
    BoundedOfficialSiteCrawler,
    CrawlBudget,
    CrawlResult,
)
from app.modules.catalogue_ingestion.metrics import get_catalogue_metrics
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    ExtractionAttemptStatus,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.provider import (
    CatalogueExtractionProvider,
    ExtractionProviderError,
    ExtractionSchemaError,
    extraction_prompt_hash,
    get_extraction_provider,
)
from app.modules.catalogue_ingestion.repository import CatalogueIngestionRepository
from app.modules.catalogue_ingestion.schemas import (
    EXTRACTION_SCHEMA_VERSION,
    CandidateListResponse,
    CandidateResponse,
    CatalogueExtractionOutput,
    IngestionRunListResponse,
    IngestionRunResponse,
    SeedCandidate,
)
from app.modules.catalogue_ingestion.seed_parser import (
    LocalSeedDocumentParser,
    SeedDocumentParser,
    SeedSourceLoader,
)
from app.modules.catalogue_ingestion.sources import (
    OfficialSourceClassifier,
    SeedUrlDiscoveryProvider,
    WebDiscoveryProvider,
)
from app.modules.catalogue_ingestion.validation import validate_and_build_proposal
from app.modules.opportunities.models import Provider, University
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.service import OpportunityService
from app.modules.opportunities.source_monitor import (
    SafeSourceFetcher,
    SourceFetcher,
    SourceFetchError,
)
from app.modules.profiles.schemas import canonical_country_code


class RunBudgetExhausted(RuntimeError):
    pass


class CatalogueIngestionService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        parser: SeedDocumentParser | None = None,
        discovery: WebDiscoveryProvider | None = None,
        fetcher: SourceFetcher | None = None,
        extractor: CatalogueExtractionProvider | None = None,
        classifier: OfficialSourceClassifier | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.repository = CatalogueIngestionRepository(session)
        self.opportunities = OpportunityRepository(session)
        self.parser = parser or LocalSeedDocumentParser()
        self.discovery = discovery or SeedUrlDiscoveryProvider()
        self.fetcher = fetcher or SafeSourceFetcher(
            timeout_seconds=settings.catalogue_ai_timeout_seconds,
            max_bytes=min(settings.catalogue_ai_max_input_characters * 4, 5_000_000),
        )
        self.extractor = extractor or get_extraction_provider(settings)
        self.classifier = classifier or OfficialSourceClassifier()
        self.metrics = get_catalogue_metrics(settings)

    def create_run_from_source(
        self,
        source: str,
        *,
        mode: IngestionMode,
        dry_run: bool,
        max_candidates: int | None = None,
    ) -> IngestionRunResponse:
        loaded = SeedSourceLoader().load(source)
        seeds = self.parser.parse(loaded)
        maximum = min(
            max_candidates or self.settings.catalogue_ai_max_candidates_per_run,
            self.settings.catalogue_ai_max_candidates_per_run,
        )
        run = CatalogueIngestionRun(
            source_label=loaded.label,
            source_fingerprint=loaded.fingerprint,
            mode=mode,
            status=IngestionRunStatus.PENDING,
            dry_run=dry_run,
            max_candidates=maximum,
            max_pages_per_candidate=self.settings.catalogue_ai_max_pages_per_candidate,
            max_model_calls=self.settings.catalogue_ai_max_calls_per_run,
            max_input_characters=self.settings.catalogue_ai_max_input_characters,
            max_output_tokens=self.settings.catalogue_ai_max_output_tokens,
            max_estimated_cost=self.settings.catalogue_ai_max_estimated_cost_per_run,
        )
        self.repository.add_run(run)
        self.repository.add_seed_candidates(run, seeds[:maximum])
        self.metrics.add("ingestion_runs_total")
        self.metrics.add("candidates_discovered", min(len(seeds), maximum))
        self.repository.refresh_run_summary(run)
        self.session.commit()
        return IngestionRunResponse.model_validate(run)

    def process_run(
        self,
        run_id: uuid.UUID,
        *,
        worker_id: str,
        batch_size: int = 25,
    ) -> IngestionRunResponse:
        run = self.repository.get_run(run_id)
        if run is None:
            raise AppError("ingestion_run_not_found", "Ingestion run was not found", 404)
        if run.status in {IngestionRunStatus.COMPLETED, IngestionRunStatus.FAILED}:
            return IngestionRunResponse.model_validate(run)
        run.status = IngestionRunStatus.RUNNING
        run.failure_code = None
        run.started_at = run.started_at or datetime.now(UTC)
        self.session.commit()

        while True:
            candidates = self.repository.claim_candidates(
                run_id=run.id,
                worker_id=worker_id,
                limit=min(batch_size, 100),
                lease_seconds=self.settings.catalogue_worker_claim_seconds,
            )
            if not candidates:
                break
            for candidate in candidates:
                try:
                    self._process_candidate(run, candidate)
                except RunBudgetExhausted:
                    run.status = IngestionRunStatus.BUDGET_EXHAUSTED
                    run.failure_code = "run_budget_exhausted"
                    self.repository.release_candidate(candidate)
                    self.session.commit()
                    self.repository.refresh_run_summary(run)
                    self.session.commit()
                    return IngestionRunResponse.model_validate(run)
                except Exception as exc:
                    candidate.status = CandidateStatus.NEEDS_REVIEW
                    candidate.failure_code = "unexpected_pipeline_failure"
                    candidate.failure_reason = type(exc).__name__
                    self.repository.release_candidate(candidate)
                    self.session.commit()
            run.checkpoint_cursor += len(candidates)
            self.session.commit()

        self.repository.refresh_run_summary(run)
        self.session.commit()
        return IngestionRunResponse.model_validate(run)

    def _process_candidate(self, run: CatalogueIngestionRun, candidate: CatalogueCandidate) -> None:
        discovered = self.discovery.discover(
            self._seed(candidate), limit=run.max_pages_per_candidate
        )
        if not discovered:
            self.metrics.add("official_sources_missing")
            self._manual_review(candidate, "official_source_not_found")
            return

        provider_url, university_url = self._known_identity_urls(candidate)
        chosen: tuple[CatalogueCandidateSource, object] | None = None
        for discovered_url in discovered:
            classification = self.classifier.classify(
                discovered_url.url,
                provider_website_url=provider_url,
                university_website_url=university_url,
                reviewed_official_domains=self.settings.catalogue_reviewed_official_domain_set,
            )
            canonical_url = self.opportunities.canonicalize_url(discovered_url.url)
            source = next(
                (item for item in candidate.sources if item.canonical_url == canonical_url), None
            )
            if source is None:
                source = CatalogueCandidateSource(
                    candidate_id=candidate.id,
                    url=discovered_url.url,
                    canonical_url=canonical_url,
                    is_official=classification.is_official,
                    trust_tier=classification.trust_tier,
                    classification_reason=classification.reason,
                )
                self.session.add(source)
                self.session.flush()
            else:
                source.is_official = classification.is_official
                source.trust_tier = classification.trust_tier
                source.classification_reason = classification.reason
            if classification.is_official and chosen is None:
                chosen = (source, classification)
        if chosen is None:
            self.metrics.add("official_sources_missing")
            self._manual_review(candidate, "official_source_not_found")
            return

        source, classification = chosen
        self.metrics.add("official_sources_found")
        candidate.status = CandidateStatus.OFFICIAL_SOURCE_CANDIDATE
        crawl_result: CrawlResult | None = None
        try:
            if self.settings.catalogue_bounded_crawling_enabled:
                per_page_bytes = min(
                    self.settings.catalogue_ai_max_input_characters * 4,
                    5_000_000,
                )
                crawl_result = BoundedOfficialSiteCrawler(fetcher=self.fetcher).crawl(
                    source.url,
                    budget=CrawlBudget(
                        max_pages=run.max_pages_per_candidate,
                        max_depth=2,
                        max_total_bytes=min(
                            per_page_bytes * run.max_pages_per_candidate,
                            20_000_000,
                        ),
                        per_host_interval_seconds=float(
                            self.settings.source_monitor_per_host_interval_seconds
                        ),
                    ),
                )
                if not crawl_result.pages:
                    raise SourceFetchError("crawler_returned_no_pages")
                fetched = crawl_result.pages[0].fetched
            else:
                fetched = self.fetcher.fetch(source.url)
        except SourceFetchError as exc:
            self.metrics.add("source_fetch_failure")
            source.status = CandidateSourceStatus.MANUAL_REVIEW
            source.failure_code = _safe_failure_code(str(exc))
            source.failure_reason = str(exc)[:1000]
            self._manual_review(candidate, source.failure_code)
            return
        final_classification = self.classifier.classify(
            fetched.final_url,
            provider_website_url=provider_url,
            university_website_url=university_url,
            reviewed_official_domains=self.settings.catalogue_reviewed_official_domain_set,
        )
        source.final_url = fetched.final_url
        self.metrics.add("source_fetch_success")
        source.canonical_url = self.opportunities.canonicalize_url(fetched.final_url)
        source.is_official = final_classification.is_official
        source.trust_tier = final_classification.trust_tier
        source.classification_reason = final_classification.reason
        if not final_classification.is_official:
            source.status = CandidateSourceStatus.MANUAL_REVIEW
            self._manual_review(candidate, "redirected_to_unofficial_source")
            return
        source.status = CandidateSourceStatus.FETCHED
        source.content_type = fetched.content_type
        source.content_hash = fetched.normalized_content_hash or fetched.content_hash
        source.relevant_excerpt = fetched.excerpt_text
        source.bytes_read = fetched.bytes_read
        source.fetched_at = datetime.now(UTC)
        if crawl_result is not None:
            self._persist_crawled_sources(
                candidate,
                crawl_result,
                provider_url=provider_url,
                university_url=university_url,
            )
            child_successes = max(0, len(crawl_result.pages) - 1)
            if child_successes:
                self.metrics.add("source_fetch_success", child_successes)
            if crawl_result.failures:
                self.metrics.add("source_fetch_failure", len(crawl_result.failures))
        candidate.status = CandidateStatus.SOURCE_FETCHED
        self.session.commit()

        if run.mode is IngestionMode.CANDIDATE_ONLY:
            self._manual_review(candidate, "candidate_only_complete")
            return
        if not self.settings.catalogue_ai_ingestion_enabled:
            self._manual_review(candidate, "ai_ingestion_disabled")
            return
        source_text = fetched.normalized_text or fetched.excerpt_text or ""
        reused = self.repository.reusable_attempt(
            canonical_url=source.canonical_url,
            content_hash=source.content_hash,
            schema_version=EXTRACTION_SCHEMA_VERSION,
            provider=self.extractor.name,
            model=self.extractor.model,
        )
        if reused is not None and reused.output_json is not None:
            output = CatalogueExtractionOutput.model_validate(reused.output_json)
            attempt_status = ExtractionAttemptStatus.REUSED
            usage = None
            reuse_is_current_attempt = (
                reused.candidate_id == candidate.id and reused.source_id == source.id
            )
        else:
            self._check_budget(run, source_text)
            try:
                result = self.extractor.extract(
                    source_url=source.final_url or source.url, source_text=source_text
                )
            except ExtractionSchemaError as exc:
                self.metrics.add("ai_schema_failures")
                self.session.add(
                    self._attempt(
                        candidate, source, ExtractionAttemptStatus.SCHEMA_FAILED, exc.code
                    )
                )
                self._manual_review(candidate, exc.code)
                return
            except ExtractionProviderError as exc:
                self.metrics.add("ai_extraction_failures")
                self.session.add(
                    self._attempt(
                        candidate, source, ExtractionAttemptStatus.PROVIDER_FAILED, exc.code
                    )
                )
                self._manual_review(candidate, exc.code)
                return
            output = result.output
            self.metrics.add("ai_extraction_calls")
            self.metrics.add("model_input_tokens", result.usage.input_tokens)
            self.metrics.add("model_output_tokens", result.usage.output_tokens)
            self.metrics.observe("estimated_ai_cost", float(result.usage.estimated_cost))
            usage = result.usage
            attempt_status = ExtractionAttemptStatus.SUCCEEDED
            reuse_is_current_attempt = False
            run.model_calls += 1
            run.input_tokens += usage.input_tokens
            run.output_tokens += usage.output_tokens
            run.estimated_cost += usage.estimated_cost
            if run.estimated_cost > run.max_estimated_cost:
                self.session.add(
                    self._attempt(
                        candidate,
                        source,
                        ExtractionAttemptStatus.SUCCEEDED,
                        None,
                        output=output,
                        usage=usage,
                    )
                )
                raise RunBudgetExhausted

        candidate.status = CandidateStatus.EXTRACTED
        trust_tier = final_classification.trust_tier
        assert trust_tier is not None
        validated = validate_and_build_proposal(
            output,
            source_url=source.final_url or source.url,
            source_text=source_text,
            source_title=candidate.seed_name,
            content_hash=source.content_hash,
            trust_tier=trust_tier,
        )
        validation_errors = _identity_resolution_errors(candidate, output) + validated.errors
        attempt = self._attempt(
            candidate,
            source,
            attempt_status if not validation_errors else ExtractionAttemptStatus.VALIDATION_FAILED,
            None if not validation_errors else "deterministic_validation_failed",
            output=output,
            usage=usage,
        )
        if not reuse_is_current_attempt:
            self.session.add(attempt)
        if validated.payload is None or validation_errors:
            self.metrics.add("validation_failures")
            candidate.status = (
                CandidateStatus.CONFLICT_DETECTED
                if output.conflicts
                else CandidateStatus.VALIDATION_FAILED
            )
            candidate.validation_errors = sorted(set(validation_errors))
            candidate.conflicts = output.conflicts
            self.repository.release_candidate(candidate)
            self.session.commit()
            return

        payload = validated.payload
        payload.name = _canonical_identity_name(candidate.seed_name, payload.name)
        candidate.proposed_payload = payload.model_dump(mode="json")
        duplicates = self.opportunities.find_opportunities_by_canonical_url(source.canonical_url)
        if duplicates:
            self.metrics.add("duplicate_candidates")
            candidate.status = CandidateStatus.DUPLICATE_CANDIDATE
            candidate.duplicate_opportunity_ids = [str(item.id) for item in duplicates]
            self.repository.release_candidate(candidate)
            self.session.commit()
            return
        candidate.status = CandidateStatus.READY_FOR_REVIEW
        self.metrics.add("candidates_ready_for_review")
        if run.mode is IngestionMode.REVIEW_QUEUE and not run.dry_run:
            created = OpportunityService(self.session).stage_opportunity_for_review(payload)
            candidate.opportunity_id = created.id
            candidate.status = CandidateStatus.SUBMITTED_FOR_REVIEW
        self.repository.release_candidate(candidate)
        self.session.commit()

    def retry_candidate(
        self, candidate_id: uuid.UUID, *, reason: str, actor: User
    ) -> CandidateResponse:
        candidate = self.repository.get_candidate_for_update(candidate_id)
        if candidate is None:
            raise AppError("catalogue_candidate_not_found", "Candidate was not found", 404)
        if candidate.status in {CandidateStatus.SUBMITTED_FOR_REVIEW, CandidateStatus.PUBLISHED}:
            raise AppError("catalogue_candidate_not_retryable", "Candidate cannot be retried", 409)
        candidate.status = CandidateStatus.DISCOVERED
        candidate.failure_code = None
        candidate.failure_reason = None
        candidate.validation_errors = []
        candidate.next_attempt_at = datetime.now(UTC)
        candidate.claimed_by = None
        candidate.claimed_until = None
        self.session.add(
            AuditLog(
                actor_user_id=actor.id,
                action="catalogue_candidate_retry_requested",
                entity_type="catalogue_candidate",
                entity_id=str(candidate.id),
                metadata_json={"reason": reason[:1000]},
            )
        )
        self.session.commit()
        return self._candidate_response(candidate)

    def submit_candidate(
        self, candidate_id: uuid.UUID, *, notes: str, actor: User
    ) -> CandidateResponse:
        candidate = self.repository.get_candidate_for_update(candidate_id)
        if candidate is None:
            raise AppError("catalogue_candidate_not_found", "Candidate was not found", 404)
        if (
            candidate.status is not CandidateStatus.READY_FOR_REVIEW
            or not candidate.proposed_payload
        ):
            raise AppError(
                "catalogue_candidate_not_ready", "Candidate has not passed review gates", 409
            )
        from app.modules.opportunities.schemas import OpportunityCreate

        payload = OpportunityCreate.model_validate(candidate.proposed_payload)
        payload.notes = f"{payload.notes or ''}\nReviewer submission note: {notes}".strip()
        created = OpportunityService(self.session).create_opportunity(payload, created_by=actor)
        candidate.opportunity_id = created.id
        candidate.status = CandidateStatus.SUBMITTED_FOR_REVIEW
        self.session.commit()
        return self._candidate_response(candidate)

    def list_runs(self, *, limit: int, offset: int) -> IngestionRunListResponse:
        items, total = self.repository.list_runs(limit=limit, offset=offset)
        return IngestionRunListResponse(
            items=[IngestionRunResponse.model_validate(item) for item in items], total=total
        )

    def list_candidates(
        self,
        *,
        status: CandidateStatus | None,
        run_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> CandidateListResponse:
        items, total = self.repository.list_candidates(
            status=status, run_id=run_id, limit=limit, offset=offset
        )
        return CandidateListResponse(
            items=[self._candidate_response(item) for item in items], total=total
        )

    def candidate(self, candidate_id: uuid.UUID) -> CandidateResponse:
        candidate = self.repository.get_candidate(candidate_id)
        if candidate is None:
            raise AppError("catalogue_candidate_not_found", "Candidate was not found", 404)
        return self._candidate_response(candidate)

    def _check_budget(self, run: CatalogueIngestionRun, source_text: str) -> None:
        if run.model_calls >= run.max_model_calls:
            raise RunBudgetExhausted
        projected_input = max(1, len(source_text) // 4)
        projected_cost = (
            Decimal(projected_input) * self.settings.catalogue_ai_input_cost_per_million
            + Decimal(run.max_output_tokens) * self.settings.catalogue_ai_output_cost_per_million
        ) / Decimal(1_000_000)
        if run.estimated_cost + projected_cost > run.max_estimated_cost:
            raise RunBudgetExhausted

    def _persist_crawled_sources(
        self,
        candidate: CatalogueCandidate,
        crawl_result: CrawlResult,
        *,
        provider_url: str | None,
        university_url: str | None,
    ) -> None:
        fetched_at = datetime.now(UTC)
        for page in crawl_result.pages[1:]:
            fetched = page.fetched
            classification = self.classifier.classify(
                fetched.final_url,
                provider_website_url=provider_url,
                university_website_url=university_url,
                reviewed_official_domains=self.settings.catalogue_reviewed_official_domain_set,
            )
            canonical_url = self.opportunities.canonicalize_url(fetched.final_url)
            child_source = next(
                (item for item in candidate.sources if item.canonical_url == canonical_url),
                None,
            )
            if child_source is None:
                child_source = CatalogueCandidateSource(
                    url=fetched.url,
                    canonical_url=canonical_url,
                    is_official=classification.is_official,
                    trust_tier=classification.trust_tier,
                    classification_reason=classification.reason,
                )
                candidate.sources.append(child_source)
            child_source.url = fetched.url
            child_source.final_url = fetched.final_url
            child_source.canonical_url = canonical_url
            child_source.is_official = classification.is_official
            child_source.trust_tier = classification.trust_tier
            child_source.classification_reason = classification.reason
            child_source.status = (
                CandidateSourceStatus.FETCHED
                if classification.is_official
                else CandidateSourceStatus.MANUAL_REVIEW
            )
            child_source.content_type = fetched.content_type
            child_source.content_hash = fetched.normalized_content_hash or fetched.content_hash
            child_source.relevant_excerpt = fetched.excerpt_text
            child_source.bytes_read = fetched.bytes_read
            child_source.fetched_at = fetched_at
            child_source.failure_code = (
                None if classification.is_official else "crawler_child_not_official"
            )
            child_source.failure_reason = (
                None if classification.is_official else classification.reason[:1000]
            )

    def _manual_review(self, candidate: CatalogueCandidate, code: str) -> None:
        candidate.status = CandidateStatus.NEEDS_REVIEW
        candidate.failure_code = code[:100]
        self.repository.release_candidate(candidate)
        self.session.commit()

    def _known_identity_urls(self, candidate: CatalogueCandidate) -> tuple[str | None, str | None]:
        provider_url = None
        university_url = None
        if candidate.seed_provider:
            provider_url = self.session.scalar(
                select(Provider.website_url).where(
                    Provider.name.ilike(candidate.seed_provider.strip())
                )
            )
        if candidate.seed_university:
            university_url = self.session.scalar(
                select(University.website_url).where(
                    University.name.ilike(candidate.seed_university.strip())
                )
            )
        return provider_url, university_url

    @staticmethod
    def _seed(candidate: CatalogueCandidate) -> SeedCandidate:
        return SeedCandidate(
            name=candidate.seed_name,
            provider=candidate.seed_provider,
            university=candidate.seed_university,
            country=candidate.seed_country,
            cycle=candidate.seed_cycle,
            intake_year=candidate.seed_intake_year,
            possible_official_url=candidate.seed_official_url,
            keywords=candidate.seed_keywords,
        )

    def _attempt(
        self,
        candidate: CatalogueCandidate,
        source: CatalogueCandidateSource,
        status: ExtractionAttemptStatus,
        error_code: str | None,
        *,
        output: CatalogueExtractionOutput | None = None,
        usage: object | None = None,
    ) -> CatalogueExtractionAttempt:
        return CatalogueExtractionAttempt(
            candidate_id=candidate.id,
            source_id=source.id,
            provider=self.extractor.name,
            model=self.extractor.model,
            schema_version=EXTRACTION_SCHEMA_VERSION,
            content_hash=source.content_hash or hashlib.sha256(b"").hexdigest(),
            prompt_hash=extraction_prompt_hash(),
            status=status,
            output_json=output.model_dump(mode="json") if output else None,
            error_code=error_code,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            estimated_cost=getattr(usage, "estimated_cost", Decimal("0")),
            latency_ms=getattr(usage, "latency_ms", 0),
        )

    @staticmethod
    def _candidate_response(candidate: CatalogueCandidate) -> CandidateResponse:
        return CandidateResponse.model_validate(candidate)


def _safe_failure_code(message: str) -> str:
    return message.split(":", 1)[0].strip().replace(" ", "_")[:100] or "source_fetch_failed"


def _identity_resolution_errors(
    candidate: CatalogueCandidate, output: CatalogueExtractionOutput
) -> list[str]:
    errors: list[str] = []
    identity = output.identity
    if not _identity_name_matches(candidate.seed_name, identity.name):
        errors.append("extracted programme identity does not match the seed candidate")
    if candidate.seed_provider and not _identity_name_matches(
        candidate.seed_provider, identity.provider_name
    ):
        errors.append("extracted provider identity conflicts with the seed candidate")
    if candidate.seed_university and not _identity_name_matches(
        candidate.seed_university, identity.university_name
    ):
        errors.append("extracted university identity conflicts with the seed candidate")
    seed_country = canonical_country_code(candidate.seed_country)
    extracted_country = identity.country_code or canonical_country_code(identity.country)
    if (
        seed_country
        and extracted_country
        and seed_country.casefold() != extracted_country.casefold()
    ):
        errors.append("extracted country conflicts with the seed candidate")
    if (
        candidate.seed_cycle
        and candidate.seed_cycle.casefold() != (output.study.cycle_id or "").casefold()
    ):
        errors.append("extracted cycle conflicts with the seed candidate")
    if (
        candidate.seed_intake_year is not None
        and candidate.seed_intake_year != output.study.intake_year
    ):
        errors.append("extracted intake year conflicts with the seed candidate")
    return errors


def _canonical_identity_name(expected: str, actual: str) -> str:
    """Remove an official page-title wrapper without changing programme identity."""

    segments = [
        segment.strip()
        for segment in re.split(r"\s+(?:-|\u2013|\u2014|\|)\s+", actual)
        if segment.strip()
    ]
    if len(segments) > 1:
        matching_segments = [
            segment for segment in segments if _identity_name_matches(expected, segment)
        ]
        if len(matching_segments) == 1:
            return matching_segments[0]

    return actual


def _identity_name_matches(expected: str, actual: str | None) -> bool:
    if not actual:
        return False

    ignored = {
        "award",
        "awards",
        "fellowship",
        "fellowships",
        "programme",
        "programmes",
        "program",
        "programs",
        "scholarship",
        "scholarships",
        "the",
    }

    def identity_tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", value.casefold())) - ignored

    def token_sets_match(expected_tokens: set[str], actual_tokens: set[str]) -> bool:
        if not expected_tokens or not actual_tokens:
            return False

        if expected_tokens == actual_tokens:
            return True

        if min(len(expected_tokens), len(actual_tokens)) >= 2 and (
            expected_tokens <= actual_tokens or actual_tokens <= expected_tokens
        ):
            return True

        overlap = expected_tokens & actual_tokens
        return len(overlap) / len(expected_tokens | actual_tokens) >= 0.6

    expected_tokens = identity_tokens(expected)
    actual_tokens = identity_tokens(actual)

    if token_sets_match(expected_tokens, actual_tokens):
        return True

    # Official sites commonly wrap the programme name in a page title such as:
    # "About us - Chevening Scholarship Programme - GOV.UK".
    # Compare separator-delimited title segments rather than globally ignoring
    # wrapper words, which would make unrelated programme names easier to match.
    title_segments = [
        segment.strip()
        for segment in re.split(r"\s+(?:-|\u2013|\u2014|\|)\s+", actual)
        if segment.strip()
    ]
    if len(title_segments) > 1:
        for segment in title_segments:
            if token_sets_match(expected_tokens, identity_tokens(segment)):
                return True

    if not expected_tokens or not actual_tokens:
        return expected.strip().casefold() == actual.strip().casefold()

    return False
