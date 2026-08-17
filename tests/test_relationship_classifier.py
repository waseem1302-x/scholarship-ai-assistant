from app.modules.catalogue_ingestion.classification import (
    CandidateRelationshipContext,
    ConfidenceBand,
    DeterministicRelationshipClassifier,
    normalize_identity_name,
)
from app.modules.opportunities.graph_models import RelationshipKind


def classify(**overrides: object):
    context = CandidateRelationshipContext(
        candidate_name="Chinese Government Scholarship",
        canonical_name="Chinese Government Scholarship",
        aliases=("CSC", "CGS"),
        candidate_provider_id="china-scholarship-council",
        canonical_provider_id="china-scholarship-council",
        candidate_application_url="https://studyinchina.csc.edu.cn/apply",
        canonical_application_urls=("https://studyinchina.csc.edu.cn/apply",),
        candidate_source_url="https://www.campuschina.org/content/details3_74776.html",
        canonical_source_urls=("https://www.campuschina.org/content/details3_74776.html",),
        source_is_official=True,
        parent_scheme_explicit=True,
        **overrides,
    )
    return DeterministicRelationshipClassifier().classify(context)


def test_name_normalization_handles_unicode_punctuation_and_generic_suffix() -> None:
    assert normalize_identity_name("  Chinese Government Scholarship — Programme  ") == (
        "chinese government"
    )


def test_exact_existing_source_and_name_is_duplicate_candidate() -> None:
    decision = classify()

    assert decision.relationship == RelationshipKind.DUPLICATE
    assert decision.confidence_band == ConfidenceBand.HIGH
    assert decision.reason_code == "exact_existing_source_and_name"
    assert decision.requires_human_review is True
    assert decision.proposes_independent_scholarship is False
    assert decision.auto_publish_allowed is False


def test_alias_provider_and_application_match_is_same_scholarship() -> None:
    decision = classify(
        candidate_name="CSC",
        candidate_source_url="https://www.campuschina.org/scholarships/csc-overview",
        canonical_source_urls=("https://www.campuschina.org/content/details3_74776.html",),
    )

    assert decision.relationship == RelationshipKind.SAME_SCHOLARSHIP
    assert decision.confidence_band == ConfidenceBand.HIGH
    assert decision.reason_code == "alias_provider_application_match"


def test_explicit_route_under_same_scheme_is_track_not_scholarship() -> None:
    decision = classify(
        candidate_name="Chinese Government Scholarship Type B",
        candidate_source_url="https://example.edu/csc/type-b",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        candidate_application_url="https://example.edu/apply/csc",
        explicit_relationship=RelationshipKind.SAME_SCHEME_TRACK,
    )

    assert decision.relationship == RelationshipKind.SAME_SCHEME_TRACK
    assert decision.proposes_independent_scholarship is False
    assert decision.auto_publish_allowed is False


def test_official_participating_university_signal_links_institution() -> None:
    decision = classify(
        candidate_name="Tsinghua University CSC",
        candidate_source_url="https://www.tsinghua.edu.cn/csc",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        candidate_application_url="https://www.tsinghua.edu.cn/csc/apply",
        explicit_relationship=RelationshipKind.PARTICIPATING_INSTITUTION,
    )

    assert decision.relationship == RelationshipKind.PARTICIPATING_INSTITUTION
    assert decision.proposes_independent_scholarship is False


def test_official_programme_signal_links_programme() -> None:
    decision = classify(
        candidate_name="MSc Computer Science under CSC",
        candidate_source_url="https://www.tsinghua.edu.cn/csc/programmes",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        candidate_application_url="https://www.tsinghua.edu.cn/csc/apply",
        explicit_relationship=RelationshipKind.ELIGIBLE_PROGRAMME,
    )

    assert decision.relationship == RelationshipKind.ELIGIBLE_PROGRAMME


def test_local_deadline_and_requirement_never_become_independent_scholarships() -> None:
    deadline = classify(
        candidate_name="Tsinghua CSC application deadline",
        candidate_source_url="https://www.tsinghua.edu.cn/csc/deadline",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        candidate_application_url="https://www.tsinghua.edu.cn/csc/apply",
        explicit_relationship=RelationshipKind.INSTITUTION_SPECIFIC_DEADLINE,
    )
    requirement = classify(
        candidate_name="Tsinghua CSC pre-admission requirement",
        candidate_source_url="https://www.tsinghua.edu.cn/csc/requirements",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        candidate_application_url="https://www.tsinghua.edu.cn/csc/apply",
        explicit_relationship=RelationshipKind.INSTITUTION_SPECIFIC_REQUIREMENT,
    )

    assert deadline.relationship == RelationshipKind.INSTITUTION_SPECIFIC_DEADLINE
    assert requirement.relationship == RelationshipKind.INSTITUTION_SPECIFIC_REQUIREMENT
    assert deadline.proposes_independent_scholarship is False
    assert requirement.proposes_independent_scholarship is False


def test_unofficial_explicit_link_signal_fails_closed() -> None:
    decision = classify(
        candidate_name="Blog list of CSC universities",
        candidate_source_url="https://scholarshipportal.example/csc-universities",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        source_is_official=False,
        explicit_relationship=RelationshipKind.PARTICIPATING_INSTITUTION,
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert decision.confidence_band == ConfidenceBand.UNRESOLVED
    assert decision.reason_code == "official_evidence_required"


def test_link_signal_without_explicit_parent_scheme_fails_closed() -> None:
    decision = classify(
        candidate_name="University scholarship deadline",
        candidate_source_url="https://www.example.edu/scholarship",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        candidate_application_url="https://www.example.edu/apply",
        parent_scheme_explicit=False,
        explicit_relationship=RelationshipKind.INSTITUTION_SPECIFIC_DEADLINE,
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert decision.reason_code == "parent_scheme_not_proven"


def test_name_variation_alone_never_creates_or_links_a_scholarship() -> None:
    decision = classify(
        candidate_name="Chinese Government Scholarship International Program",
        candidate_provider_id=None,
        canonical_provider_id="china-scholarship-council",
        candidate_application_url=None,
        candidate_source_url="https://example.edu/article",
        canonical_source_urls=("https://www.campuschina.org/csc",),
        source_is_official=False,
        parent_scheme_explicit=False,
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert decision.proposes_independent_scholarship is False
    assert decision.auto_publish_allowed is False
