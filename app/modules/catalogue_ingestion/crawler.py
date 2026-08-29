"""Topology-aware bounded crawling over already-verified official sources.

Network safety remains delegated to the injected ``SourceFetcher`` boundary. The crawler owns
frontier ranking, deduplication, per-dimension budgets, typed authority for cross-domain roots, and
browser/OCR escalation requests. It never bypasses authentication, CAPTCHA, robots, redirect,
MIME, byte, or host restrictions.
"""

from __future__ import annotations

import hashlib
import heapq
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from app.modules.catalogue_ingestion.acquisition_planner import AcquisitionFrontierNeed
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
_MAX_FETCH_ATTEMPTS = 100
_MAX_ACCEPTED_ARTIFACTS = 25
_DEFAULT_TOTAL_BYTES = 20 * 1024 * 1024
_DEFAULT_WALL_SECONDS = 120.0
_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv"}
_IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_CHALLENGE_MARKERS = (
    "captcha",
    "verify you are human",
    "checking your browser",
    "access denied",
    "challenge-platform",
    "cf-chl-",
)
_JAVASCRIPT_SHELL_MARKERS = (
    "please enable javascript",
    "enable javascript to continue",
    "javascript is required",
    "loading homepage",
    "loading page",
    "app-root",
    "__next_data__",
)
_NEGATIVE_TERMS = (
    "news archive",
    "newsroom",
    "press release",
    "social media",
    "facebook",
    "instagram",
    "linkedin",
    "twitter",
    "x.com",
    "actualités",
    "noticias",
    "berita",
)
_DEFAULT_LEXICON: dict[str, tuple[str, ...]] = {
    "identity": (
        "scholarship",
        "scholarships",
        "award",
        "fellowship",
        "bourse",
        "beca",
        "bolsa",
        "stipendium",
        "奨学金",
        "奖学金",
        "장학금",
        "منحة",
        "biasiswa",
        "beasiswa",
    ),
    "programmes": (
        "programme",
        "program",
        "course",
        "degree",
        "study programme",
        "programa",
        "curso",
        "formation",
        "studiengang",
        "学部",
        "研究科",
        "课程",
        "专业",
        "프로그램",
        "برنامج",
        "program pengajian",
        "program studi",
    ),
    "programme_details": (
        "curriculum",
        "duration",
        "field of study",
        "subject",
        "major",
        "discipline",
        "duración",
        "durée",
        "研究分野",
        "专业",
        "tempoh",
        "bidang studi",
    ),
    "routes": (
        "application route",
        "nomination",
        "embassy",
        "university recommendation",
        "application channel",
        "track",
        "voie",
        "ruta",
        "推薦",
        "大使館",
        "신청 경로",
        "مسار التقديم",
        "laluan permohonan",
        "jalur pendaftaran",
    ),
    "eligibility": (
        "eligibility",
        "eligible",
        "requirement",
        "requirements",
        "admissibility",
        "requisitos",
        "elegibilidade",
        "資格",
        "申请资格",
        "자격",
        "الأهلية",
        "kelayakan",
        "persyaratan",
    ),
    "eligibility_context": (
        "condition",
        "restriction",
        "exclusion",
        "exception",
        "conditions",
        "restricción",
        "除外",
        "제외",
        "شروط",
        "syarat",
    ),
    "documents_core": (
        "document",
        "documents",
        "checklist",
        "form",
        "formular",
        "documentos",
        "documents requis",
        "書類",
        "材料",
        "서류",
        "المستندات",
        "dokumen",
    ),
    "documents_requirements": (
        "certified",
        "translation",
        "original",
        "copy",
        "submission",
        "certificación",
        "traduction",
        "証明",
        "翻译",
        "인증",
        "ترجمة",
        "terjemahan",
    ),
    "documents_counts": ("original", "copies", "copy", "部", "份", "salinan"),
    "documents_format": (
        "format",
        "template",
        "download",
        "pdf",
        "docx",
        "xlsx",
        "csv",
        "様式",
        "表格",
        "borang",
        "formulir",
    ),
    "funding": (
        "funding",
        "stipend",
        "tuition",
        "allowance",
        "benefit",
        "coverage",
        "financement",
        "financiación",
        "mensualité",
        "学費",
        "奨学金額",
        "资助",
        "学费",
        "지원금",
        "التمويل",
        "elaun",
        "tunjangan",
    ),
    "application_timeline": (
        "apply",
        "application",
        "deadline",
        "timeline",
        "schedule",
        "closing date",
        "candidature",
        "fecha límite",
        "prazo",
        "bewerbung",
        "締切",
        "申請",
        "截止日期",
        "申请",
        "마감",
        "신청",
        "الموعد النهائي",
        "permohonan",
        "tarikh tutup",
        "pendaftaran",
        "batas waktu",
    ),
}


