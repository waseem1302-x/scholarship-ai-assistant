import hashlib

import pytest

from app.modules.catalogue_ingestion.crawler import (
    BoundedOfficialSiteCrawler,
    CrawlBudget,
    normalize_crawl_url,
    score_crawl_link,
    score_crawl_link_for_root,
)
from app.modules.opportunities.source_monitor import FetchedLink, FetchedSource, SourceFetchError

ROOT = "https://example.edu/scholarships/csc"


def fetched_page(
    url: str,
    text: str,
    *,
    links: tuple[FetchedLink, ...] = (),
    content_hash: str | None = None,
    final_url: str | None = None,
) -> FetchedSource:
    normalized_hash = content_hash or hashlib.sha256(text.encode()).hexdigest()
    return FetchedSource(
        url=url,
        final_url=final_url or url,
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

    def _response(self, url: str) -> FetchedSource:
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    def fetch(self, url: str) -> FetchedSource:
        return self._response(url)

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        response = self._response(url)
        if response.bytes_read > max_bytes:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        return response


def test_crawl_url_normalization_removes_tracking_fragment_and_default_port() -> None:
    assert (
        normalize_crawl_url(
            "https://EXAMPLE.edu:443/scholarships/csc/?utm_source=test&b=2&a=1#deadline"
        )
        == "https://example.edu/scholarships/csc?a=1&b=2"
    )


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

    assert fetcher.calls == [ROOT, deadline, funding]
    assert [page.url for page in result.pages] == [ROOT, deadline, funding]
    assert news not in fetcher.calls
    assert result.budget_exhausted is False


def test_crawl_ranking_prioritizes_applicant_evidence_over_post_award_material() -> None:
    applicant_guidance = FetchedLink(
        url="https://example.edu/advice-for-applicants/",
        text="Advice for applicants",
    )
    application_form = FetchedLink(
        url="https://example.edu/downloads/masters-template-application-form.pdf",
        text="Template application form",
    )
    current_scholar_handbook = FetchedLink(
        url="https://example.edu/current-scholars/handbook-policies-forms/",
        text="Handbook, policies and forms",
    )
    award_holder_form = FetchedLink(
        url="https://example.edu/forms/stipend-advance-award-holders.pdf",
        text="Stipend advance form for award holders",
    )

    assert score_crawl_link(applicant_guidance) > score_crawl_link(current_scholar_handbook)
    assert score_crawl_link(application_form) > score_crawl_link(award_holder_form)


def test_crawl_ranking_prefers_pages_in_the_same_programme_namespace() -> None:
    root = "https://example.edu/scholarships/lao/CGSP/Pages/default.aspx"
    programme_page = FetchedLink(
        url="https://example.edu/scholarships/lao/CGSP/Pages/Program-Offered.aspx",
        text="Program Offered",
    )
    unrelated_track = FetchedLink(
        url="https://example.edu/services/universities/tts/Pages/default.aspx",
        text="Tenure Track Statutes",
    )

    assert score_crawl_link_for_root(root, programme_page) > score_crawl_link_for_root(
        root, unrelated_track
    )


def test_bounded_crawler_ignores_low_relevance_navigation_and_post_award_links() -> None:
    applicant_guidance = "https://example.edu/advice-for-applicants"
    faq = "https://example.edu/scholarship-frequently-asked-questions"
    current_scholars = "https://example.edu/current-scholars/handbook-policies-forms"
    award_holder_form = "https://example.edu/forms/code-of-conduct-for-award-holders.pdf"
    about = "https://example.edu/about-us"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(url=current_scholars, text="Handbook, policies and forms"),
                    FetchedLink(url=award_holder_form, text="Code of Conduct for Award Holders"),
                    FetchedLink(url=about, text="About us"),
                    FetchedLink(url=applicant_guidance, text="Advice for applicants"),
                    FetchedLink(url=faq, text="Frequently asked questions"),
                ),
            ),
            applicant_guidance: fetched_page(
                applicant_guidance,
                "Official application guidance and required documents.",
            ),
            faq: fetched_page(faq, "Scholarship applicant frequently asked questions."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=5, max_depth=1),
    )

    assert fetcher.calls == [ROOT, applicant_guidance, faq]
    assert {item.url for item in result.rejected if item.reason == "low_scholarship_relevance"} >= {
        current_scholars,
        award_holder_form,
        about,
    }


