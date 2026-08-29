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

_MAX_ROOT_PAGES = 60
_DEFAULT_TOTAL_BYTES = 60 * 1024 * 1024
_MIN_RELEVANCE_SCORE = 25
_NEAR_DUPLICATE_MIN_CHARS = 2_000
_NEAR_DUPLICATE_TAIL_CHARS = 4_096
_NEAR_DUPLICATE_MAX_LENGTH_DELTA = 512
_POSITIVE_SIGNALS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\b(?:scholarship|scholarships|award|awards|funding)\b", re.I), 20),
    (re.compile(r"\b(?:eligibility|eligible|requirement|requirements)\b", re.I), 30),
    (
        re.compile(
            r"\b(?:advice for applicants?|applicant guidance|how[- ]?to[- ]?apply)\b",
            re.I,
        ),
        40,
    ),
    (re.compile(r"\b(?:apply|application|applications|applicants?)\b", re.I), 20),
    (
        re.compile(
            r"\b(?:deadline|deadlines|timeline|opening date|closing date|application period)\b",
            re.I,
        ),
        35,
    ),
    (re.compile(r"\b(?:benefit|benefits|funding|stipend|tuition|allowance)\b", re.I), 30),
    (
        re.compile(
            r"\b(?:programme|program|course|courses|university list|fields? of study)\b",
            re.I,
        ),
        20,
    ),
    (
        re.compile(
            r"\b(?:required documents?|supporting documents?|document checklist|"
            r"application forms?|template application)\b",
            re.I,
        ),
        35,
    ),
    (re.compile(r"\b(?:document|documents|checklist|forms?)\b", re.I), 20),
    (re.compile(r"\b(?:selection|interview|screening|results?|schedule)\b", re.I), 25),
    (
        re.compile(
            r"\b(?:rules?|regulations?|terms of participation|competition rules?)\b",
            re.I,
        ),
        45,
    ),
    (
        re.compile(
            r"\b(?:subjects?|subject areas?|study areas?|academic disciplines?)\b",
            re.I,
        ),
        30,
    ),
    (
        re.compile(
            r"\b(?:degree tracks?|bachelor(?:['\u2019]s)?|master(?:['\u2019]s)?|doctoral|"
            r"postdoctoral)\b",
            re.I,
        ),
        70,
    ),
    (re.compile(r"\b(?:guideline|guidelines|prospectus)\b", re.I), 20),
    (re.compile(r"\b(?:participating|institutions?|universities)\b", re.I), 15),
    (
        re.compile(
            r"\b(?:nominating agenc(?:y|ies)|nomination route|embassy route|"
            r"application route|country route|(?:embassy|university|nomination) track)\b",
            re.I,
        ),
        30,
    ),
    (re.compile(r"\bprogram(?:me)? offered\b", re.I), 35),
    (re.compile(r"\b(?:faq|frequently asked questions?|guidance)\b", re.I), 30),
)
_NEGATIVE_SIGNALS: tuple[tuple[re.Pattern[str], int], ...] = (
    (
        re.compile(
            r"\b(?:current scholars?|current fellows?|award[- ]?holders?|alumni|"
            r"post[- ]?award|after your award)\b",
            re.I,
        ),
        90,
    ),
    (
        re.compile(
            r"\b(?:code of conduct|departure forms?|stipend advance|disciplinary|"
            r"handbook policies and forms|tenure track|sample tasks?|practice materials?|"
            r"preparation materials?|recommended reading|exam preparation)\b",
            re.I,
        ),
        90,
    ),
    (
        re.compile(
            r"\b(?:calendar|news|newsroom|social media|facebook|instagram|"
            r"linkedin|twitter|privacy|cookie|accessibility|contact us|author|"
            r"find a scholarship|scholarships? and fellowships?|programme pages?)\b",
            re.I,
        ),
        50,
    ),
)


@dataclass(frozen=True, slots=True)
class CrawlBudget:
    """Hard accepted-page and traversal limits for one verified root URL.

    ``max_total_bytes`` caps accepted evidence-page payload bytes. ``SafeSourceFetcher``
    may read one sentinel byte beyond the remaining allowance to detect overflow; robots
    payloads remain separately bounded by the existing safe fetcher policy.
    """

    max_pages: int = _MAX_ROOT_PAGES
    max_depth: int = 3
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
    sort_depth: int
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


def _scholarship_collection_topic(url: str) -> tuple[str, frozenset[str]] | None:
    """Return the scholarship collection path and scheme-specific slug tokens."""

    segments = [segment.casefold() for segment in urlsplit(url).path.split("/") if segment]
    for index, segment in enumerate(segments[:-1]):
        if segment not in {"scholarship", "scholarships"}:
            continue
        slug = segments[index + 1]
        tokens = {
            token.removesuffix("s")
            for token in re.findall(r"[a-z0-9]+", slug)
            if token not in {"scholarship", "scholarships", "application", "applications"}
        }
        return "/".join(segments[: index + 1]), frozenset(tokens)
    return None


def _is_sibling_scholarship_page(root_url: str, candidate_url: str) -> bool:
    """Reject a different scheme reached through a provider-wide scholarship listing."""

    root_topic = _scholarship_collection_topic(root_url)
    candidate_topic = _scholarship_collection_topic(candidate_url)
    if root_topic is None or candidate_topic is None or root_topic[0] != candidate_topic[0]:
        return False
    root_path = urlsplit(root_url).path.rstrip("/").casefold()
    candidate_path = urlsplit(candidate_url).path.rstrip("/").casefold()
    if candidate_path == root_path or candidate_path.startswith(f"{root_path}/"):
        return False
    root_tokens = root_topic[1]
    candidate_tokens = candidate_topic[1]
    return bool(root_tokens and not root_tokens.issubset(candidate_tokens))


