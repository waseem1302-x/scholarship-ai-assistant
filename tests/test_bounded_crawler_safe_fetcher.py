from app.modules.opportunities.source_monitor import (
    FetchedLink,
    SafeRedirectHandler,
    SafeSourceFetcher,
)

ROOT = "https://example.edu/scholarships/csc"


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
