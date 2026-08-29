from datetime import date

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.source_routing import (
    SOURCE_ROUTER_VERSION,
    SourceContentRole,
    SourceCycle,
    classify_source,
    routed_objectives,
)


def test_funding_page_routes_only_unresolved_funding() -> None:
    decision = classify_source(
        source_url="https://example.edu/scholarship/funding",
        source_text="The stipend and tuition financial support are listed here for 2027.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.classifier_version == SOURCE_ROUTER_VERSION
    assert decision.role is SourceContentRole.FUNDING
    assert decision.cycle is SourceCycle.UPCOMING
    assert routed_objectives(
        decision,
        unresolved={ClaimObjective.FUNDING, ClaimObjective.DOCUMENTS_COUNTS},
    ) == (ClaimObjective.FUNDING,)
    assert routed_objectives(decision) == (ClaimObjective.FUNDING,)


def test_document_checklist_never_routes_funding_or_programme_objectives() -> None:
    decision = classify_source(
        source_url="https://example.edu/checklist",
        source_text="Required documents: application form, transcript and certified translation.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.role is SourceContentRole.DOCUMENT_CHECKLIST
    assert ClaimObjective.FUNDING not in decision.applicable_objectives
    assert ClaimObjective.PROGRAMMES not in decision.applicable_objectives


def test_unknown_source_fails_closed_but_multi_topic_source_routes_all_supported_roles() -> None:
    unknown = classify_source(
        source_url="https://example.edu/page",
        source_text="Welcome to the official website.",
        observed_on=date(2026, 8, 24),
    )
    conflicting = classify_source(
        source_url="https://example.edu/page",
        source_text="Funding stipend and required documents checklist.",
        observed_on=date(2026, 8, 24),
    )

    assert unknown.role is SourceContentRole.UNKNOWN
    assert unknown.requires_manual_review is True
    assert routed_objectives(unknown, unresolved=set(ClaimObjective)) == ()
    assert conflicting.role is SourceContentRole.FUNDING
    assert conflicting.requires_manual_review is False
    assert conflicting.ambiguity_reason == "multiple_supported_content_roles"
    assert set(conflicting.applicable_objectives) == {
        ClaimObjective.FUNDING,
        ClaimObjective.DOCUMENTS_CORE,
        ClaimObjective.DOCUMENTS_REQUIREMENTS,
        ClaimObjective.DOCUMENTS_COUNTS,
        ClaimObjective.DOCUMENTS_FORMAT,
    }


def test_unambiguous_url_role_takes_precedence_over_multi_topic_body() -> None:
    decision = classify_source(
        source_url="https://example.edu/scholarship/apply",
        source_text="Use the official application route and apply online here.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.role is SourceContentRole.APPLICATION_PORTAL
    assert decision.requires_manual_review is False
    assert decision.applicable_objectives == (ClaimObjective.ROUTES,)


def test_authoritative_specialist_url_ignores_navigation_noise_and_cycle_dates() -> None:
    decision = classify_source(
        source_url=(
            "https://www.hec.gov.pk/english/scholarshipsgrants/lao/CGSP/"
            "Pages/Eligibility-Criteria.aspx"
        ),
        source_text=(
            "Eligibility criteria. A test score obtained after January 2024 is valid. "
            "Applicants intending to enrol in September 2026 apply for the 2026/2027 "
            "scholarship. Navigation: funding, required documents, how to apply, deadline."
        ),
        observed_on=date(2026, 8, 28),
    )

    assert decision.role is SourceContentRole.ELIGIBILITY
    assert decision.requires_manual_review is False
    assert decision.applicable_objectives == (
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.ELIGIBILITY_CONTEXT,
    )
    assert "authoritative_url_role:eligibility" in decision.deterministic_signals


def test_authoritative_specialist_urls_have_narrow_objectives() -> None:
    cases = {
        "Pages/Financial-Coverage.aspx": {ClaimObjective.FUNDING},
        "Pages/Program-Offered.aspx": {
            ClaimObjective.PROGRAMMES,
            ClaimObjective.PROGRAMME_DETAILS,
        },
        "Pages/Required-Documents.aspx": {
            ClaimObjective.DOCUMENTS_CORE,
            ClaimObjective.DOCUMENTS_REQUIREMENTS,
            ClaimObjective.DOCUMENTS_COUNTS,
            ClaimObjective.DOCUMENTS_FORMAT,
        },
    }

    for path, expected in cases.items():
        decision = classify_source(
            source_url=f"https://www.hec.gov.pk/{path}",
            source_text=(
                "Scholarship eligibility funding required documents application process "
                "programme deadline for 2026."
            ),
            observed_on=date(2026, 8, 28),
        )
        assert set(decision.applicable_objectives) == expected


def test_contact_page_is_not_routed_from_navigation_text() -> None:
    decision = classify_source(
        source_url="https://www.hec.gov.pk/scholarship/Pages/Contact-Us.aspx",
        source_text="Contact us. Navigation: eligibility, funding, required documents, apply.",
        observed_on=date(2026, 8, 28),
    )

    assert decision.role is SourceContentRole.UNKNOWN
    assert decision.requires_manual_review is True
    assert decision.applicable_objectives == ()


def test_public_notice_is_limited_to_eligibility_facts() -> None:
    decision = classify_source(
        source_url="https://www.hec.gov.pk/scholarship/Documents/Public-Notice.pdf",
        source_text=(
            "Eligibility notice with navigation links for programmes, funding and applications."
        ),
        observed_on=date(2026, 8, 28),
    )

    assert decision.role is SourceContentRole.ELIGIBILITY
    assert set(decision.applicable_objectives) == {
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.ELIGIBILITY_CONTEXT,
    }


def test_cycle_mixing_requires_manual_review() -> None:
    decision = classify_source(
        source_url="https://example.edu/guidelines",
        source_text="Required documents and application form for the 2025 and 2027 cycles.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.cycle is SourceCycle.AMBIGUOUS
    assert decision.requires_manual_review is True
    assert routed_objectives(decision, unresolved=set(ClaimObjective)) == ()


def test_current_application_year_and_next_intake_are_one_coherent_cycle() -> None:
    decision = classify_source(
        source_url="https://example.edu/2027-guidelines.pdf",
        source_text=(
            "Applications close in 2026 for the 2027 intake. Eligibility, funding, "
            "required documents and application process are provided."
        ),
        observed_on=date(2026, 8, 24),
    )

    assert decision.cycle is SourceCycle.UPCOMING
    assert decision.requires_manual_review is False
    assert {ClaimObjective.ELIGIBILITY, ClaimObjective.FUNDING} <= set(
        decision.applicable_objectives
    )


def test_birth_year_is_not_treated_as_a_historical_scholarship_cycle() -> None:
    decision = classify_source(
        source_url="https://example.edu/2027-guidelines.pdf",
        source_text=(
            "2027 scholarship application guidelines. Applicants must have been born "
            "on or after 2 April 1992."
        ),
        observed_on=date(2026, 8, 24),
    )

    assert decision.cycle is SourceCycle.UPCOMING
    assert decision.requires_manual_review is False


def test_degree_page_winner_language_and_bibliography_do_not_misroute() -> None:
    decision = classify_source(
        source_url="https://programme.example/subject/computer-science/ma",
        source_text=(
            "Master's and doctoral tracks. List of degree programs. "
            "The Open Doors winner should know the required subjects. "
            "Recommended reading: Example Author, 2010. Another textbook, 2019."
        ),
        observed_on=date(2026, 8, 28),
    )

    assert decision.role is SourceContentRole.PROGRAMME_DIRECTORY
    assert decision.cycle is SourceCycle.EVERGREEN
    assert decision.requires_manual_review is False
    assert set(decision.applicable_objectives) == {
        ClaimObjective.PROGRAMMES,
        ClaimObjective.PROGRAMME_DETAILS,
    }
    assert "authoritative_url_role:programme_directory" in decision.deterministic_signals


def test_publication_year_does_not_make_current_scholarship_page_ambiguous() -> None:
    decision = classify_source(
        source_url="https://example.edu/scholarships/commonwealth-masters-scholarships",
        source_text=(
            "Commonwealth Master's Scholarships by Alumni Team | Sep 15, 2020. "
            "Applications for the 2027/28 academic year open in September. "
            "Eligibility, funding, required documents, application process and deadline "
            "are provided on this page."
        ),
        observed_on=date(2026, 8, 24),
    )

    assert decision.cycle is SourceCycle.UPCOMING
    assert decision.requires_manual_review is False
    assert set(decision.applicable_objectives) == set(ClaimObjective)


def test_degree_label_in_url_does_not_hide_comprehensive_body_objectives() -> None:
    decision = classify_source(
        source_url="https://example.edu/scholarships/masters-scholarship",
        source_text=(
            "Master's scholarship overview. Eligibility, funding, required documents, "
            "application process and deadline for the 2027 intake."
        ),
        observed_on=date(2026, 8, 24),
    )

    assert decision.role is SourceContentRole.CURRENT_CYCLE_GUIDELINE
    assert decision.requires_manual_review is False
    assert set(decision.applicable_objectives) == set(ClaimObjective)


def test_evergreen_deadline_source_requires_cycle_resolution() -> None:
    decision = classify_source(
        source_url="https://example.edu/application-deadline",
        source_text="The application deadline is published on this page.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.role is SourceContentRole.DEADLINE_TIMELINE
    assert decision.cycle is SourceCycle.EVERGREEN
    assert decision.requires_manual_review is True
    assert decision.ambiguity_reason == "deadline_cycle_unresolved"
    assert routed_objectives(decision, unresolved=set(ClaimObjective)) == ()
