import hashlib

import pytest

from app.modules.catalogue_ingestion.crawler import (
    BoundedOfficialSiteCrawler,
    CrawlBudget,
    normalize_crawl_url,
    score_crawl_link,
)
from app.modules.opportunities.source_monitor import FetchedLink, FetchedSource, SourceFetchError

ROOT = "https://example.edu/scholarships/csc"


def fetched_page(
    url: str,
    text: str,
    *,
    links: tuple[FetchedLink, ...] = (),
    content_hash: str | None = None,
    final_url: str | None = None,
) -> FetchedSource:
    normalized_hash = content_hash or hashlib.sha256(text.encode()).hexdigest()
    return FetchedSource(
        url=url,
        final_url=final_url or url,
        content_hash=normalized_hash,
        excerpt_text=text[:500],
        section_label="Scholarship",
        bytes_read=len(text.encode()),
        normalized_text=text,
        normalized_content_hash=normalized_hash,
        content_type="text/html",
        links=links,
    )


class FakeFetcher:
    def __init__(self, responses: dict[str, FetchedSource | Exception]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def _response(self, url: str) -> FetchedSource:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    def fetch(self, url: str) -> FetchedSource:
        return self._response(url)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        response = self._response(url)
        if response.bytes_read > max_bytes:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        return response


def test_crawl_url_normalization_removes_tracking_fragment_and_default_port() -> None:
    assert (
        normalize_crawl_url(
            "https://EXAMPLE.edu:443/scholarships/csc/?utm_source=test&b=2&a=1#deadline"
        )
        == "https://example.edu/scholarships/csc?a=1&b=2"
    )


def test_bounded_crawler_fetches_root_then_highest_value_same_host_pages() -> None:
    funding = "https://example.edu/scholarships/csc/funding"
    deadline = "https://example.edu/scholarships/csc/deadline"
    news = "https://example.edu/news/archive"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "CSC scholarship overview with official application guidance.",
                links=(
                    FetchedLink(url=news, text="University news archive"),
                    FetchedLink(url=deadline, text="Application deadline and timeline"),
                    FetchedLink(url=funding, text="Scholarship funding benefits and tuition"),
                ),
            ),
            funding: fetched_page(funding, "Funding, stipend and tuition coverage details."),
            deadline: fetched_page(deadline, "Official application deadline and timeline details."),
            news: fetched_page(news, "Unrelated news archive."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=3, max_depth=1),
    )

    assert fetcher.calls == [ROOT, deadline, funding]
    assert [page.url for page in result.pages] == [ROOT, deadline, funding]
    assert news not in fetcher.calls
    assert result.budget_exhausted is True


def test_crawler_skips_static_and_calendar_resources_before_fetch() -> None:
    script = "https://example.edu/build/app.js"
    calendar = "https://example.edu/calendar/event.ics"
    eligibility = "https://example.edu/scholarships/csc/eligibility"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Official scholarship overview.",
                links=(
                    FetchedLink(url=script, text=""),
                    FetchedLink(url=calendar, text=""),
                    FetchedLink(url=eligibility, text="Eligibility requirements"),
                ),
            ),
            eligibility: fetched_page(eligibility, "Official eligibility requirements."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, eligibility]
    assert [item.reason for item in result.rejected].count("non_content_resource") == 2


def test_unlabeled_schedule_link_ranks_below_labeled_scholarship_content() -> None:
    blank_schedule = FetchedLink(
        url="https://example.edu/calendar/schedule-items/application-form",
        text="",
    )
    eligibility = FetchedLink(
        url="https://example.edu/scholarships/csc/eligibility",
        text="Eligibility requirements",
    )

    assert score_crawl_link(blank_schedule) < score_crawl_link(eligibility)


def test_bounded_crawler_rejects_cross_domain_auth_and_session_links() -> None:
    eligibility = "https://example.edu/scholarships/csc/eligibility"
    login = "https://example.edu/login?next=/scholarships/csc"
    external = "https://unrelated.example/scholarships/csc"
    session = "https://example.edu/account/session/123"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Official scholarship overview.",
                links=(
                    FetchedLink(url=external, text="External scholarship copy"),
                    FetchedLink(url=login, text="Login to apply"),
                    FetchedLink(url=session, text="Application session"),
                    FetchedLink(url=eligibility, text="Scholarship eligibility requirements"),
                ),
            ),
            eligibility: fetched_page(eligibility, "Official eligibility requirements."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, eligibility]
    assert {item.reason for item in result.rejected} >= {
        "cross_domain_unverified",
        "authentication_or_session_link",
    }


