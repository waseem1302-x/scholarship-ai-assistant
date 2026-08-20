"""Bounded official-site crawling that never bypasses ``SafeSourceFetcher``.

PR4 deliberately separates crawl orchestration from network safety. The crawler
ranks and schedules already-linked public pages, while every actual request is
performed by the injected ``SourceFetcher`` implementation. In production that
boundary remains ``SafeSourceFetcher`` with its HTTPS, DNS/IP, robots, redirect,
content-type, and byte limits.
"""

from __future__ import annotations

import heapq
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

from app.modules.catalogue_ingestion.url_policy import (
    is_authentication_or_session_url,
    normalize_crawl_url_identity,
)
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SafeSourceFetcher,
    SourceFetcher,
    SourceFetchError,
)

_MAX_ROOT_PAGES = 10
_DEFAULT_TOTAL_BYTES = 20 * 1024 * 1024
_POSITIVE_SIGNALS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(?:scholarship|scholarships|award|awards|funding)\b", re.I), 20),
    (re.compile(r"\b(?:eligibility|eligible|requirement|requirements)\b", re.I), 15),
    (re.compile(r"\b(?:apply|application|applications|how[- ]?to)\b", re.I), 15),
    (re.compile(r"\b(?:deadline|deadlines|timeline|closing date)\b", re.I), 15),
    (re.compile(r"\b(?:benefit|benefits|funding|stipend|tuition)\b", re.I), 15),
    (re.compile(r"\b(?:programme|program|course|courses|university list)\b", re.I), 10),
    (re.compile(r"\b(?:faq|guidance|terms)\b", re.I), 8),
)
_NEGATIVE_SIGNAL = re.compile(
    r"\b(?:calendar|news archive|newsroom|social media|facebook|instagram|linkedin|twitter)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CrawlBudget:
    """Hard accepted-page and traversal limits for one verified root URL.

    ``max_total_bytes`` caps accepted evidence-page payload bytes. ``SafeSourceFetcher``
    may read one sentinel byte beyond the remaining allowance to detect overflow; robots
    payloads remain separately bounded by the existing safe fetcher policy.
    """

    max_pages: int = _MAX_ROOT_PAGES
    max_depth: int = 2
    max_total_bytes: int = _DEFAULT_TOTAL_BYTES
    max_links_per_page: int = 100
    per_host_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_pages <= _MAX_ROOT_PAGES:
            raise ValueError(f"max_pages must be between 1 and {_MAX_ROOT_PAGES}")
        if not 0 <= self.max_depth <= 3:
            raise ValueError("max_depth must be between 0 and 3")
        if self.max_total_bytes < 1:
            raise ValueError("max_total_bytes must be positive")
        if not 1 <= self.max_links_per_page <= 500:
            raise ValueError("max_links_per_page must be between 1 and 500")
        if self.per_host_interval_seconds < 0:
            raise ValueError("per_host_interval_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    depth: int
    score: int
    fetched: FetchedSource


@dataclass(frozen=True, slots=True)
class CrawlFailure:
    url: str
    depth: int
    reason: str


@dataclass(frozen=True, slots=True)
class RejectedCrawlLink:
    url: str
    depth: int
    reason: str


@dataclass(frozen=True, slots=True)
class CrawlResult:
    root_url: str
    pages: tuple[CrawledPage, ...]
    failures: tuple[CrawlFailure, ...]
    rejected: tuple[RejectedCrawlLink, ...]
    duplicate_content_urls: tuple[str, ...]
    total_bytes: int
    fetch_attempts: int
    budget_exhausted: bool


@dataclass(order=True, slots=True)
class _QueuedLink:
    sort_score: int
    insertion_order: int
    url: str = field(compare=False)
    depth: int = field(compare=False)
    score: int = field(compare=False)


def normalize_crawl_url(value: str) -> str | None:
    """Normalize public HTTPS crawl identities without erasing meaningful query data."""

    return normalize_crawl_url_identity(value)


def _host(value: str) -> str | None:
    normalized = normalize_crawl_url(value)
    if normalized is None:
        return None
    return urlsplit(normalized).hostname


def _is_authentication_or_session_link(url: str) -> bool:
    return is_authentication_or_session_url(url)


def score_crawl_link(link: FetchedLink) -> int:
    """Rank official-site links by deterministic scholarship relevance signals."""

    combined = " ".join(part for part in (link.url, link.text, link.title or "") if part)
    score = 30
    for pattern, weight in _POSITIVE_SIGNALS:
        if pattern.search(combined):
            score += weight
    if _NEGATIVE_SIGNAL.search(combined):
        score -= 20
    return score


def _failure_code(exc: SourceFetchError) -> str:
    value = str(exc).strip()
    if not value:
        return "source_fetch_failed"
    return value.split(":", 1)[0].strip() or "source_fetch_failed"


def _safe_fetch_with_limit(
    fetcher: SafeSourceFetcher,
    url: str,
    *,
    max_bytes: int,
) -> FetchedSource:
    """Reuse SafeSourceFetcher while tightening only the current page byte allowance.

    The clone shares the configured opener and robots cache, so PR4 does not introduce a
    second network path. Existing host-specific policies stay intact except that their
    payload limit can only become stricter for this one request.
    """

    original_policy = fetcher.policy_for(url)
    bounded_policies = {
        host: replace(policy, max_bytes=min(policy.max_bytes, max_bytes))
        for host, policy in fetcher.crawl_policies.items()
    }
    bounded = SafeSourceFetcher(
        timeout_seconds=fetcher.timeout_seconds,
        max_bytes=min(fetcher.max_bytes, max_bytes),
        crawl_policies=bounded_policies,
    )
    bounded.opener = fetcher.opener
    bounded._robots = fetcher._robots
    try:
        return bounded.fetch(url)
    except SourceFetchError as exc:
        if _failure_code(exc) == "source_too_large" and max_bytes < original_policy.max_bytes:
            raise SourceFetchError("crawl_byte_budget_exceeded") from exc
        raise


def _fetch_with_limit(fetcher: SourceFetcher, url: str, *, max_bytes: int) -> FetchedSource:
    """Fetch through a boundary capable of enforcing the remaining crawl allowance."""

    if max_bytes < 1:
        raise SourceFetchError("crawl_byte_budget_exceeded")
    bounded_fetch = getattr(fetcher, "fetch_with_limit", None)
    if callable(bounded_fetch):
        return bounded_fetch(url, max_bytes=max_bytes)
    if isinstance(fetcher, SafeSourceFetcher):
        return _safe_fetch_with_limit(fetcher, url, max_bytes=max_bytes)
    raise SourceFetchError("crawler_fetcher_does_not_support_byte_budget")


class BoundedOfficialSiteCrawler:
    """Explore a small ranked slice of one already-verified official host.

    The crawler performs no HTTP itself. Callers inject the existing source
    fetcher boundary, which keeps SSRF, robots, redirect, peer-IP, MIME, and
    response-size checks centralized in one implementation. Crawling is sequential,
    giving each host an effective concurrency cap of one in addition to the optional
    inter-request interval.
    """

    def __init__(
        self,
        *,
        fetcher: SourceFetcher,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.fetcher = fetcher
        self.sleeper = sleeper

    def crawl(
        self,
        root_url: str,
        *,
        budget: CrawlBudget | None = None,
        allowed_hosts: set[str] | None = None,
    ) -> CrawlResult:
        limits = budget or CrawlBudget()
        normalized_root = normalize_crawl_url(root_url)
        if normalized_root is None:
            raise SourceFetchError("invalid_crawl_root")
        root_host = _host(normalized_root)
        assert root_host is not None
        permitted_hosts = {
            host.casefold().strip(".") for host in (allowed_hosts or {root_host}) if host.strip()
        }
        if root_host not in permitted_hosts:
            raise SourceFetchError("crawl_root_host_not_verified")

        pages: list[CrawledPage] = []
        failures: list[CrawlFailure] = []
        rejected: list[RejectedCrawlLink] = []
        duplicates: list[str] = []
        seen_urls = {normalized_root}
        completed_urls: set[str] = set()
        seen_hashes: set[str] = set()
        queue: list[_QueuedLink] = []
        insertion_order = 0
        total_bytes = 0
        fetch_attempts = 0
        budget_exhausted = False
        previous_host: str | None = None

        def fetch_page(url: str, *, depth: int, score: int, root: bool = False) -> bool:
            nonlocal total_bytes, fetch_attempts, budget_exhausted, previous_host
            if fetch_attempts >= limits.max_pages:
                budget_exhausted = True
                return False
            remaining_bytes = limits.max_total_bytes - total_bytes
            if remaining_bytes <= 0:
                budget_exhausted = True
                return False

            current_host = _host(url)
            if (
                previous_host is not None
                and current_host == previous_host
                and limits.per_host_interval_seconds > 0
            ):
                self.sleeper(limits.per_host_interval_seconds)

            fetch_attempts += 1
            try:
                fetched = _fetch_with_limit(self.fetcher, url, max_bytes=remaining_bytes)
            except SourceFetchError as exc:
                failure_code = _failure_code(exc)
                if root:
                    raise
                failures.append(CrawlFailure(url=url, depth=depth, reason=failure_code))
                previous_host = current_host
                if failure_code in {
                    "crawl_byte_budget_exceeded",
                    "crawler_fetcher_does_not_support_byte_budget",
                }:
                    budget_exhausted = True
                    return False
                return True

            if fetched.bytes_read > remaining_bytes:
                if root:
                    raise SourceFetchError("crawler_fetcher_violated_byte_budget")
                failures.append(
                    CrawlFailure(
                        url=url,
                        depth=depth,
                        reason="crawler_fetcher_violated_byte_budget",
                    )
                )
                previous_host = current_host
                budget_exhausted = True
                return False

            final_url = normalize_crawl_url(fetched.final_url)
            if final_url is None:
                if root:
                    raise SourceFetchError("crawler_root_redirect_invalid")
                failures.append(
                    CrawlFailure(url=url, depth=depth, reason="redirected_to_invalid_url")
                )
                previous_host = current_host
                return True
            final_host = _host(final_url)
            if final_host not in permitted_hosts:
                if root:
                    raise SourceFetchError("crawler_root_redirect_left_verified_domain")
                rejected.append(
                    RejectedCrawlLink(
                        url=final_url,
                        depth=depth,
                        reason="cross_domain_unverified",
                    )
                )
                previous_host = current_host
                return True

            completed_urls.add(url)
            completed_urls.add(final_url)
            seen_urls.add(final_url)
            total_bytes += fetched.bytes_read
            content_hash = fetched.normalized_content_hash or fetched.content_hash
            if content_hash in seen_hashes:
                duplicates.append(final_url)
            else:
                seen_hashes.add(content_hash)
                pages.append(CrawledPage(url=final_url, depth=depth, score=score, fetched=fetched))
                if depth < limits.max_depth:
                    enqueue_links(fetched.links, depth=depth + 1)

            previous_host = final_host
            if total_bytes >= limits.max_total_bytes:
                budget_exhausted = bool(queue)
                return not budget_exhausted
            return True

        def enqueue_links(links: tuple[FetchedLink, ...], *, depth: int) -> None:
            nonlocal insertion_order
            considered = 0
            for link in links:
                if considered >= limits.max_links_per_page:
                    break
                considered += 1
                normalized = normalize_crawl_url(link.url)
                if normalized is None:
                    rejected.append(
                        RejectedCrawlLink(
                            url=link.url,
                            depth=depth,
                            reason="invalid_or_unsafe_url",
                        )
                    )
                    continue
                if _is_authentication_or_session_link(normalized):
                    rejected.append(
                        RejectedCrawlLink(
                            url=normalized,
                            depth=depth,
                            reason="authentication_or_session_link",
                        )
                    )
                    continue
                if _host(normalized) not in permitted_hosts:
                    rejected.append(
                        RejectedCrawlLink(
                            url=normalized,
                            depth=depth,
                            reason="cross_domain_unverified",
                        )
                    )
                    continue
                if normalized in seen_urls or normalized in completed_urls:
                    continue
                seen_urls.add(normalized)
                score = score_crawl_link(link)
                heapq.heappush(
                    queue,
                    _QueuedLink(
                        sort_score=-score,
                        insertion_order=insertion_order,
                        url=normalized,
                        depth=depth,
                        score=score,
                    ),
                )
                insertion_order += 1

        if not fetch_page(normalized_root, depth=0, score=100, root=True):
            return CrawlResult(
                root_url=normalized_root,
                pages=tuple(pages),
                failures=tuple(failures),
                rejected=tuple(rejected),
                duplicate_content_urls=tuple(duplicates),
                total_bytes=total_bytes,
                fetch_attempts=fetch_attempts,
                budget_exhausted=True,
            )

        while queue and not budget_exhausted:
            if fetch_attempts >= limits.max_pages:
                budget_exhausted = True
                break
            item = heapq.heappop(queue)
            if item.depth > limits.max_depth or item.url in completed_urls:
                continue
            if not fetch_page(item.url, depth=item.depth, score=item.score):
                break

        if queue and fetch_attempts >= limits.max_pages:
            budget_exhausted = True

        return CrawlResult(
            root_url=normalized_root,
            pages=tuple(pages),
            failures=tuple(failures),
            rejected=tuple(rejected),
            duplicate_content_urls=tuple(duplicates),
            total_bytes=total_bytes,
            fetch_attempts=fetch_attempts,
            budget_exhausted=budget_exhausted,
        )


__all__ = [
    "BoundedOfficialSiteCrawler",
    "CrawlBudget",
    "CrawlFailure",
    "CrawlResult",
    "CrawledPage",
    "RejectedCrawlLink",
    "normalize_crawl_url",
    "score_crawl_link",
]
