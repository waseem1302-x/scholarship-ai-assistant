"""Scheduled source monitoring for official opportunity evidence."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.modules.opportunities.lifecycle import SOURCE_FRESHNESS_DAYS
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.schemas import (
    SourceCheckRequest,
    SourceExcerptCreate,
)
from app.modules.opportunities.service import OpportunityService

DEFAULT_CHECK_INTERVAL_DAYS = 7
DEFAULT_MONITOR_LIMIT = 20
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 10
USER_AGENT = "ScholarshipAI-SourceMonitor/0.1"
SECTION_KEYWORDS = {
    "Deadline": ("deadline", "closing date", "application closes", "apply by"),
    "Eligibility": ("eligib", "nationality", "citizen", "academic requirement", "gpa"),
    "Funding": ("funding", "tuition", "stipend", "allowance", "coverage", "benefit"),
    "Documents": ("document", "transcript", "recommendation", "passport", "cv"),
    "Application process": ("apply", "application portal", "application process", "submit"),
}


class SourceFetchError(Exception):
    """Raised when a source cannot be safely fetched for monitoring."""


@dataclass(frozen=True)
class FetchedSource:
    url: str
    final_url: str
    content_hash: str
    excerpt_text: str | None
    section_label: str | None
    bytes_read: int


@dataclass(frozen=True)
class SourceCrawlPolicy:
    host: str
    check_interval_days: int = DEFAULT_CHECK_INTERVAL_DAYS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES
    user_agent: str = USER_AGENT


@dataclass(frozen=True)
class EvidenceSection:
    label: str
    text: str


@dataclass(frozen=True)
class SourceMonitorFailure:
    source_id: str
    url: str
    error: str


@dataclass(frozen=True)
class SourceMonitorRunResult:
    candidates: int
    checked: int
    changed: int
    unchanged: int
    initialized_hashes: int
    failed: int
    dry_run: bool
    failures: list[SourceMonitorFailure] = field(default_factory=list)


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> FetchedSource: ...


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_monitor_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class SafeSourceFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        crawl_policies: dict[str, SourceCrawlPolicy] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.crawl_policies = crawl_policies or {}
        self.opener = urllib.request.build_opener(SafeRedirectHandler)

    def fetch(self, url: str) -> FetchedSource:
        validate_monitor_url(url)
        policy = self.policy_for(url)
        request = urllib.request.Request(url, headers={"User-Agent": policy.user_agent})
        try:
            with self.opener.open(request, timeout=policy.timeout_seconds) as response:
                final_url = response.geturl()
                validate_monitor_url(final_url)
                validate_response_peer(response)
                payload = response.read(policy.max_bytes + 1)
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise SourceFetchError(f"source_fetch_failed: {exc}") from exc

        if len(payload) > policy.max_bytes:
            raise SourceFetchError(f"source_too_large: exceeded {policy.max_bytes} bytes")

        evidence_text = normalize_evidence_text(payload)
        section = extract_evidence_section(evidence_text)
        hash_input = section.text if section else evidence_text
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        return FetchedSource(
            url=url,
            final_url=final_url,
            content_hash=content_hash,
            excerpt_text=(section.text[:500] if section else extract_excerpt(payload)),
            section_label=section.label if section else None,
            bytes_read=len(payload),
        )

    def policy_for(self, url: str) -> SourceCrawlPolicy:
        host = (urllib.parse.urlparse(url).hostname or "").casefold()
        return self.crawl_policies.get(
            host,
            SourceCrawlPolicy(
                host=host,
                timeout_seconds=self.timeout_seconds,
                max_bytes=self.max_bytes,
            ),
        )


class SourceMonitor:
    def __init__(self, session: Session, *, fetcher: SourceFetcher | None = None) -> None:
        self.session = session
        self.repository = OpportunityRepository(session)
        self.service = OpportunityService(session)
        self.fetcher = fetcher or SafeSourceFetcher()

    def run(
        self,
        *,
        dry_run: bool = False,
        limit: int = DEFAULT_MONITOR_LIMIT,
        check_interval_days: int = DEFAULT_CHECK_INTERVAL_DAYS,
        now: datetime | None = None,
    ) -> SourceMonitorRunResult:
        observed_at = now or datetime.now(UTC)
        sources = self.repository.list_sources_due_for_monitoring(
            now=observed_at,
            check_interval_days=check_interval_days,
            freshness_days=SOURCE_FRESHNESS_DAYS,
            limit=limit,
        )
        checked = changed = unchanged = initialized_hashes = 0
        failures: list[SourceMonitorFailure] = []

        for source in sources:
            previous_hash = source.content_hash
            try:
                fetched = self.fetcher.fetch(source.url)
            except SourceFetchError as exc:
                failures.append(
                    SourceMonitorFailure(
                        source_id=str(source.id),
                        url=source.url,
                        error=str(exc),
                    )
                )
                continue

            checked += 1
            has_changed = previous_hash is not None and fetched.content_hash != previous_hash
            if previous_hash is None:
                initialized_hashes += 1
            elif has_changed:
                changed += 1
            else:
                unchanged += 1

            if dry_run:
                continue

            self.service.record_source_check(
                source.id,
                SourceCheckRequest(
                    content_hash=fetched.content_hash,
                    observed_at=observed_at,
                    change_summary=_change_summary(
                        changed=has_changed,
                        previous_hash=previous_hash,
                        final_url=fetched.final_url,
                    ),
                    excerpt=_excerpt_payload(fetched) if has_changed else None,
                ),
                checked_by=None,
            )

        return SourceMonitorRunResult(
            candidates=len(sources),
            checked=checked,
            changed=changed,
            unchanged=unchanged,
            initialized_hashes=initialized_hashes,
            failed=len(failures),
            dry_run=dry_run,
            failures=failures,
        )


def validate_monitor_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise SourceFetchError("unsafe_source_url: only https URLs can be monitored")
    if not parsed.hostname:
        raise SourceFetchError("unsafe_source_url: host is required")
    if parsed.username or parsed.password:
        raise SourceFetchError("unsafe_source_url: credentials are not allowed")

    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise SourceFetchError("unsafe_source_url: localhost is not allowed")

    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SourceFetchError(f"unsafe_source_url: host could not be resolved ({host})") from exc

    for *_, sockaddr in addresses:
        address = ipaddress.ip_address(sockaddr[0])
        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise SourceFetchError("unsafe_source_url: private or reserved network target")


def validate_response_peer(response: object) -> None:
    peer = response_peer_address(response)
    if peer is None:
        raise SourceFetchError("unsafe_source_url: peer address could not be verified")
    address = ipaddress.ip_address(peer)
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise SourceFetchError("unsafe_source_url: private or reserved network peer")


def response_peer_address(response: object) -> str | None:
    current = response
    for attribute in ("fp", "raw", "_sock"):
        current = getattr(current, attribute, None)
        if current is None:
            return None
    getpeername = getattr(current, "getpeername", None)
    if getpeername is None:
        return None
    peer = getpeername()
    return peer[0] if peer else None


def normalize_evidence_text(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="ignore")
    text = re.sub(
        r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<(h[1-6]|p|li|dt|dd|section|article|div)\b[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", text)
    text = re.sub(r"\b[a-f0-9]{12,}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_evidence_section(text: str, *, max_chars: int = 500) -> EvidenceSection | None:
    if len(text) < 20:
        return None
    lowered = text.casefold()
    best_label = None
    best_position = len(text)
    for label, keywords in SECTION_KEYWORDS.items():
        positions = [lowered.find(keyword) for keyword in keywords if lowered.find(keyword) >= 0]
        if positions and min(positions) < best_position:
            best_label = label
            best_position = min(positions)
    if best_label is None:
        return EvidenceSection("General scholarship evidence", text[:max_chars])
    start = max(0, best_position - 120)
    return EvidenceSection(best_label, text[start : start + max_chars].strip())


def extract_excerpt(payload: bytes, *, max_chars: int = 500) -> str | None:
    text = normalize_evidence_text(payload)
    if len(text) < 20:
        return None
    return text[:max_chars]


def _excerpt_payload(fetched: FetchedSource) -> SourceExcerptCreate | None:
    if fetched.excerpt_text is None:
        return None
    return SourceExcerptCreate(
        section_label=fetched.section_label or "Automated source monitor",
        locator=fetched.final_url,
        text=fetched.excerpt_text,
        content_hash=fetched.content_hash,
    )


def _change_summary(*, changed: bool, previous_hash: str | None, final_url: str) -> str:
    if previous_hash is None:
        return f"Automated source monitor recorded initial content hash from {final_url}."
    if changed:
        return f"Automated source monitor detected changed content at {final_url}."
    return f"Automated source monitor found no content-hash change at {final_url}."