def test_bounded_crawler_enforces_depth_limit() -> None:
    level_one = "https://example.edu/scholarships/csc/requirements"
    level_two = "https://example.edu/scholarships/csc/requirements/documents"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(FetchedLink(url=level_one, text="Eligibility requirements"),),
            ),
            level_one: fetched_page(
                level_one,
                "Eligibility requirements.",
                links=(FetchedLink(url=level_two, text="Required documents"),),
            ),
            level_two: fetched_page(level_two, "Required document list."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, level_one]
    assert [page.depth for page in result.pages] == [0, 1]
    assert level_two not in fetcher.calls


def test_bounded_crawler_normalizes_and_deduplicates_urls_before_fetch() -> None:
    canonical = "https://example.edu/scholarships/csc/deadline"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(
                        url=f"{canonical}/?utm_source=one#dates",
                        text="Application deadline",
                    ),
                    FetchedLink(
                        url=f"{canonical}?utm_medium=two",
                        text="Closing date",
                    ),
                ),
            ),
            canonical: fetched_page(canonical, "Official application deadline."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, canonical]
    assert [page.url for page in result.pages] == [ROOT, canonical]


def test_bounded_crawler_does_not_refetch_redirect_destination_already_queued() -> None:
    old_url = "https://example.edu/scholarships/csc/funding-old"
    canonical = "https://example.edu/scholarships/csc/funding"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(
                        url=old_url,
                        text="Scholarship funding benefits and tuition",
                    ),
                    FetchedLink(url=canonical, text="Scholarship funding"),
                ),
            ),
            old_url: fetched_page(
                old_url,
                "Official funding details.",
                final_url=canonical,
            ),
            canonical: fetched_page(canonical, "Official funding details."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, old_url]
    assert [page.url for page in result.pages] == [ROOT, canonical]


def test_bounded_crawler_deduplicates_fetched_content_hashes() -> None:
    first = "https://example.edu/scholarships/csc/funding"
    second = "https://example.edu/scholarships/csc/benefits"
    duplicate_hash = hashlib.sha256(b"same official content").hexdigest()
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(url=first, text="Scholarship funding"),
                    FetchedLink(url=second, text="Scholarship benefits"),
                ),
            ),
            first: fetched_page(first, "Same official content", content_hash=duplicate_hash),
            second: fetched_page(second, "Same official content", content_hash=duplicate_hash),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, first, second]
    assert len(result.pages) == 2
    assert result.duplicate_content_urls == (second,)


def test_bounded_crawler_records_child_failure_and_continues() -> None:
    broken = "https://example.edu/scholarships/csc/deadline"
    eligibility = "https://example.edu/scholarships/csc/eligibility"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(url=broken, text="Application deadline"),
                    FetchedLink(url=eligibility, text="Eligibility requirements"),
                ),
            ),
            broken: SourceFetchError("source_unreachable: http_503"),
            eligibility: fetched_page(eligibility, "Official eligibility requirements."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, broken, eligibility]
    assert [page.url for page in result.pages] == [ROOT, eligibility]
    assert result.failures[0].url == broken
    assert result.failures[0].reason == "source_unreachable"


def test_bounded_crawler_root_failure_fails_closed() -> None:
    fetcher = FakeFetcher({ROOT: SourceFetchError("robots_disallowed")})

    with pytest.raises(SourceFetchError, match="robots_disallowed"):
        BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
            ROOT,
            budget=CrawlBudget(max_pages=10, max_depth=1),
        )


def test_bounded_crawler_requires_fetcher_that_can_enforce_remaining_bytes() -> None:
    class LegacyFetcher:
        def fetch(self, url: str) -> FetchedSource:
            return fetched_page(url, "Official scholarship overview.")

    with pytest.raises(
        SourceFetchError,
        match="crawler_fetcher_does_not_support_byte_budget",
    ):
        BoundedOfficialSiteCrawler(fetcher=LegacyFetcher()).crawl(
            ROOT,
            budget=CrawlBudget(max_pages=10, max_depth=1),
        )


def test_bounded_crawler_stops_before_accepting_page_over_remaining_byte_budget() -> None:
    first = "https://example.edu/scholarships/csc/funding"
    second = "https://example.edu/scholarships/csc/deadline"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "R" * 40,
                links=(
                    FetchedLink(url=first, text="Scholarship funding benefits"),
                    FetchedLink(url=second, text="Application deadline"),
                ),
            ),
            first: fetched_page(first, "F" * 70),
            second: fetched_page(second, "D" * 20),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1, max_total_bytes=50),
    )

    assert fetcher.calls == [ROOT, second]
    assert result.budget_exhausted is True
    assert result.total_bytes == 40
    assert result.total_bytes <= 50
    assert result.failures[-1].url == second
    assert result.failures[-1].reason == "crawl_byte_budget_exceeded"
    assert first not in fetcher.calls
