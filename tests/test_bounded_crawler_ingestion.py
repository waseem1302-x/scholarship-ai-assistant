import hashlib
import json

from sqlalchemy import select

from app.core.config import Settings
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    IngestionMode,
)
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.opportunities.source_monitor import FetchedLink, FetchedSource

ROOT = "https://scholarships.gov.uk/example"
FUNDING = "https://scholarships.gov.uk/example/funding"
DEADLINE = "https://scholarships.gov.uk/example/deadline"
EXTERNAL = "https://third-party.example/example"


def settings(*, crawling: bool, max_pages: int = 3) -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
        catalogue_bounded_crawling_enabled=crawling,
        catalogue_ai_max_pages_per_candidate=max_pages,
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

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        return self.responses[url]


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


def test_bounded_crawling_flag_defaults_off() -> None:
    configured = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="test-secret-that-is-at-least-32-characters-long",
    )

    assert configured.catalogue_bounded_crawling_enabled is False


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