class AcquisitionAuthority(StrEnum):
    PROGRAMME_OWNER = "official_programme_owner"
    GOVERNMENT_MINISTRY = "official_government_ministry"
    DELIVERY_PARTNER = "official_delivery_partner"
    INSTITUTION = "institution_specific_authority"
    REVIEWED_AUXILIARY = "reviewed_auxiliary_source"


class StaticPageSufficiency(StrEnum):
    FULL_CONTENT = "full_content"
    PARTIAL_CONTENT = "partial_content"
    JAVASCRIPT_SHELL = "javascript_shell"
    CHALLENGE = "challenge_login_captcha"
    UNSUPPORTED = "unsupported"


class AcquisitionEscalationKind(StrEnum):
    BROWSER_RENDER = "browser_render"
    OCR = "ocr"
    DOCUMENT_CONVERSION = "document_conversion"


@dataclass(frozen=True, slots=True)
class AcquisitionSeed:
    url: str
    authority: AcquisitionAuthority = AcquisitionAuthority.PROGRAMME_OWNER


@dataclass(frozen=True, slots=True)
class AcquisitionLexicon:
    terms_by_objective: Mapping[str, tuple[str, ...]]
    negative_terms: tuple[str, ...] = _NEGATIVE_TERMS

    @classmethod
    def defaults(cls) -> "AcquisitionLexicon":
        return cls(terms_by_objective=dict(_DEFAULT_LEXICON))

    @classmethod
    def from_mapping(
        cls,
        overrides: Mapping[str, Sequence[str]] | None,
    ) -> "AcquisitionLexicon":
        merged = {key: list(values) for key, values in _DEFAULT_LEXICON.items()}
        for objective, values in (overrides or {}).items():
            normalized = [" ".join(str(value).split()).strip() for value in values]
            merged[str(objective)] = [value for value in normalized if value][:100]
        return cls(
            terms_by_objective={key: tuple(values) for key, values in merged.items()},
            negative_terms=_NEGATIVE_TERMS,
        )


