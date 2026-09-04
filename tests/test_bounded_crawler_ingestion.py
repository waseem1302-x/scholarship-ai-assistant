import hashlib
import json
from decimal import Decimal

from sqlalchemy import select

from app.core.config import Settings
from app.modules.catalogue_ingestion.acquisition_runtime import crawl_budget_for_run
from app.modules.catalogue_ingestion.hardened_service import HardenedCatalogueIngestionService
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueSourceArtifact,
    IngestionMode,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.opportunities.source_monitor import FetchedLink, FetchedSource, SourceFetchError

ROOT = "https://scholarships.gov.uk/example"
FUNDING = "https://scholarships.gov.uk/example/funding"
DEADLINE = "https://scholarships.gov.uk/example/deadline"
EXTERNAL = "https://third-party.example/example"


def settings(
    *,
    crawling: bool,
    max_pages: int = 3,
    completeness: bool = False,
) -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_bounded_crawling_enabled=crawling,
        catalogue_ai_max_pages_per_candidate=max_pages,
        catalogue_completeness_mode_enabled=completeness,
        source_monitor_per_host_interval_seconds=0,
    )


def fetched(url: str, text: str, *, links: tuple[FetchedLink, ...] = ()) -> FetchedSource:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return FetchedSource(
        url=url,
        final_url=url,
        content_hash=digest,
        excerpt_text=text,
        section_label="Scholarship",
        bytes_read=len(text.encode()),
        normalized_text=text,
        normalized_content_hash=digest,
        content_type="text/html",
        links=links,
    )


class MappingFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.responses = {
            ROOT: fetched(
                ROOT,
                "Official scholarship overview and application guidance.",
                links=(
                    FetchedLink(url=EXTERNAL, text="External copy"),
                    FetchedLink(url=DEADLINE, text="Application deadline and timeline"),
                    FetchedLink(url=FUNDING, text="Scholarship funding stipend and tuition"),
                ),
            ),
            FUNDING: fetched(FUNDING, "Official scholarship funding and stipend details."),
            DEADLINE: fetched(DEADLINE, "Official scholarship application deadline details."),
        }

    def _response(self, url: str) -> FetchedSource:
        self.calls.append(url)
        return self.responses[url]

    def fetch(self, url: str) -> FetchedSource:
        return self._response(url)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        response = self._response(url)
        if response.bytes_read > max_bytes:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        return response


def seed_file(tmp_path):
    path = tmp_path / "crawler-seed.json"
    path.write_text(
        json.dumps([{"name": "Example Scholarship", "possible_official_url": ROOT}]),
        encoding="utf-8",
    )
    return path


def run_candidate(db_session, tmp_path, *, crawling: bool, max_pages: int = 3):
    fetcher = MappingFetcher()
    service = CatalogueIngestionService(
        db_session,
        settings(crawling=crawling, max_pages=max_pages),
        fetcher=fetcher,
    )
    run = service.create_run_from_source(
        str(seed_file(tmp_path)),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
    )
    service.process_run(run.id, worker_id="crawler-test")
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    assert candidate is not None
    sources = list(
        db_session.scalars(
            select(CatalogueCandidateSource)
            .where(CatalogueCandidateSource.candidate_id == candidate.id)
            .order_by(CatalogueCandidateSource.canonical_url)
        )
    )
    return candidate, sources, fetcher


def test_bounded_crawling_defaults_to_ten_pages() -> None:
    configured = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
    )

    assert configured.catalogue_bounded_crawling_enabled is True
    assert configured.catalogue_ai_max_pages_per_candidate == 10


def test_bounded_crawling_accepts_twenty_five_page_ceiling() -> None:
    configured = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_ai_max_pages_per_candidate=25,
    )

    assert configured.catalogue_ai_max_pages_per_candidate == 25


def test_completeness_mode_persists_paid_failsafes_and_exhausts_frontier(
    db_session,
    tmp_path,
) -> None:
    configured = settings(crawling=True, completeness=True)
    service = CatalogueIngestionService(db_session, configured, fetcher=MappingFetcher())

    response = service.create_run_from_source(
        str(seed_file(tmp_path)),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
    )
    run = service.repository.get_run(response.id)
    assert run is not None

    budget = crawl_budget_for_run(run, configured)

    assert run.max_model_calls == 500
    assert run.max_estimated_cost == Decimal("5")
    assert budget.max_fetch_attempts == 1_000
    assert budget.max_accepted_artifacts is None
    assert budget.max_wall_seconds is None
    assert budget.max_depth == 3
    assert budget.max_links_per_page == 500