def score_crawl_link(link: FetchedLink) -> int:
    """Rank official-site links by deterministic scholarship relevance signals."""

    combined = " ".join(part for part in (link.url, link.text, link.title or "") if part)
    score = 0
    for pattern, weight in _POSITIVE_SIGNALS:
        if pattern.search(combined):
            score += weight
    for pattern, weight in _NEGATIVE_SIGNALS:
        if pattern.search(combined):
            score -= weight
    return score


_GENERIC_PATH_TOKENS = frozenset(
    {
        "about",
        "aspx",
        "content",
        "default",
        "english",
        "index",
        "page",
        "pages",
        "programme",
        "programmes",
        "scholarship",
        "scholarships",
        "scholarshipsgrants",
        "services",
        "site",
        "students",
        "universities",
        "faculty",
    }
)


def _route_path_tokens(url: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9]+", urlsplit(url).path.casefold())
        if len(token) >= 4 and token not in _GENERIC_PATH_TOKENS
    )


def score_crawl_link_for_root(root_url: str, link: FetchedLink) -> int:
    """Prefer pages and documents inside the root scholarship's route namespace."""

    score = score_crawl_link(link)
    candidate_path = urlsplit(link.url).path.rstrip("/").casefold()
    root_path = urlsplit(root_url).path.rstrip("/").casefold()
    if candidate_path == f"{root_path}/about" or (not root_path and candidate_path == "/about"):
        # A concise ``about`` page on a programme microsite commonly contains the
        # authoritative identity, available levels, and funding overview. Keep
        # broader organisational pages such as ``about-us`` below the threshold.
        score += 30
    if _route_path_tokens(root_url) & _route_path_tokens(link.url):
        score += 100
    return score


def _failure_code(exc: SourceFetchError) -> str:
    value = str(exc).strip()
    if not value:
        return "source_fetch_failed"
    return value.split(":", 1)[0].strip() or "source_fetch_failed"


def _is_near_duplicate_evidence(text: str, accepted_texts: list[str]) -> bool:
    """Detect template variants whose substantive body is byte-for-byte identical.

    Some programme sites expose both a default route and an explicit degree-tab route.
    Their page titles differ while the complete evidence body is identical. Comparing a
    long suffix plus a tight length bound removes those duplicates without collapsing
    short pages or pages that merely share navigation/footer boilerplate.
    """

    if len(text) < _NEAR_DUPLICATE_MIN_CHARS:
        return False
    tail_chars = min(_NEAR_DUPLICATE_TAIL_CHARS, len(text) // 2)
    tail = text[-tail_chars:]
    return any(
        abs(len(text) - len(existing)) <= _NEAR_DUPLICATE_MAX_LENGTH_DELTA
        and len(existing) >= _NEAR_DUPLICATE_MIN_CHARS
        and existing[-tail_chars:] == tail
        for existing in accepted_texts
    )


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
    """Explore a ranked, bounded evidence set from an already-verified official host.

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
        accepted_texts: list[str] = []
        queue: list[_QueuedLink] = []
        insertion_order = 0
        total_bytes = 0
        fetch_attempts = 0
        budget_exhausted = False
        previous_host: str | None = None
        crawl_scope_root = normalized_root

        def fetch_page(url: str, *, depth: int, score: int, root: bool = False) -> bool:
            nonlocal total_bytes, fetch_attempts, budget_exhausted, previous_host, crawl_scope_root
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

            if root:
                crawl_scope_root = final_url

            completed_urls.add(url)
            completed_urls.add(final_url)
            seen_urls.add(final_url)
            total_bytes += fetched.bytes_read
            content_hash = fetched.normalized_content_hash or fetched.content_hash
            if content_hash in seen_hashes or _is_near_duplicate_evidence(
                fetched.normalized_text, accepted_texts
            ):
                duplicates.append(final_url)
            else:
                seen_hashes.add(content_hash)
                accepted_texts.append(fetched.normalized_text)
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
            candidates: list[tuple[int, int, str]] = []
            for source_order, link in enumerate(links):
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
                if _is_sibling_scholarship_page(normalized_root, normalized):
                    rejected.append(
                        RejectedCrawlLink(
                            url=normalized,
                            depth=depth,
                            reason="different_scholarship_scheme",
                        )
                    )
                    continue
                if normalized in seen_urls or normalized in completed_urls:
                    continue
                score = score_crawl_link_for_root(crawl_scope_root, link)
                if score < _MIN_RELEVANCE_SCORE:
                    rejected.append(
                        RejectedCrawlLink(
                            url=normalized,
                            depth=depth,
                            reason="low_scholarship_relevance",
                        )
                    )
                    continue
                candidates.append((score, source_order, normalized))

            candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
            for score, _, normalized in candidates[: limits.max_links_per_page]:
                if normalized in seen_urls or normalized in completed_urls:
                    continue
                seen_urls.add(normalized)
                heapq.heappush(
                    queue,
                    _QueuedLink(
                        sort_depth=depth,
                        sort_score=-score,
                        insertion_order=insertion_order,
                        url=normalized,
                        depth=depth,
                        score=score,
                    ),
                )
                insertion_order += 1
            for _, _, normalized in candidates[limits.max_links_per_page :]:
                rejected.append(
                    RejectedCrawlLink(
                        url=normalized,
                        depth=depth,
                        reason="page_link_budget_exceeded",
                    )
                )

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
