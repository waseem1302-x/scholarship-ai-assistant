"""Unit tests for the EvidenceAcquirer boundary (Phase 1a)."""

from __future__ import annotations

import pytest

from app.modules.catalogue_ingestion.evidence_acquirer import (
    EVIDENCE_ACQUIRER_CONTRACT_VERSION,
    AcquiredArtifact,
    AcquisitionRequest,
    AcquisitionTier,
    AcquisitionTiers,
    LegacySafeEvidenceAcquirer,
    SourceRoleHint,
    default_evidence_acquirer,
)
from app.modules.opportunities.source_monitor import (
    FetchedLink,
    FetchedSource,
    SourceFetchError,
)


class _FakeFetcher:
    def __init__(self, result: FetchedSource | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _sample_fetched(*, url: str = "https://example.gov/scholarship") -> FetchedSource:
    return FetchedSource(
        url=url,
        final_url=url,
        content_hash="abc123",
        excerpt_text="Eligibility requires citizenship.",
        section_label="Eligibility",
        bytes_read=1200,
        normalized_text="Eligibility requires citizenship. Funding covers tuition.",
        normalized_content_hash="def456",
        content_type="text/html",
        links=(FetchedLink(url=f"{url}/apply", text="Apply", title="Apply now"),),
    )


def test_legacy_acquirer_returns_static_http_artifact() -> None:
    fetched = _sample_fetched()
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=fetched))
    result = acquirer.acquire(AcquisitionRequest(url=fetched.url, role_hint=SourceRoleHint.PRIMARY))

    assert result.fetched is fetched
    artifact = result.artifact
    assert isinstance(artifact, AcquiredArtifact)
    assert artifact.requested_url == fetched.url
    assert artifact.final_url == fetched.final_url
    assert artifact.content_hash == "abc123"
    assert artifact.normalized_content_hash == "def456"
    assert artifact.normalized_text == fetched.normalized_text
    assert artifact.bytes_read == 1200
    assert artifact.tier is AcquisitionTier.STATIC_HTTP
    assert artifact.tier is AcquisitionTiers.STATIC_HTTP
    assert artifact.role_hint is SourceRoleHint.PRIMARY
    assert artifact.acquirer_contract_version == EVIDENCE_ACQUIRER_CONTRACT_VERSION
    assert artifact.links == fetched.links
    assert artifact.retrieved_at.tzinfo is not None


def test_legacy_acquirer_rejects_browser_flag() -> None:
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=_sample_fetched()))
    with pytest.raises(SourceFetchError, match="browser_acquisition_not_enabled"):
        acquirer.acquire(
            AcquisitionRequest(
                url="https://example.gov/scholarship",
                allow_browser=True,
            )
        )


def test_legacy_acquirer_rejects_document_and_ocr_flags() -> None:
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=_sample_fetched()))
    with pytest.raises(SourceFetchError, match="document_parser_not_enabled"):
        acquirer.acquire(
            AcquisitionRequest(
                url="https://example.gov/doc.pdf",
                allow_document_parser=True,
            )
        )
    with pytest.raises(SourceFetchError, match="ocr_not_enabled"):
        acquirer.acquire(
            AcquisitionRequest(
                url="https://example.gov/scan.pdf",
                allow_ocr=True,
            )
        )


def test_legacy_acquirer_propagates_fetch_errors() -> None:
    acquirer = LegacySafeEvidenceAcquirer(
        fetcher=_FakeFetcher(error=SourceFetchError("robots_disallowed"))
    )
    with pytest.raises(SourceFetchError, match="robots_disallowed"):
        acquirer.acquire(AcquisitionRequest(url="https://example.gov/blocked"))


def test_legacy_acquirer_enforces_max_bytes_on_plain_fetcher() -> None:
    large = _sample_fetched()
    large = FetchedSource(
        url=large.url,
        final_url=large.final_url,
        content_hash=large.content_hash,
        excerpt_text=large.excerpt_text,
        section_label=large.section_label,
        bytes_read=50_000,
        normalized_text=large.normalized_text,
        normalized_content_hash=large.normalized_content_hash,
        content_type=large.content_type,
        links=large.links,
    )
    acquirer = LegacySafeEvidenceAcquirer(fetcher=_FakeFetcher(result=large))
    with pytest.raises(SourceFetchError, match="source_too_large"):
        acquirer.acquire(AcquisitionRequest(url=large.url, max_bytes=10_000))


def test_acquisition_request_rejects_empty_url() -> None:
    with pytest.raises(ValueError, match="url is required"):
        AcquisitionRequest(url="")