def test_bounded_crawler_prioritizes_microsite_rules_subjects_and_about_over_news() -> None:
    root = "https://programme.example/"
    rules = "https://programme.example/rules"
    subject = "https://programme.example/subject/46"
    about = "https://programme.example/about"
    news = "https://programme.example/news/registration-opens"
    fetcher = FakeFetcher(
        {
            root: fetched_page(
                root,
                "International scholarship programme overview.",
                links=(
                    FetchedLink(url=news, text="Scholarship registration news"),
                    FetchedLink(url=about, text="About"),
                    FetchedLink(url=subject, text="Computer and Data Science"),
                    FetchedLink(url=rules, text="Rules of participation"),
                ),
            ),
            rules: fetched_page(rules, "Official eligibility and application rules."),
            subject: fetched_page(subject, "Degree programmes in this subject area."),
            about: fetched_page(about, "Programme identity and scholarship benefits."),
            news: fetched_page(news, "A general news item."),
        }
    )

    BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        root,
        budget=CrawlBudget(max_pages=4, max_depth=1),
    )

    assert fetcher.calls == [root, rules, about, subject]
    assert news not in fetcher.calls


def test_bounded_crawler_covers_sibling_sections_before_nested_downloads() -> None:
    root = "https://programme.example/"
    first_subject = "https://programme.example/subject/biology"
    second_subject = "https://programme.example/subject/engineering"
    nested_pdf = "https://programme.example/download/program-guidelines.pdf"
    fetcher = FakeFetcher(
        {
            root: fetched_page(
                root,
                "International scholarship programme overview.",
                links=(
                    FetchedLink(url=first_subject, text="Biology"),
                    FetchedLink(url=second_subject, text="Engineering"),
                ),
            ),
            first_subject: fetched_page(
                first_subject,
                "Biology degree programmes.",
                links=(FetchedLink(url=nested_pdf, text="Program guidelines PDF download"),),
            ),
            second_subject: fetched_page(second_subject, "Engineering degree programmes."),
            nested_pdf: fetched_page(nested_pdf, "Detailed programme rules."),
        }
    )

    BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        root,
        budget=CrawlBudget(max_pages=3, max_depth=2),
    )

    assert fetcher.calls == [root, first_subject, second_subject]
    assert nested_pdf not in fetcher.calls


def test_crawl_ranking_prefers_degree_track_page_over_generic_programme_download() -> None:
    track = FetchedLink(
        url="https://programme.example/subject/data-science/ma",
        text="Master's and doctoral tracks",
    )
    programme_pdf = FetchedLink(
        url="https://programme.example/attachment/123/download",
        text="Program download PDF",
    )

    assert score_crawl_link(track) > score_crawl_link(programme_pdf)
    assert score_crawl_link(programme_pdf) < 25


def test_crawl_ranking_excludes_exam_preparation_material() -> None:
    sample_tasks = FetchedLink(
        url="https://programme.example/attachment/456/download",
        text="Second-round sample tasks PDF download",
    )

    assert score_crawl_link(sample_tasks) < 25


def test_bounded_crawler_selects_relevant_links_after_early_navigation_noise() -> None:
    eligibility = "https://example.edu/eligibility"
    links = tuple(
        [FetchedLink(url=f"https://example.edu/navigation/{index}", text=f"Navigation {index}")
         for index in range(110)]
        + [FetchedLink(url=eligibility, text="Scholarship eligibility requirements")]
    )
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(ROOT, "Scholarship overview.", links=links),
            eligibility: fetched_page(eligibility, "Official eligibility requirements."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=2, max_depth=1, max_links_per_page=10),
    )

    assert fetcher.calls == [ROOT, eligibility]
    assert [page.url for page in result.pages] == [ROOT, eligibility]