@dataclass(frozen=True, slots=True)
class CrawlBudget:
    """Independent acquisition limits for one candidate frontier.

    ``max_pages`` is a deprecated compatibility alias. When supplied it tightens both fetch
    attempts and accepted artifacts, matching the pre-Batch-4 meaning without allowing it to
    loosen either new limit.
    """

    max_fetch_attempts: int = 12
    max_accepted_artifacts: int = _MAX_ROOT_PAGES
    max_depth: int = 2
    max_total_bytes: int = _DEFAULT_TOTAL_BYTES
    max_host_requests: int = 10
    max_wall_seconds: float = _DEFAULT_WALL_SECONDS
    max_browser_renders: int = 0
    max_document_conversions: int = 4
    max_links_per_page: int = 100
    per_host_interval_seconds: float = 0.0
    max_pages: int | None = None

    def __post_init__(self) -> None:
        if self.max_pages is not None:
            if not 1 <= self.max_pages <= _MAX_ROOT_PAGES:
                raise ValueError(f"max_pages must be between 1 and {_MAX_ROOT_PAGES}")
            object.__setattr__(
                self,
                "max_fetch_attempts",
                min(self.max_fetch_attempts, self.max_pages),
            )
            object.__setattr__(
                self,
                "max_accepted_artifacts",
                min(self.max_accepted_artifacts, self.max_pages),
            )
        if not 1 <= self.max_fetch_attempts <= _MAX_FETCH_ATTEMPTS:
            raise ValueError(f"max_fetch_attempts must be between 1 and {_MAX_FETCH_ATTEMPTS}")
        if not 1 <= self.max_accepted_artifacts <= _MAX_ACCEPTED_ARTIFACTS:
            raise ValueError(
                f"max_accepted_artifacts must be between 1 and {_MAX_ACCEPTED_ARTIFACTS}"
            )
        if not 0 <= self.max_depth <= 3:
            raise ValueError("max_depth must be between 0 and 3")
        if self.max_total_bytes < 1:
            raise ValueError("max_total_bytes must be positive")
        if self.max_host_requests < 1:
            raise ValueError("max_host_requests must be positive")
        if self.max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be positive")
        if self.max_browser_renders < 0:
            raise ValueError("max_browser_renders cannot be negative")
        if self.max_document_conversions < 0:
            raise ValueError("max_document_conversions cannot be negative")
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
    sufficiency: StaticPageSufficiency = StaticPageSufficiency.FULL_CONTENT


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
class AcquisitionEscalation:
    url: str
    depth: int
    kind: AcquisitionEscalationKind
    reason: str
    capability_enabled: bool


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
    accepted_artifacts: int = 0
    near_duplicate_content_urls: tuple[str, ...] = ()
    host_requests: tuple[tuple[str, int], ...] = ()
    elapsed_seconds: float = 0.0
    browser_renders: int = 0
    document_conversions: int = 0
    escalations: tuple[AcquisitionEscalation, ...] = ()
    budget_reasons: tuple[str, ...] = ()
    unresolved_frontier: tuple[str, ...] = ()


@dataclass(order=True, slots=True)
class _QueuedLink:
    sort_score: int
    insertion_order: int
    url: str = field(compare=False)
    depth: int = field(compare=False)
    score: int = field(compare=False)
    is_seed: bool = field(compare=False, default=False)


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


def score_crawl_link(
    link: FetchedLink,
    *,
    frontier_needs: Iterable[AcquisitionFrontierNeed] = (),
    lexicon: AcquisitionLexicon | None = None,
) -> int:
    """Rank links with unresolved coverage, multilingual text, and structural context."""

    active_lexicon = lexicon or AcquisitionLexicon.defaults()
    relation = _link_relation(link)
    hreflang = str(getattr(link, "hreflang", "") or "")
    context = " ".join(str(item) for item in getattr(link, "context_tags", ()) or ())
    combined = " ".join(
        part
        for part in (
            link.url,
            link.text,
            link.title or "",
            relation,
            hreflang,
            context,
        )
        if part
    ).casefold()
    score = 20
    score += _structural_link_score(link)

    needs = tuple(frontier_needs)
    objectives = tuple(dict.fromkeys(need.objective for need in needs))
    if not objectives:
        objectives = tuple(active_lexicon.terms_by_objective)
    for objective in objectives:
        terms = active_lexicon.terms_by_objective.get(objective, ())
        matches = sum(1 for term in terms if term.casefold() in combined)
        score += min(matches, 3) * 12

    for need in needs:
        for keyword in need.keywords:
            if keyword.casefold() in combined:
                score += 18
        for reason in need.reasons:
            reason_terms = [item for item in re.split(r"[^\w]+", reason.casefold()) if len(item) >= 4]
            if any(term in combined for term in reason_terms[:6]):
                score += 5

    if any(term.casefold() in combined for term in active_lexicon.negative_terms):
        score -= 25
    return score


