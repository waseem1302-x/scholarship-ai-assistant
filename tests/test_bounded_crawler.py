import hashlib

import pytest

from app.modules.catalogue_ingestion.crawler import (
    BoundedOfficialSiteCrawler,
    CrawlBudget,
    normalize_crawl_url,
)
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SafeRedirectHandler,
    SafeSourceFetcher,
    SourceFetchError,
)

ROOT = "https://example.edu/scholarships/csc"


def fetched_page(
    url: str,
    text: str,
    *,
    links: tuple[FetchedLink, ...] = (),
    content_hash: str | None = None,
) -> FetchedSource:
    normalized_hash = content_hash or hashlib.sha256(text.encode()).hexdigest()
    return FetchedSource(
        url=url,
        final_url=url,
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

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def test_crawl_url_normalization_removes_tracking_fragment_and_default_port() -> None:
    assert normalize_crawl_url(
        "https://EXAMPLE.edu:443/scholarships/csc/?utm_source=test&b=2&a=1#deadline"
    ) == "https://example.edu/scholarships/csc?a=1&b=2"


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

    assert fetcher.calls == [ROOT, funding, deadline]
    assert [page.url for page in result.pages] == [ROOT, funding, deadline]
    assert news not in fetcher.calls
    assert result.budget_exhausted is True


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


def test_bounded_crawler_stops_after_total_byte_budget_is_exceeded() -> None:
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
        budget=CrawlBudget(max_pages=10, max_depth=1, max_total_bytes=100),
    )

    assert fetcher.calls == [ROOT, first]
    assert result.budget_exhausted is True
    assert result.total_bytes == 110
    assert second not in fetcher.calls


def test_safe_source_fetcher_extracts_links_for_crawler(monkeypatch) -> None:
    class Headers:
        def get_content_type(self) -> str:
            return "text/html"

    class Response:
        headers = Headers()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self) -> str:
            return ROOT

        def read(self, limit: int) -> bytes:
            del limit
            return (
                b"<html><body><main>Official CSC scholarship information with enough text."
                b'<a href="/scholarships/csc/deadline?utm_source=x#dates" '
                b'title="Timeline">Application deadline</a>'
                b'<a href="https://outside.example/csc">External page</a>'
                b"</main></body></html>"
            )

    class Opener:
        def open(self, request, timeout: int):
            del request, timeout
            return Response()

    monkeypatch.setattr(
        "app.modules.opportunities.source_monitor.validate_monitor_url",
        lambda url: None,
    )
    monkeypatch.setattr(
        "app.modules.opportunities.source_monitor.validate_response_peer",
        lambda response: None,
    )

    fetcher = SafeSourceFetcher()
    fetcher.opener = Opener()
    fetcher._robots["https://example.edu"] = None

    fetched = fetcher.fetch(ROOT)

    assert fetched.links == (
        FetchedLink(
            url="https://example.edu/scholarships/csc/deadline?utm_source=x#dates",
            text="Application deadline",
            title="Timeline",
        ),
        FetchedLink(url="https://outside.example/csc", text="External page", title=None),
    )


def test_safe_redirect_handler_is_capped_at_five_redirects() -> None:
    assert SafeRedirectHandler.max_redirections == 5
