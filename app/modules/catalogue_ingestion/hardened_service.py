"""Batch-4 acquisition overrides for catalogue ingestion.

The base service keeps the established extraction, validation, review, and lease orchestration.
This derived service narrows the override to acquisition so the production admin path gets the
shared topology-aware frontier without replacing the large compatibility service wholesale.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.catalogue_ingestion.acquisition_fetcher import CatalogueSafeSourceFetcher
from app.modules.catalogue_ingestion.acquisition_models import CatalogueAcquisitionSnapshot
from app.modules.catalogue_ingestion.acquisition_planner import CatalogueAcquisitionPlanner
from app.modules.catalogue_ingestion.acquisition_runtime import (
    acquisition_seeds,
    acquisition_snapshot_payload,
    crawl_budget_for_run,
)
from app.modules.catalogue_ingestion.browser_fetcher import PlaywrightBrowserSourceFetcher
from app.modules.catalogue_ingestion.crawler import (
    BoundedOfficialSiteCrawler,
    CrawlBudget,
    CrawlResult,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
    CatalogueSourceArtifact,
    IngestionMode,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.opportunities.source_monitor import FetchedSource, SourceFetcher, SourceFetchError


class HardenedCatalogueIngestionService(CatalogueIngestionService):
    """Production acquisition path with shared frontier and durable budget evidence."""

    def __init__(
        self,
        session,
        settings,
        *,
        parser=None,
        discovery=None,
        fetcher: SourceFetcher | None = None,
        extractor=None,
        claim_extractor=None,
        classifier=None,
    ) -> None:
        effective_fetcher = fetcher or CatalogueSafeSourceFetcher(
            timeout_seconds=settings.catalogue_ai_timeout_seconds,
            max_bytes=settings.catalogue_source_max_bytes_per_page,
        )
        super().__init__(
            session,
            settings,
            parser=parser,
            discovery=discovery,
            fetcher=effective_fetcher,
            extractor=extractor,
            claim_extractor=claim_extractor,
            classifier=classifier,
        )
        self.acquisition_planner = CatalogueAcquisitionPlanner(session)
        browser_fetcher = (
            PlaywrightBrowserSourceFetcher(effective_fetcher)
            if settings.catalogue_browser_fetching_enabled
            and isinstance(effective_fetcher, CatalogueSafeSourceFetcher)
            else None
        )
        self.acquisition_crawler = BoundedOfficialSiteCrawler(
            fetcher=self.fetcher,
            browser_fetcher=browser_fetcher,
        )

    def _process_direct_candidate(
        self,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        run_lease_token: str,
    ) -> None:
        if not self.settings.catalogue_bounded_crawling_enabled:
            # The compatibility path still benefits from the overridden generic source acceptance
            # and persistence methods below; it simply keeps the operator's explicit fetch order.
            return super()._process_direct_candidate(run, candidate, run_lease_token)

        self._heartbeat_candidate(run, candidate, run_lease_token)
        explicit_sources = [
            source
            for source in candidate.sources
            if source.source_role in {CandidateSourceRole.PRIMARY, CandidateSourceRole.SUPPORTING}
        ]
        explicit_sources.sort(
            key=lambda item: (
                0 if item.source_role is CandidateSourceRole.PRIMARY else 1,
                item.canonical_url,
            )
        )
        primary_sources = [
            item for item in explicit_sources if item.source_role is CandidateSourceRole.PRIMARY
        ]
        if (
            len(primary_sources) != 1
            or not explicit_sources
            or (
                not self.settings.catalogue_completeness_mode_enabled
                and len(explicit_sources) > run.max_pages_per_candidate
            )
        ):
            self._manual_review(run, candidate, "direct_source_bundle_invalid", run_lease_token)
            return

        if candidate.status is CandidateStatus.SOURCE_FETCHED and all(
            source.status is CandidateSourceStatus.FETCHED and source.artifacts
            for source in explicit_sources
        ):
            if run.mode is IngestionMode.CANDIDATE_ONLY:
                self._manual_review(run, candidate, "candidate_only_complete", run_lease_token)
            elif not self.settings.catalogue_ai_ingestion_enabled:
                self._manual_review(run, candidate, "ai_ingestion_disabled", run_lease_token)
            else:
                self._process_direct_claims(run, candidate, run_lease_token)
            return

        provider_url, university_url = self._known_identity_urls(candidate)
        candidate.status = CandidateStatus.OFFICIAL_SOURCE_CANDIDATE
        for source in explicit_sources:
            if not self._classify_direct_source(
                source,
                provider_url=provider_url,
                university_url=university_url,
            ):
                self._manual_review(
                    run,
                    candidate,
                    "direct_source_bundle_incomplete",
                    run_lease_token,
                )
                return

        plan = self.acquisition_planner.plan(
            candidate.id,
            seed_keywords=candidate.seed_keywords,
        )
        budget = crawl_budget_for_run(run, self.settings)
        try:
            self._heartbeat_candidate(run, candidate, run_lease_token)
            crawl_result = self.acquisition_crawler.crawl_many(
                acquisition_seeds(explicit_sources),
                budget=budget,
                heartbeat=lambda: self._heartbeat_candidate(run, candidate, run_lease_token),
                frontier_needs=plan.needs,
                browser_enabled=self.settings.catalogue_browser_fetching_enabled,
                ocr_enabled=(
                    self.settings.catalogue_document_intelligence_enabled
                    or (
                        self.settings.catalogue_docling_enabled
                        and self.settings.catalogue_docling_do_ocr
                    )
                ),
                primary_root=primary_sources[0].url,
                enqueue_seed_sitemaps=self.settings.catalogue_completeness_mode_enabled,
            )
            self._record_acquisition_snapshot(run, candidate, plan, budget, crawl_result)
            self._heartbeat_candidate(run, candidate, run_lease_token)
        except SourceFetchError as exc:
            self._record_direct_fetch_failure(primary_sources[0], exc)
            self._manual_review(
                run,
                candidate,
                "direct_source_bundle_incomplete",
                run_lease_token,
            )
            return

        accepted_by_identity = self._accepted_page_identity(crawl_result)
        duplicate_identities = {
            self.opportunities.canonicalize_url(value)
            for value in (
                *crawl_result.duplicate_content_urls,
                *crawl_result.near_duplicate_content_urls,
            )
        }
        failures = False
        for source in explicit_sources:
            fetched = accepted_by_identity.get(source.canonical_url)
            if fetched is None:
                fetched = accepted_by_identity.get(self.opportunities.canonicalize_url(source.url))
            if fetched is None:
                if (
                    source.source_role is CandidateSourceRole.SUPPORTING
                    and source.canonical_url in duplicate_identities
                ):
                    # A supporting URL may resolve to evidence already accepted from another root.
                    # Keep that source transparent for review without making the whole bundle fail
                    # or inventing an artifact that was not separately accepted.
                    source.status = CandidateSourceStatus.MANUAL_REVIEW
                    source.failure_code = "duplicate_evidence_source"
                    source.failure_reason = (
                        "Supporting source resolved to duplicate or near-duplicate "
                        "accepted evidence"
                    )
                    continue
                source.status = CandidateSourceStatus.MANUAL_REVIEW
                source.failure_code = "explicit_source_not_acquired"
                source.failure_reason = self._unresolved_source_reason(source, crawl_result)
                failures = True
                continue
            if not self._accept_direct_source(
                candidate,
                source,
                fetched,
                provider_url=provider_url,
                university_url=university_url,
            ):
                failures = True

        self._persist_crawled_sources(
            candidate,
            crawl_result,
            provider_url=provider_url,
            university_url=university_url,
            heartbeat=lambda: self._heartbeat_candidate(run, candidate, run_lease_token),
        )
        if crawl_result.failures:
            self.metrics.add("source_fetch_failure", len(crawl_result.failures))

        if failures:
            self._manual_review(
                run,
                candidate,
                "direct_source_bundle_incomplete",
                run_lease_token,
            )
            return
        candidate.status = CandidateStatus.SOURCE_FETCHED
        self._heartbeat_candidate(run, candidate, run_lease_token)
        if run.mode is IngestionMode.CANDIDATE_ONLY:
            self._manual_review(run, candidate, "candidate_only_complete", run_lease_token)
            return
        if not self.settings.catalogue_ai_ingestion_enabled:
            self._manual_review(run, candidate, "ai_ingestion_disabled", run_lease_token)
            return
        self._process_direct_claims(run, candidate, run_lease_token)

    def _accept_direct_source(
        self,
        candidate: CatalogueCandidate,
        source: CatalogueCandidateSource,
        fetched: FetchedSource,
        *,
        provider_url: str | None,
        university_url: str | None,
        root_fetched: FetchedSource | None = None,
    ) -> bool:
        # Batch 3 generalized topology, so the old MEXT lexical child/root gate is no longer a
        # valid source-acceptance criterion. Officiality + scoped evidence own that decision now.
        del root_fetched
        return super()._accept_direct_source(
            candidate,
            source,
            fetched,
            provider_url=provider_url,
            university_url=university_url,
            root_fetched=None,
        )

    def _persist_crawled_sources(
        self,
        candidate: CatalogueCandidate,
        crawl_result: CrawlResult,
        *,
        provider_url: str | None,
        university_url: str | None,
        heartbeat: object | None = None,
    ) -> None:
        """Persist every accepted official crawl artifact without topic-specific narrowing."""

        fetched_at = datetime.now(UTC)
        explicit_ids = {
            item.id
            for item in candidate.sources
            if item.source_role in {CandidateSourceRole.PRIMARY, CandidateSourceRole.SUPPORTING}
        }
        for page in crawl_result.pages:
            if callable(heartbeat):
                heartbeat()
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
            if child_source is not None and child_source.id in explicit_ids:
                # The explicit-root artifact is persisted by _accept_direct_source.
                continue
            if child_source is None:
                child_source = CatalogueCandidateSource(
                    url=fetched.url,
                    canonical_url=canonical_url,
                    source_role=CandidateSourceRole.CRAWLED,
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
            child_source.content_type = fetched.content_type
            child_source.content_hash = fetched.normalized_content_hash or fetched.content_hash
            child_source.relevant_excerpt = fetched.excerpt_text
            child_source.bytes_read = fetched.bytes_read
            child_source.fetched_at = fetched_at
            if classification.is_official:
                child_source.status = CandidateSourceStatus.FETCHED
                child_source.failure_code = None
                child_source.failure_reason = None
                self.session.flush()
                self._persist_source_artifact(child_source, fetched)
            else:
                child_source.status = CandidateSourceStatus.MANUAL_REVIEW
                child_source.failure_code = "crawler_child_not_official"
                child_source.failure_reason = classification.reason[:1000]
        if callable(heartbeat):
            heartbeat()

    def _persist_source_artifact(
        self,
        source: CatalogueCandidateSource,
        fetched: FetchedSource,
    ) -> None:
        """Persist immutable normalized evidence with conversion provenance when available."""

        normalized_text = fetched.normalized_text or fetched.excerpt_text
        if not normalized_text:
            raise SourceFetchError("source_normalized_text_missing")
        content_hash = fetched.normalized_content_hash or fetched.content_hash
        existing = self.session.scalar(
            select(CatalogueSourceArtifact).where(
                CatalogueSourceArtifact.source_id == source.id,
                CatalogueSourceArtifact.content_hash == content_hash,
            )
        )
        if existing is not None:
            return
        content_type = fetched.content_type
        conversion_version = getattr(fetched, "conversion_version", None)
        extraction_method = (
            str(conversion_version)
            if conversion_version
            else "pdf_text"
            if content_type == "application/pdf"
            else "normalized_text"
        )
        links = []
        for item in fetched.links[:500]:
            link = {"url": item.url, "text": item.text, "title": item.title}
            relation = getattr(item, "relation", None)
            hreflang = getattr(item, "hreflang", None)
            media_type = getattr(item, "media_type", None)
            context_tags = getattr(item, "context_tags", None)
            if relation:
                link["relation"] = list(relation) if not isinstance(relation, str) else [relation]
            if hreflang:
                link["hreflang"] = hreflang
            if media_type:
                link["media_type"] = media_type
            if context_tags:
                link["context_tags"] = list(context_tags)
            links.append(link)
        source.artifacts.append(
            CatalogueSourceArtifact(
                final_url=fetched.final_url,
                content_type=content_type,
                content_hash=content_hash,
                normalized_text=normalized_text,
                extraction_method=extraction_method[:64],
                byte_count=fetched.bytes_read,
                character_count=len(normalized_text),
                fetch_metadata={
                    "operator_host": self._safe_host(source.url),
                    "source_role": source.source_role.value,
                    "links": links,
                    "original_artifact_hash": getattr(fetched, "original_artifact_hash", None),
                    "sniffed_content_type": getattr(fetched, "sniffed_content_type", None),
                    "conversion_version": conversion_version,
                    "coordinates": list(getattr(fetched, "coordinates", ()) or ()),
                    "canonical_url_hint": getattr(fetched, "canonical_url_hint", None),
                    "language_hints": list(getattr(fetched, "language_hints", ()) or ()),
                },
            )
        )

    def _record_acquisition_snapshot(
        self,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        plan,
        budget: CrawlBudget,
        result: CrawlResult,
    ) -> None:
        plan_json, budget_json, result_json = acquisition_snapshot_payload(
            plan=plan,
            budget=budget,
            result=result,
        )
        self.session.add(
            CatalogueAcquisitionSnapshot(
                run_id=run.id,
                candidate_id=candidate.id,
                coverage_revision=plan.coverage_revision,
                plan_json=plan_json,
                budget_json=budget_json,
                result_json=result_json,
            )
        )
        self.session.flush()

    def _accepted_page_identity(self, result: CrawlResult) -> dict[str, FetchedSource]:
        identities: dict[str, FetchedSource] = {}
        for page in result.pages:
            fetched = page.fetched
            for raw_url in (fetched.url, fetched.final_url, page.url):
                identities[self.opportunities.canonicalize_url(raw_url)] = fetched
        return identities

    def _unresolved_source_reason(
        self,
        source: CatalogueCandidateSource,
        result: CrawlResult,
    ) -> str:
        canonical = source.canonical_url
        relevant = [
            item.reason
            for item in result.failures
            if self.opportunities.canonicalize_url(item.url) == canonical
        ]
        relevant.extend(
            item.reason
            for item in result.rejected
            if self.opportunities.canonicalize_url(item.url) == canonical
        )
        if relevant:
            return "; ".join(sorted(set(relevant)))[:1000]
        if result.budget_exhausted:
            return (
                "Acquisition ended before this explicit source was accepted: "
                + ", ".join(result.budget_reasons)
            )[:1000]
        if result.escalations:
            return "Explicit source requires a disabled or later-stage acquisition escalation"
        return "Explicit source was not accepted into the bounded acquisition frontier"

    @staticmethod
    def _safe_host(value: str) -> str | None:
        from urllib.parse import urlsplit

        return urlsplit(value).hostname


__all__ = ["HardenedCatalogueIngestionService"]