def test_bounded_crawler_rejects_sibling_scholarship_scheme() -> None:
    root = "https://example.edu/scholarships/commonwealth-masters-scholarships"
    own_details = f"{root}/how-to-apply"
    sibling = "https://example.edu/scholarships/commonwealth-shared-scholarships-applications"
    fetcher = FakeFetcher(
        {
            root: fetched_page(
                root,
                "Commonwealth Master's Scholarship overview.",
                links=(
                    FetchedLink(url=sibling, text="Commonwealth Shared Scholarships applications"),
                    FetchedLink(url=own_details, text="How to apply and required documents"),
                ),
            ),
            own_details: fetched_page(own_details, "Application process and required documents."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        root,
        budget=CrawlBudget(max_pages=5, max_depth=1),
    )

    assert fetcher.calls == [root, own_details]
    assert any(
        item.url == sibling and item.reason == "different_scholarship_scheme"
        for item in result.rejected
    )


def test_bounded_crawler_rejects_cross_domain_auth_and_session_links() -> None:
    eligibility = "https://example.edu/scholarships/csc/eligibility"
    login = "https://example.edu/login?next=/scholarships/csc"
    external = "https://unrelated.example/scholarships/csc"
    session = "https://example.edu/account/session/123"
    sharepoint_auth = (
        "https://example.edu/_layouts/15/Authenticate.aspx?Source=%2Fscholarships%2Fcsc"
    )
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Official scholarship overview.",
                links=(
                    FetchedLink(url=external, text="External scholarship copy"),
                    FetchedLink(url=login, text="Login to apply"),
                    FetchedLink(url=session, text="Application session"),
                    FetchedLink(url=sharepoint_auth, text="Sign in"),
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
    assert sharepoint_auth not in fetcher.calls


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


def test_bounded_crawler_deduplicates_title_only_page_variants() -> None:
    base = "https://programme.example/subject/data-science"
    explicit_bachelor = f"{base}/b"
    shared_body = "Degree programmes and curriculum evidence. " * 150
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(url=base, text="Data Science subject"),
                    FetchedLink(url=explicit_bachelor, text="Bachelor's track"),
                ),
            ),
            base: fetched_page(base, f"Data Science {shared_body}"),
            explicit_bachelor: fetched_page(
                explicit_bachelor,
                f"Bachelor's in Data Science {shared_body}",
            ),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=3, max_depth=1),
        allowed_hosts={"example.edu", "programme.example"},
    )

    assert fetcher.calls == [ROOT, explicit_bachelor, base]
    assert len(result.pages) == 2
    assert result.duplicate_content_urls == (base,)


def test_bounded_crawler_does_not_refetch_redirect_destination_already_queued() -> None:
    old_url = "https://example.edu/scholarships/csc/funding-old"
    canonical = "https://example.edu/scholarships/csc/funding"
    fetcher = FakeFetcher(
        {
            ROOT: fetched_page(
                ROOT,
                "Scholarship overview.",
                links=(
                    FetchedLink(
                        url=old_url,
                        text="Scholarship funding benefits and tuition",
                    ),
                    FetchedLink(url=canonical, text="Scholarship funding"),
                ),
            ),
            old_url: fetched_page(
                old_url,
                "Official funding details.",
                final_url=canonical,
            ),
            canonical: fetched_page(canonical, "Official funding details."),
        }
    )

    result = BoundedOfficialSiteCrawler(fetcher=fetcher).crawl(
        ROOT,
        budget=CrawlBudget(max_pages=10, max_depth=1),
    )

    assert fetcher.calls == [ROOT, old_url]
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


def test_bounded_crawler_requires_fetcher_that_can_enforce_remaining_bytes() -> None:
    class LegacyFetcher:
        def fetch(self, url: str) -> FetchedSource:
            return fetched_page(url, "Official scholarship overview.")

    with pytest.raises(
        SourceFetchError,
        match="crawler_fetcher_does_not_support_byte_budget",
    ):
        BoundedOfficialSiteCrawler(fetcher=LegacyFetcher()).crawl(
            ROOT,
            budget=CrawlBudget(max_pages=10, max_depth=1),
        )


def test_bounded_crawler_stops_before_accepting_page_over_remaining_byte_budget() -> None:
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
        budget=CrawlBudget(max_pages=10, max_depth=1, max_total_bytes=50),
    )

    assert fetcher.calls == [ROOT, second]
    assert result.budget_exhausted is True
    assert result.total_bytes == 40
    assert result.total_bytes <= 50
    assert result.failures[-1].url == second
    assert result.failures[-1].reason == "crawl_byte_budget_exceeded"
    assert first not in fetcher.calls
