import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.modules.opportunities.models import (
    DegreeLevel,
    Opportunity,
    OpportunityStatus,
    Provider,
    Source,
    SourceExcerpt,
    SourceType,
    VerificationRecord,
    VerificationStatus,
)
from app.modules.opportunities.source_monitor import (
    FetchedSource,
    SourceFetchError,
    SourceMonitor,
    extract_evidence_section,
    extract_excerpt,
    normalize_evidence_text,
    validate_monitor_url,
    validate_response_peer,
)

NOW = datetime(2026, 8, 12, tzinfo=UTC)


class FakeFetcher:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.urls.append(url)
        payload = self.payloads[url]
        return FetchedSource(
            url=url,
            final_url=url,
            content_hash=hashlib.sha256(payload).hexdigest(),
            excerpt_text=extract_excerpt(payload),
            section_label="Automated source monitor",
            bytes_read=len(payload),
        )


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def add_active_verified_source(
    db_session,
    *,
    url: str,
    content_hash: str | None,
    last_updated_at: datetime | None,
) -> Source:
    provider = Provider(name=f"Monitor Provider {url}")
    opportunity = Opportunity(
        provider=provider,
        name=f"Monitor Opportunity {url}",
        country="Malaysia",
        degree_level=DegreeLevel.MASTERS,
        application_deadline=NOW + timedelta(days=30),
        status=OpportunityStatus.ACTIVE,
    )
    source = Source(
        url=url,
        source_type=SourceType.OFFICIAL,
        title="Official source",
        relevant_excerpt="Official source contains scholarship evidence for monitoring.",
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
        last_verified_at=NOW,
        last_updated_at=last_updated_at,
        content_hash=content_hash,
    )
    opportunity.sources.append(source)
    db_session.add(opportunity)
    db_session.commit()
    return source


def test_source_monitor_demotes_changed_verified_source(db_session) -> None:
    source = add_active_verified_source(
        db_session,
        url="https://example.edu/changed",
        content_hash=_hash(b"old source content"),
        last_updated_at=NOW - timedelta(days=8),
    )
    fetcher = FakeFetcher(
        {
            "https://example.edu/changed": (
                b"<html><main>Official source now contains changed scholarship "
                b"deadline and eligibility text for review.</main></html>"
            )
        }
    )

    result = SourceMonitor(db_session, fetcher=fetcher).run(now=NOW, limit=10)
    db_session.refresh(source)

    assert result.candidates == 1
    assert result.checked == 1
    assert result.changed == 1
    assert result.failed == 0
    assert source.verification_status is VerificationStatus.NEEDS_REVIEW
    assert source.content_hash == fetcher.fetch("https://example.edu/changed").content_hash

    records = db_session.scalars(select(VerificationRecord)).all()
    assert len(records) == 1
    assert records[0].checked_by_user_id is None
    assert records[0].metadata_json["changed"] is True

    excerpts = db_session.scalars(select(SourceExcerpt)).all()
    assert len(excerpts) == 1
    assert excerpts[0].captured_by_user_id is None
    assert "changed scholarship deadline" in excerpts[0].text


def test_source_monitor_records_initial_hash_without_demoting_source(db_session) -> None:
    source = add_active_verified_source(
        db_session,
        url="https://example.edu/initial",
        content_hash=None,
        last_updated_at=None,
    )
    fetcher = FakeFetcher(
        {
            "https://example.edu/initial": (
                b"Official source content used to initialize monitoring hash."
            )
        }
    )

    result = SourceMonitor(db_session, fetcher=fetcher).run(now=NOW, limit=10)
    db_session.refresh(source)

    assert result.initialized_hashes == 1
    assert result.changed == 0
    assert source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
    assert source.content_hash == _hash(
        b"Official source content used to initialize monitoring hash."
    )


def test_source_monitor_dry_run_does_not_mutate_source(db_session) -> None:
    original_hash = _hash(b"old source content")
    source = add_active_verified_source(
        db_session,
        url="https://example.edu/dry-run",
        content_hash=original_hash,
        last_updated_at=NOW - timedelta(days=8),
    )
    fetcher = FakeFetcher({"https://example.edu/dry-run": b"changed source content"})

    result = SourceMonitor(db_session, fetcher=fetcher).run(now=NOW, dry_run=True, limit=10)
    db_session.refresh(source)

    assert result.changed == 1
    assert result.dry_run is True
    assert source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
    assert source.content_hash == original_hash
    assert db_session.scalars(select(VerificationRecord)).all() == []


def test_source_monitor_skips_sources_that_are_not_due(db_session) -> None:
    add_active_verified_source(
        db_session,
        url="https://example.edu/not-due",
        content_hash=_hash(b"stable content"),
        last_updated_at=NOW - timedelta(days=1),
    )
    fetcher = FakeFetcher({"https://example.edu/not-due": b"changed source content"})

    result = SourceMonitor(db_session, fetcher=fetcher).run(now=NOW, limit=10)

    assert result.candidates == 0
    assert fetcher.urls == []


def test_monitor_url_validation_blocks_unsafe_targets() -> None:
    for url in (
        "http://example.edu/source",
        "https://localhost/source",
        "https://127.0.0.1/source",
    ):
        try:
            validate_monitor_url(url)
        except SourceFetchError:
            continue
        raise AssertionError(f"Unsafe monitor URL was accepted: {url}")


def test_monitor_normalizes_dynamic_html_before_section_hashing() -> None:
    first = normalize_evidence_text(
        b"<html><script>analytics('abc123456789')</script>"
        b"<main><h2>Eligibility</h2><p>Applicants must be international students.</p>"
        b"<p>Rendered at 12:34:56</p></main></html>"
    )
    second = normalize_evidence_text(
        b"<html><script>analytics('def987654321')</script>"
        b"<main><h2>Eligibility</h2><p>Applicants must be international students.</p>"
        b"<p>Rendered at 23:45:01</p></main></html>"
    )
    first_section = extract_evidence_section(first)
    second_section = extract_evidence_section(second)

    assert first_section is not None
    assert second_section is not None
    assert first_section.label == "Eligibility"
    assert first_section.text == second_section.text


class PeerSocket:
    def __init__(self, address: str) -> None:
        self.address = address

    def getpeername(self) -> tuple[str, int]:
        return (self.address, 443)


class PeerResponse:
    def __init__(self, address: str) -> None:
        self.fp = type("Fp", (), {})()
        self.fp.raw = type("Raw", (), {})()
        self.fp.raw._sock = PeerSocket(address)


def test_response_peer_validation_rejects_private_addresses() -> None:
    validate_response_peer(PeerResponse("93.184.216.34"))

    try:
        validate_response_peer(PeerResponse("127.0.0.1"))
    except SourceFetchError:
        return
    raise AssertionError("Private response peer address was accepted")