def test_acquisition_request_rejects_non_positive_max_bytes() -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        AcquisitionRequest(url="https://example.gov/x", max_bytes=0)


def test_default_factory_returns_legacy_acquirer() -> None:
    acquirer = default_evidence_acquirer()
    assert isinstance(acquirer, LegacySafeEvidenceAcquirer)


def test_tier_alias_is_identical() -> None:
    assert AcquisitionTiers is AcquisitionTier


def test_universal_keyword_masking_preserves_global_scholarships() -> None:
    """Verify long DAAD, Chevening, and Fulbright documents are not blanked out."""
    from app.modules.catalogue_ingestion.claim_provider import _objective_source_text
    from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective

    long_text = (
        "Chevening Scholarships are the UK government global scholarship programme. "
        "Eligibility criteria require minimum 3.3 GPA and leadership experience. "
        "Funding benefits include full tuition fees and monthly stipend of GBP 1,400. "
        "Application deadline for submission is November 5, 2027. "
    ) + ("Standard university general filler text. " * 300)

    assert len(long_text) > 6000

    identity_masked = _objective_source_text(long_text, ClaimObjective.IDENTITY)
    assert "Chevening" in identity_masked or "scholarship" in identity_masked.lower()

    eligibility_masked = _objective_source_text(long_text, ClaimObjective.ELIGIBILITY)
    assert "Eligibility" in eligibility_masked or "gpa" in eligibility_masked.lower()

    funding_masked = _objective_source_text(long_text, ClaimObjective.FUNDING)
    assert "stipend" in funding_masked.lower() or "tuition" in funding_masked.lower()

    timeline_masked = _objective_source_text(long_text, ClaimObjective.APPLICATION_TIMELINE)
    assert "deadline" in timeline_masked.lower() or "submission" in timeline_masked.lower()


def test_multi_charset_decoding() -> None:
    """Verify charset detection across Shift-JIS, GB2312, and Windows-1252."""
    from app.modules.catalogue_ingestion.acquisition_fetcher import convert_catalogue_payload

    # 1. Shift-JIS (Japanese)
    sjis_html = (
        '<html><head><meta charset="shift_jis"></head><body>東京大学 研究生 奨学金</body></html>'
    ).encode("shift_jis")
    res_sjis = convert_catalogue_payload(
        sjis_html, content_type="text/html", final_url="https://u-tokyo.ac.jp"
    )
    assert "東京大学" in res_sjis.text
    assert "奨学金" in res_sjis.text

    # 2. GB18030 (Chinese)
    gb_html = (
        '<html><head><meta charset="gb2312"></head><body>中国政府奖学金 申请指南</body></html>'
    ).encode("gb18030")
    res_gb = convert_catalogue_payload(
        gb_html, content_type="text/html", final_url="https://campuschina.org"
    )
    assert "中国政府奖学金" in res_gb.text

    # 3. Windows-1252 (French/European)
    win_html = (
        '<html><head><meta charset="windows-1252"></head><body>'
        "Bourse d\u2019Excellence Eiffel pour étudiants étrangers</body></html>"
    ).encode("windows-1252")
    res_win = convert_catalogue_payload(
        win_html, content_type="text/html", final_url="https://campusfrance.org"
    )
    assert "Eiffel" in res_win.text


def test_unicode_and_whitespace_invariant_evidence_span_matching() -> None:
    """Verify smart-quote, non-breaking-space, and whitespace span matching."""
    from decimal import Decimal

    from app.modules.catalogue_ingestion.claim_provider import _bind_unique_evidence_span
    from app.modules.catalogue_ingestion.claim_resolution import _valid_evidence_span
    from app.modules.catalogue_ingestion.claim_schemas import (
        ClaimEntityType,
        ClaimScope,
        ClaimValue,
        ExtractedClaim,
    )

    source_text = "Applicants must receive a monthly living stipend of $1,200 USD."

    claim1 = ExtractedClaim(
        entity_type=ClaimEntityType.FUNDING,
        entity_key="stipend_1",
        field_path="amount",
        scope=ClaimScope(),
        value=ClaimValue(
            string_value=None,
            decimal_value=Decimal("1200"),
            integer_value=None,
            boolean_value=None,
            string_list_value=None,
        ),
        excerpt="monthly living stipend of $1,200 USD",
        excerpt_start=source_text.find("monthly living stipend of $1,200 USD"),
        excerpt_end=source_text.find("monthly living stipend of $1,200 USD")
        + len("monthly living stipend of $1,200 USD"),
        basis="explicit",
    )
    assert _valid_evidence_span(source_text, claim1) is True

    claim2 = claim1.model_copy(update={"excerpt": "monthly\u00a0living stipend of $1,200 USD"})
    assert _valid_evidence_span(source_text, claim2) is True

    claim3 = claim1.model_copy(update={"excerpt_start": 0, "excerpt_end": 10})
    bound = _bind_unique_evidence_span(claim3, source_text)
    assert bound.excerpt_start == source_text.find("monthly living stipend of $1,200 USD")
    assert bound.excerpt_end == bound.excerpt_start + len("monthly living stipend of $1,200 USD")