def test_completeness_mode_accepts_direct_source_bundle_beyond_page_budget(
    db_session,
) -> None:
    configured = settings(crawling=True, max_pages=10, completeness=True)
    service = CatalogueIngestionService(db_session, configured, fetcher=MappingFetcher())
    supporting_urls = [f"https://scholarships.gov.uk/example/source-{index}" for index in range(11)]

    response = service.create_run_from_url(
        ROOT,
        supporting_urls=supporting_urls,
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
    )

    run = service.repository.get_run(response.id)
    assert run is not None
    assert run.max_pages_per_candidate == 10


def test_hardened_resume_reuses_persisted_artifact_without_recrawling(
    db_session,
    monkeypatch,
) -> None:
    configured = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://example.openai.azure.com",
        catalogue_ai_model="structured-output-deployment",
        catalogue_ai_input_cost_per_million=Decimal("1"),
        catalogue_ai_output_cost_per_million=Decimal("2"),
        catalogue_bounded_crawling_enabled=True,
        source_monitor_per_host_interval_seconds=0,
    )
    service = HardenedCatalogueIngestionService(
        db_session,
        configured,
        fetcher=MappingFetcher(),
    )
    response = service.create_run_from_url(
        ROOT,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    run = service.repository.get_run(response.id)
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == response.id)
    )
    assert run is not None
    assert candidate is not None
    source = candidate.sources[0]
    source.status = CandidateSourceStatus.FETCHED
    source.artifacts.append(
        CatalogueSourceArtifact(
            final_url=ROOT,
            content_type="text/html",
            content_hash="a" * 64,
            normalized_text="Persisted official scholarship evidence.",
            extraction_method="normalized_text",
            byte_count=40,
            character_count=40,
            fetch_metadata={},
        )
    )
    candidate.status = CandidateStatus.SOURCE_FETCHED
    db_session.flush()
    claim_calls: list[str] = []

    monkeypatch.setattr(service, "_heartbeat_candidate", lambda *_args: None)
    monkeypatch.setattr(
        service,
        "_process_direct_claims",
        lambda *_args: claim_calls.append("claims"),
    )

    def fail_if_crawled(*_args, **_kwargs):
        raise AssertionError("persisted evidence must be reused")

    monkeypatch.setattr(service.acquisition_crawler, "crawl_many", fail_if_crawled)

    service._process_direct_candidate(run, candidate, "lease-token")

    assert claim_calls == ["claims"]


def test_ingestion_keeps_single_page_behavior_when_bounded_crawling_is_disabled(
    db_session,
    tmp_path,
) -> None:
    candidate, sources, fetcher = run_candidate(
        db_session,
        tmp_path,
        crawling=False,
    )

    assert fetcher.calls == [ROOT]
    assert len(sources) == 1
    assert sources[0].canonical_url == ROOT
    assert candidate.status == CandidateStatus.NEEDS_REVIEW
    assert candidate.failure_code == "candidate_only_complete"


def test_ingestion_persists_bounded_same_domain_child_sources_when_enabled(
    db_session,
    tmp_path,
) -> None:
    candidate, sources, fetcher = run_candidate(
        db_session,
        tmp_path,
        crawling=True,
        max_pages=3,
    )

    assert fetcher.calls == [ROOT, DEADLINE, FUNDING]
    assert EXTERNAL not in fetcher.calls
    assert {source.canonical_url for source in sources} == {ROOT, FUNDING, DEADLINE}
    assert all(source.status == CandidateSourceStatus.FETCHED for source in sources)
    assert all(source.is_official for source in sources)
    assert all(source.content_hash for source in sources)
    assert candidate.status == CandidateStatus.NEEDS_REVIEW
    assert candidate.failure_code == "candidate_only_complete"


def test_ingestion_accepts_twenty_five_page_runtime_budget(db_session, tmp_path) -> None:
    candidate, sources, fetcher = run_candidate(
        db_session,
        tmp_path,
        crawling=True,
        max_pages=25,
    )

    assert fetcher.calls == [ROOT, DEADLINE, FUNDING]
    assert len(sources) == 3
    assert candidate.failure_code == "candidate_only_complete"


def test_ingestion_run_page_budget_caps_total_root_and_child_fetches(
    db_session,
    tmp_path,
) -> None:
    _, sources, fetcher = run_candidate(
        db_session,
        tmp_path,
        crawling=True,
        max_pages=2,
    )

    assert fetcher.calls == [ROOT, DEADLINE]
    assert {source.canonical_url for source in sources} == {ROOT, DEADLINE}
