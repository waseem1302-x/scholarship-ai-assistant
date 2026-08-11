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
from app.modules.opportunities.schemas import SourceCheckRequest, SourceExcerptCreate
from app.modules.opportunities.service import OpportunityService

DEFAULT_CHECK_INTERVAL_DAYS = 7
DEFAULT_MONITOR_LIMIT = 20
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 10
USER_AGENT = "ScholarshipAI-SourceMonitor/0.1"


class SourceFetchError(Exception):
    """Raised when a source cannot be safely fetched for monitoring."""


@dataclass(frozen=True)
class FetchedSource:
    url: str
    final_url: str
    content_hash: str
    excerpt_text: str | None
    bytes_read: int


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
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.opener = urllib.request.build_opener(SafeRedirectHandler)

    def fetch(self, url: str) -> FetchedSource:
        validate_monitor_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                validate_monitor_url(final_url)
                payload = response.read(self.max_bytes + 1)
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise SourceFetchError(f"source_fetch_failed: {exc}") from exc

        if len(payload) > self.max_bytes:
            raise SourceFetchError(f"source_too_large: exceeded {self.max_bytes} bytes")

        content_hash = hashlib.sha256(payload).hexdigest()
        return FetchedSource(
            url=url,
            final_url=final_url,
            content_hash=content_hash,
            excerpt_text=extract_excerpt(payload),
            bytes_read=len(payload),
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


def extract_excerpt(payload: bytes, *, max_chars: int = 500) -> str | None:
    text = payload.decode("utf-8", errors="ignore")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 20:
        return None
    return text[:max_chars]


def _excerpt_payload(fetched: FetchedSource) -> SourceExcerptCreate | None:
    if fetched.excerpt_text is None:
        return None
    return SourceExcerptCreate(
        section_label="Automated source monitor",
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