def test_flexible_datetime_parsing() -> None:
    """Verify that multiple non-standard dates and timezones are parsed accurately to UTC."""
    from datetime import UTC, datetime

    from app.modules.catalogue_ingestion.normalization_utils import (
        parse_flexible_datetime,
        resolve_timezone_offset,
    )

    # 1. ISO format
    dt1 = parse_flexible_datetime("2027-11-05")
    assert dt1 == datetime(2027, 11, 5, 0, 0, tzinfo=UTC)

    # 2. Slashes & Dots
    dt2 = parse_flexible_datetime("2027/03/15")
    assert dt2 == datetime(2027, 3, 15, 0, 0, tzinfo=UTC)
    dt3 = parse_flexible_datetime("2027.12.31")
    assert dt3 == datetime(2027, 12, 31, 0, 0, tzinfo=UTC)

    # 3. European Day-Month-Year
    dt4 = parse_flexible_datetime("31-10-2027")
    assert dt4 == datetime(2027, 10, 31, 0, 0, tzinfo=UTC)

    # 4. Written month
    dt5 = parse_flexible_datetime("November 5, 2027")
    assert dt5 == datetime(2027, 11, 5, 0, 0, tzinfo=UTC)
    dt6 = parse_flexible_datetime("5 Nov 2027")
    assert dt6 == datetime(2027, 11, 5, 0, 0, tzinfo=UTC)

    # 5. Timezone resolution
    jst_tz = resolve_timezone_offset("JST")
    assert jst_tz is not None
    dt_jst = parse_flexible_datetime("2027-11-05T23:59:00", default_tz="JST")
    assert dt_jst is not None
    # 23:59 JST is 14:59 UTC
    assert dt_jst.hour == 14 and dt_jst.minute == 59


def test_currency_disambiguation() -> None:
    """Verify that ambiguous currency symbols are resolved according to destination country code."""
    from app.modules.catalogue_ingestion.normalization_utils import disambiguate_currency

    assert disambiguate_currency("$", "AU") == "AUD"
    assert disambiguate_currency("$", "SG") == "SGD"
    assert disambiguate_currency("$", "CA") == "CAD"
    assert disambiguate_currency("$", "US") == "USD"
    assert disambiguate_currency("£", "GB") == "GBP"
    assert disambiguate_currency("€", "FR") == "EUR"
    assert disambiguate_currency("¥", "JP") == "JPY"
    assert disambiguate_currency("元", "CN") == "CNY"


def test_crawler_subdomain_authority_inheritance() -> None:
    """Verify that official subdomains inherit crawl authority from parent root."""
    from app.modules.catalogue_ingestion.crawler import (
        BoundedOfficialSiteCrawler,
    )
    from app.modules.opportunities.source_monitor import FetchedLink, FetchedSource, SourceFetcher

    class MockFetcher(SourceFetcher):
        def fetch(self, url: str, **kwargs) -> FetchedSource:
            return self.fetch_with_limit(url, max_bytes=50_000)

        def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
            import hashlib

            url_hash = hashlib.sha256(url.encode()).hexdigest()
            return FetchedSource(
                url=url,
                final_url=url,
                content_hash=url_hash,
                excerpt_text=f"Scholarship page for {url}",
                section_label="",
                bytes_read=500,
                normalized_text=f"Scholarship details for {url}",
                normalized_content_hash=url_hash,
                content_type="text/html",
                links=(FetchedLink(url="https://apply.example.gov/guidelines", text="Guidelines"),),
            )

    crawler = BoundedOfficialSiteCrawler(fetcher=MockFetcher())
    result = crawler.crawl("https://example.gov/scholarships")
    # Subdomain apply.example.gov should be enqueued and crawled rather than rejected
    assert any("apply.example.gov" in page.url for page in result.pages)
