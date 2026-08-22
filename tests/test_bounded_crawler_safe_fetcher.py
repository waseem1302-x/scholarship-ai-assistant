from urllib.request import Request

import pytest

from app.modules.catalogue_ingestion.crawler import BoundedOfficialSiteCrawler, CrawlBudget
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    SafeRedirectHandler,
    SafeSourceFetcher,
    SourceFetchError,
)

ROOT = "https://example.edu/scholarships/csc"


def _configure_safe_fetcher(monkeypatch, payload: bytes, *, configured_max_bytes: int = 1_000_000):
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
            return payload[:limit]

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

    fetcher = SafeSourceFetcher(max_bytes=configured_max_bytes)
    fetcher.opener = Opener()
    fetcher._robots["https://example.edu"] = None
    return fetcher


def test_safe_source_fetcher_extracts_links_for_crawler(monkeypatch) -> None:
    payload = (
        b"<html><body><main>Official CSC scholarship information with enough text."
        b'<a href="/scholarships/csc/deadline?utm_source=x#dates" '
        b'title="Timeline">Application deadline</a>'
        b'<a href="https://outside.example/csc">External page</a>'
        b"</main></body></html>"
    )
    fetcher = _configure_safe_fetcher(monkeypatch, payload)

    fetched = fetcher.fetch(ROOT)

    assert fetched.links == (
        FetchedLink(
            url="https://example.edu/scholarships/csc/deadline?utm_source=x#dates",
            text="Application deadline",
            title="Timeline",
        ),
        FetchedLink(url="https://outside.example/csc", text="External page", title=None),
    )


def test_bounded_crawler_applies_remaining_budget_through_safe_fetcher(monkeypatch) -> None:
    payload = b"<html><body>Official scholarship evidence that exceeds thirty bytes.</body></html>"
    fetcher = _configure_safe_fetcher(monkeypatch, payload, configured_max_bytes=100)

    with pytest.raises(SourceFetchError, match="crawl_byte_budget_exceeded"):
        BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
            ROOT,
            budget=CrawlBudget(max_pages=1, max_depth=0, max_total_bytes=30),
        )


def test_safe_source_fetcher_keeps_its_stricter_per_page_limit(monkeypatch) -> None:
    payload = b"<html><body>Official scholarship evidence that exceeds forty bytes.</body></html>"
    fetcher = _configure_safe_fetcher(monkeypatch, payload, configured_max_bytes=40)

    with pytest.raises(SourceFetchError, match="source_too_large"):
        fetcher.fetch(ROOT)


def test_safe_redirect_handler_is_capped_at_five_redirects() -> None:
    assert SafeRedirectHandler.max_redirections == 5


def test_safe_redirect_handler_upgrades_same_host_downgrade_without_http_request(
    monkeypatch,
) -> None:
    validated: list[str] = []
    monkeypatch.setattr(
        "app.modules.opportunities.source_monitor.validate_monitor_url",
        validated.append,
    )
    request = Request("https://www.example.go.jp/scholarship")

    redirected = SafeRedirectHandler().redirect_request(
        request,
        None,
        301,
        "Moved",
        {},
        "http://www.example.go.jp/scholarship/",
    )

    assert redirected is not None
    assert redirected.full_url == "https://www.example.go.jp/scholarship/"
    assert validated == ["https://www.example.go.jp/scholarship/"]


def test_safe_redirect_handler_does_not_upgrade_cross_host_downgrade() -> None:
    request = Request("https://www.example.go.jp/scholarship")

    with pytest.raises(SourceFetchError, match="only https"):
        SafeRedirectHandler().redirect_request(
            request,
            None,
            301,
            "Moved",
            {},
            "http://outside.example/scholarship/",
        )

    with pytest.raises(SourceFetchError, match="invalid redirect port"):
        SafeRedirectHandler().redirect_request(
            request,
            None,
            301,
            "Moved",
            {},
            "http://www.example.go.jp:not-a-port/scholarship/",
        )