def classify_static_page(fetched: FetchedSource) -> StaticPageSufficiency:
    """Classify whether static acquisition is usable before any browser escalation."""

    text = " ".join(
        part for part in (fetched.normalized_text, fetched.excerpt_text) if part
    ).casefold()
    url = fetched.final_url.casefold()
    content_type = fetched.content_type.casefold()
    if any(marker in text or marker in url for marker in _CHALLENGE_MARKERS):
        return StaticPageSufficiency.CHALLENGE
    if content_type not in {
        "application/pdf",
        "application/xhtml+xml",
        "text/html",
        "text/plain",
        "text/csv",
    }:
        return StaticPageSufficiency.UNSUPPORTED
    compact = " ".join(text.split())
    if content_type in {"text/html", "application/xhtml+xml"} and (
        any(marker in compact for marker in _JAVASCRIPT_SHELL_MARKERS)
        or (len(compact) < 300 and len(fetched.links) >= 3)
    ):
        return StaticPageSufficiency.JAVASCRIPT_SHELL
    if len(compact) >= 1_200:
        return StaticPageSufficiency.FULL_CONTENT
    if len(compact) >= 80:
        return StaticPageSufficiency.PARTIAL_CONTENT
    return StaticPageSufficiency.UNSUPPORTED


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
    """Reuse SafeSourceFetcher while tightening only the current page byte allowance."""

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
    """Explore a ranked, authority-bounded frontier using one safe fetch boundary."""

    def __init__(
        self,
        *,
        fetcher: SourceFetcher,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.fetcher = fetcher
        self.sleeper = sleeper
        self.clock = clock

    def crawl(
        self,
        root_url: str,
        *,
        budget: CrawlBudget | None = None,
        allowed_hosts: set[str] | None = None,
        heartbeat: Callable[[], None] | None = None,
        frontier_needs: Iterable[AcquisitionFrontierNeed] = (),
        lexicon: AcquisitionLexicon | None = None,
        browser_enabled: bool = False,
        ocr_enabled: bool = False,
    ) -> CrawlResult:
        """Backward-compatible single-root wrapper around the shared frontier crawler."""

        normalized = normalize_crawl_url(root_url)
        if normalized is None:
            raise SourceFetchError("invalid_crawl_root")
        root_host = _host(normalized)
        assert root_host is not None
        seeds = [AcquisitionSeed(normalized, AcquisitionAuthority.PROGRAMME_OWNER)]
        for host in sorted(allowed_hosts or set()):
            normalized_host = host.casefold().strip(".")
            if normalized_host and normalized_host != root_host:
                seeds.append(
                    AcquisitionSeed(
                        f"https://{normalized_host}/",
                        AcquisitionAuthority.REVIEWED_AUXILIARY,
                    )
                )
        return self.crawl_many(
            seeds,
            budget=budget,
            heartbeat=heartbeat,
            frontier_needs=frontier_needs,
            lexicon=lexicon,
            browser_enabled=browser_enabled,
            ocr_enabled=ocr_enabled,
            primary_root=normalized,
            enqueue_auxiliary_roots=False,
        )

    def crawl_many(
        self,
        seeds: Iterable[AcquisitionSeed | str],
        *,
        budget: CrawlBudget | None = None,
        heartbeat: Callable[[], None] | None = None,
        frontier_needs: Iterable[AcquisitionFrontierNeed] = (),
        lexicon: AcquisitionLexicon | None = None,
        browser_enabled: bool = False,
        ocr_enabled: bool = False,
        primary_root: str | None = None,
        enqueue_auxiliary_roots: bool = True,
    ) -> CrawlResult:
        """Crawl multiple explicitly-authorized roots through one deduplicated frontier."""

        limits = budget or CrawlBudget()
        needs = tuple(frontier_needs)
        active_lexicon = lexicon or AcquisitionLexicon.defaults()
        normalized_seeds: list[AcquisitionSeed] = []
        authority_by_host: dict[str, AcquisitionAuthority] = {}
        for index, raw_seed in enumerate(seeds):
            seed = (
                raw_seed
                if isinstance(raw_seed, AcquisitionSeed)
                else AcquisitionSeed(
                    str(raw_seed),
                    AcquisitionAuthority.PROGRAMME_OWNER
                    if index == 0
                    else AcquisitionAuthority.REVIEWED_AUXILIARY,
                )
            )
            normalized_url = normalize_crawl_url(seed.url)
            if normalized_url is None:
                raise SourceFetchError("invalid_crawl_root")
            host = _host(normalized_url)
            assert host is not None
            authority_by_host[host] = seed.authority
            normalized_seeds.append(AcquisitionSeed(normalized_url, seed.authority))
        if not normalized_seeds:
            raise SourceFetchError("invalid_crawl_root")

        normalized_primary = normalize_crawl_url(primary_root or normalized_seeds[0].url)
        if normalized_primary is None:
            raise SourceFetchError("invalid_crawl_root")
        primary_host = _host(normalized_primary)
        if primary_host not in authority_by_host:
            raise SourceFetchError("crawl_root_host_not_verified")

        pages: list[CrawledPage] = []
        failures: list[CrawlFailure] = []
        rejected: list[RejectedCrawlLink] = []
        duplicates: list[str] = []
        near_duplicates: list[str] = []
        escalations: list[AcquisitionEscalation] = []
        unresolved: set[str] = {
            f"{need.objective}:{need.scope_type}:{need.scope_key}:{reason}"
            for need in needs
            for reason in need.reasons
        }
        budget_reasons: set[str] = set()
        seen_urls: set[str] = set()
        completed_urls: set[str] = set()
        seen_hashes: set[str] = set()
        signatures: list[tuple[str, frozenset[int], frozenset[str]]] = []
        queue: list[_QueuedLink] = []
        insertion_order = 0
        total_bytes = 0
        fetch_attempts = 0
        accepted_artifacts = 0
        browser_renders = 0
        document_conversions = 0
        host_requests: dict[str, int] = {}
        last_host_request: dict[str, float] = {}
        budget_exhausted = False
        started = self.clock()

        def pulse() -> None:
            if heartbeat is not None:
                heartbeat()

        def elapsed() -> float:
            return max(0.0, self.clock() - started)

        def mark_budget(reason: str) -> None:
            nonlocal budget_exhausted
            budget_exhausted = True
            budget_reasons.add(reason)
            unresolved.add(f"acquisition_budget:{reason}")

        def enqueue(
            url: str,
            *,
            depth: int,
            score: int,
            is_seed: bool = False,
        ) -> None:
            nonlocal insertion_order
            normalized = normalize_crawl_url(url)
            if normalized is None or normalized in seen_urls or normalized in completed_urls:
                return
            host = _host(normalized)
            if host not in authority_by_host:
                rejected.append(
                    RejectedCrawlLink(
                        url=normalized,
                        depth=depth,
                        reason="cross_domain_without_typed_authority",
                    )
                )
                return
            seen_urls.add(normalized)
            heapq.heappush(
                queue,
                _QueuedLink(
                    sort_score=-score,
                    insertion_order=insertion_order,
                    url=normalized,
                    depth=depth,
                    score=score,
                    is_seed=is_seed,
                ),
            )
            insertion_order += 1

        def enqueue_sitemap(seed_url: str) -> None:
            parsed = urlsplit(seed_url)
            sitemap = urlunsplit((parsed.scheme, parsed.netloc, "/sitemap.xml", "", ""))
            enqueue(sitemap, depth=1, score=95)

        def enqueue_links(links: tuple[FetchedLink, ...], *, depth: int) -> None:
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
                host = _host(normalized)
                if host not in authority_by_host:
                    rejected.append(
                        RejectedCrawlLink(
                            url=normalized,
                            depth=depth,
                            reason="cross_domain_without_typed_authority",
                        )
                    )
                    continue
                enqueue(
                    normalized,
                    depth=depth,
                    score=score_crawl_link(
                        link,
                        frontier_needs=needs,
                        lexicon=active_lexicon,
                    ),
                )

        def add_escalation(
            *,
            url: str,
            depth: int,
            kind: AcquisitionEscalationKind,
            reason: str,
        ) -> None:
            enabled = (
                browser_enabled
                if kind is AcquisitionEscalationKind.BROWSER_RENDER
                else ocr_enabled
                if kind is AcquisitionEscalationKind.OCR
                else True
            )
            item = AcquisitionEscalation(
                url=url,
                depth=depth,
                kind=kind,
                reason=reason,
                capability_enabled=enabled,
            )
            if item not in escalations:
                escalations.append(item)
            unresolved.add(
                f"acquisition_escalation:{kind.value}:{'enabled' if enabled else 'disabled'}:{reason}"
            )

        def fetch_page(item: _QueuedLink) -> bool:
            nonlocal total_bytes, fetch_attempts, accepted_artifacts, document_conversions
            pulse()
            if elapsed() >= limits.max_wall_seconds:
                mark_budget("wall_time")
                return False
            if fetch_attempts >= limits.max_fetch_attempts:
                mark_budget("fetch_attempts")
                return False
            if accepted_artifacts >= limits.max_accepted_artifacts:
                mark_budget("accepted_artifacts")
                return False
            if item.depth > limits.max_depth:
                return True

            current_host = _host(item.url)
            if current_host is None or current_host not in authority_by_host:
                rejected.append(
                    RejectedCrawlLink(
                        url=item.url,
                        depth=item.depth,
                        reason="host_not_authorized",
                    )
                )
                return True
            if host_requests.get(current_host, 0) >= limits.max_host_requests:
                mark_budget(f"host_requests:{current_host}")
                return False
            remaining_bytes = limits.max_total_bytes - total_bytes
            if remaining_bytes <= 0:
                mark_budget("bytes")
                return False
            if _looks_like_document(item.url) and document_conversions >= limits.max_document_conversions:
                mark_budget("document_conversions")
                return False

            previous_request = last_host_request.get(current_host)
            if previous_request is not None and limits.per_host_interval_seconds > 0:
                wait = limits.per_host_interval_seconds - (self.clock() - previous_request)
                if wait > 0:
                    if elapsed() + wait >= limits.max_wall_seconds:
                        mark_budget("wall_time")
                        return False
                    pulse()
                    self.sleeper(wait)
                    pulse()

            fetch_attempts += 1
            host_requests[current_host] = host_requests.get(current_host, 0) + 1
            last_host_request[current_host] = self.clock()
            pulse()
            try:
                fetched = _fetch_with_limit(self.fetcher, item.url, max_bytes=remaining_bytes)
            except SourceFetchError as exc:
                pulse()
                failure_code = _failure_code(exc)
                failures.append(CrawlFailure(url=item.url, depth=item.depth, reason=failure_code))
                escalation = _escalation_for_failure(item.url, str(exc))
                if escalation is not None:
                    add_escalation(
                        url=item.url,
                        depth=item.depth,
                        kind=escalation,
                        reason=failure_code,
                    )
                if failure_code in {
                    "crawl_byte_budget_exceeded",
                    "crawler_fetcher_does_not_support_byte_budget",
                }:
                    mark_budget("bytes")
                    return False
                if item.is_seed and item.url == normalized_primary and escalation is None:
                    raise
                return True
            pulse()

            if fetched.bytes_read > remaining_bytes:
                failures.append(
                    CrawlFailure(
                        url=item.url,
                        depth=item.depth,
                        reason="crawler_fetcher_violated_byte_budget",
                    )
                )
                mark_budget("bytes")
                return False
            total_bytes += fetched.bytes_read

            final_url = normalize_crawl_url(fetched.final_url)
            if final_url is None:
                failures.append(
                    CrawlFailure(url=item.url, depth=item.depth, reason="redirected_to_invalid_url")
                )
                if item.is_seed and item.url == normalized_primary:
                    raise SourceFetchError("crawler_root_redirect_invalid")
                return True
            final_host = _host(final_url)
            if final_host not in authority_by_host:
                rejected.append(
                    RejectedCrawlLink(
                        url=final_url,
                        depth=item.depth,
                        reason="redirect_cross_domain_without_typed_authority",
                    )
                )
                if item.is_seed and item.url == normalized_primary:
                    raise SourceFetchError("crawler_root_redirect_left_verified_domain")
                return True

            completed_urls.add(item.url)
            completed_urls.add(final_url)
            seen_urls.add(final_url)
            sufficiency = classify_static_page(fetched)
            if sufficiency is StaticPageSufficiency.CHALLENGE:
                failures.append(
                    CrawlFailure(url=final_url, depth=item.depth, reason="challenge_or_captcha")
                )
                unresolved.add("acquisition_blocked:challenge_or_captcha")
                return True
            if sufficiency is StaticPageSufficiency.JAVASCRIPT_SHELL:
                add_escalation(
                    url=final_url,
                    depth=item.depth,
                    kind=AcquisitionEscalationKind.BROWSER_RENDER,
                    reason="static_javascript_shell",
                )
                return True
            if (
                fetched.content_type.casefold() == "application/pdf"
                and sufficiency is StaticPageSufficiency.PARTIAL_CONTENT
            ):
                add_escalation(
                    url=final_url,
                    depth=item.depth,
                    kind=AcquisitionEscalationKind.OCR,
                    reason="pdf_static_text_partial",
                )
            elif sufficiency is StaticPageSufficiency.UNSUPPORTED:
                failures.append(
                    CrawlFailure(url=final_url, depth=item.depth, reason="static_content_unsupported")
                )
                escalation = _escalation_for_failure(final_url, fetched.content_type)
                if escalation is not None:
                    add_escalation(
                        url=final_url,
                        depth=item.depth,
                        kind=escalation,
                        reason="static_content_unsupported",
                    )
                return True

            if _content_requires_document_conversion(fetched):
                document_conversions += 1
                if document_conversions > limits.max_document_conversions:
                    mark_budget("document_conversions")
                    return False

            content_hash = fetched.normalized_content_hash or fetched.content_hash
            if content_hash in seen_hashes:
                duplicates.append(final_url)
                if item.depth < limits.max_depth:
                    enqueue_links(fetched.links, depth=item.depth + 1)
                return True

            signature, numbers = _near_duplicate_signature(fetched)
            if any(
                _signature_similarity(signature, prior_signature) >= 0.97
                and numbers == prior_numbers
                for _prior_url, prior_signature, prior_numbers in signatures
            ):
                near_duplicates.append(final_url)
            signatures.append((final_url, signature, numbers))
            seen_hashes.add(content_hash)
            pages.append(
                CrawledPage(
                    url=final_url,
                    depth=item.depth,
                    score=item.score,
                    fetched=fetched,
                    sufficiency=sufficiency,
                )
            )
            accepted_artifacts += 1
            if item.depth < limits.max_depth:
                enqueue_links(fetched.links, depth=item.depth + 1)
            if accepted_artifacts >= limits.max_accepted_artifacts and queue:
                mark_budget("accepted_artifacts")
                return False
            if total_bytes >= limits.max_total_bytes and queue:
                mark_budget("bytes")
                return False
            return True

        roots_to_enqueue = normalized_seeds if enqueue_auxiliary_roots else normalized_seeds[:1]
        for index, seed in enumerate(roots_to_enqueue):
            enqueue(seed.url, depth=0, score=100 - index, is_seed=True)
            if limits.max_depth > 0:
                enqueue_sitemap(seed.url)

        while queue and not budget_exhausted:
            pulse()
            item = heapq.heappop(queue)
            if item.url in completed_urls:
                continue
            if not fetch_page(item):
                break

        if queue and not budget_exhausted:
            if fetch_attempts >= limits.max_fetch_attempts:
                mark_budget("fetch_attempts")
            elif accepted_artifacts >= limits.max_accepted_artifacts:
                mark_budget("accepted_artifacts")
            elif elapsed() >= limits.max_wall_seconds:
                mark_budget("wall_time")
        pulse()

        return CrawlResult(
            root_url=normalized_primary,
            pages=tuple(pages),
            failures=tuple(failures),
            rejected=tuple(rejected),
            duplicate_content_urls=tuple(duplicates),
            total_bytes=total_bytes,
            fetch_attempts=fetch_attempts,
            budget_exhausted=budget_exhausted,
            accepted_artifacts=accepted_artifacts,
            near_duplicate_content_urls=tuple(near_duplicates),
            host_requests=tuple(sorted(host_requests.items())),
            elapsed_seconds=elapsed(),
            browser_renders=browser_renders,
            document_conversions=document_conversions,
            escalations=tuple(escalations),
            budget_reasons=tuple(sorted(budget_reasons)),
            unresolved_frontier=tuple(sorted(unresolved)),
        )


def _link_relation(link: FetchedLink) -> str:
    relation = getattr(link, "relation", ())
    if isinstance(relation, str):
        return relation.casefold()
    if isinstance(relation, (tuple, list, set)):
        return " ".join(str(item).casefold() for item in relation)
    return ""


def _structural_link_score(link: FetchedLink) -> int:
    parsed = urlsplit(link.url)
    path = parsed.path.casefold()
    relation = _link_relation(link)
    context = {str(item).casefold() for item in getattr(link, "context_tags", ()) or ()}
    score = 0
    if "next" in relation:
        score += 30
    if "alternate" in relation or getattr(link, "hreflang", None):
        score += 18
    if "canonical" in relation:
        score += 5
    if "table" in context:
        score += 12
    if path.endswith("/sitemap.xml") or path.endswith("sitemap.xml"):
        score += 35
    if _looks_like_document(link.url):
        score += 20
    if any(term in path for term in ("download", "document", "resource", "form", "guide", "handbook")):
        score += 18
    query_keys = {key.casefold() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & {"page", "p", "offset", "start", "cursor"}:
        score += 18
    if re.search(r"/(?:page|p)/\d+/?$", path):
        score += 18
    return score


def _looks_like_document(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return any(path.endswith(extension) for extension in _DOCUMENT_EXTENSIONS)


def _looks_like_image(url: str) -> bool:
    path = urlsplit(url).path.casefold()
    return any(path.endswith(extension) for extension in _IMAGE_EXTENSIONS)


def _content_requires_document_conversion(fetched: FetchedSource) -> bool:
    return fetched.content_type.casefold() in {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
    }


def _escalation_for_failure(
    url: str,
    message: str,
) -> AcquisitionEscalationKind | None:
    lowered = message.casefold()
    if "captcha" in lowered or "authentication" in lowered or "access_denied" in lowered:
        return None
    if _looks_like_image(url) or "image/" in lowered:
        return AcquisitionEscalationKind.OCR
    if urlsplit(url).path.casefold().endswith(".pdf") and (
        "no_extractable_evidence" in lowered
        or "source_requires_ocr" in lowered
        or "application/pdf" in lowered
    ):
        return AcquisitionEscalationKind.OCR
    if any(
        urlsplit(url).path.casefold().endswith(extension)
        for extension in (".doc", ".docx", ".xls", ".xlsx", ".csv")
    ) or any(
        marker in lowered
        for marker in (
            "wordprocessingml",
            "spreadsheetml",
            "text/csv",
            "document_conversion",
        )
    ):
        return AcquisitionEscalationKind.DOCUMENT_CONVERSION
    if "no_extractable_evidence" in lowered or "javascript" in lowered:
        return AcquisitionEscalationKind.BROWSER_RENDER
    return None


def _near_duplicate_signature(
    fetched: FetchedSource,
) -> tuple[frozenset[int], frozenset[str]]:
    text = fetched.normalized_text or fetched.excerpt_text or ""
    tokens = re.findall(r"[\w\-]{2,}", text.casefold(), flags=re.UNICODE)
    numbers = frozenset(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))
    if len(tokens) < 5:
        stable_tokens = {
            int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            for token in tokens
        }
        return frozenset(stable_tokens), numbers
    shingles = {
        int.from_bytes(
            hashlib.blake2b(" ".join(tokens[index : index + 5]).encode(), digest_size=8).digest(),
            "big",
        )
        for index in range(min(len(tokens) - 4, 1_500))
    }
    if len(shingles) > 512:
        shingles = set(sorted(shingles)[:512])
    return frozenset(shingles), numbers


def _signature_similarity(left: frozenset[int], right: frozenset[int]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


__all__ = [
    "AcquisitionAuthority",
    "AcquisitionEscalation",
    "AcquisitionEscalationKind",
    "AcquisitionLexicon",
    "AcquisitionSeed",
    "BoundedOfficialSiteCrawler",
    "CrawlBudget",
    "CrawlFailure",
    "CrawlResult",
    "CrawledPage",
    "RejectedCrawlLink",
    "StaticPageSufficiency",
    "classify_static_page",
    "normalize_crawl_url",
    "score_crawl_link",
]
