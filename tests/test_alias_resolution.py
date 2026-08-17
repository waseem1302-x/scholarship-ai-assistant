from app.modules.catalogue_ingestion.classification import (
    CandidateRelationshipContext,
    DeterministicRelationshipClassifier,
    normalize_identity_name,
    normalize_url,
)
from app.modules.opportunities.graph_models import RelationshipKind


def test_registered_alias_can_resolve_same_scholarship_with_identity_evidence() -> None:
    decision = DeterministicRelationshipClassifier().classify(
        CandidateRelationshipContext(
            candidate_name="CGS",
            canonical_name="Chinese Government Scholarship",
            aliases=("CSC", "CGS"),
            candidate_provider_id="csc",
            canonical_provider_id="csc",
            candidate_application_url="https://studyinchina.csc.edu.cn/apply",
            canonical_application_urls=("https://studyinchina.csc.edu.cn/apply",),
            candidate_source_url="https://www.campuschina.org/cgs",
            canonical_source_urls=("https://www.campuschina.org/csc",),
            source_is_official=True,
            parent_scheme_explicit=True,
        )
    )

    assert decision.relationship == RelationshipKind.SAME_SCHOLARSHIP


def test_unregistered_translation_is_not_fuzzy_identity_proof() -> None:
    decision = DeterministicRelationshipClassifier().classify(
        CandidateRelationshipContext(
            candidate_name="Beca del Gobierno Chino",
            canonical_name="Chinese Government Scholarship",
            aliases=("CSC", "CGS"),
            candidate_provider_id="csc",
            canonical_provider_id="csc",
            candidate_application_url="https://studyinchina.csc.edu.cn/apply-other",
            canonical_application_urls=("https://studyinchina.csc.edu.cn/apply",),
            candidate_source_url="https://www.campuschina.org/translated-page",
            canonical_source_urls=("https://www.campuschina.org/csc",),
            source_is_official=True,
            parent_scheme_explicit=False,
        )
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert decision.proposes_independent_scholarship is False


def test_case_punctuation_and_generic_suffix_normalize_deterministically() -> None:
    assert normalize_identity_name("Chinese-Government Scholarship Programme") == (
        "chinese government"
    )
    assert normalize_identity_name("  CHINESE government scholarship  ") == "chinese government"


def test_url_normalization_removes_tracking_but_preserves_meaningful_query() -> None:
    assert (
        normalize_url("HTTPS://Example.EDU:443/scholarships/csc/?cycle=2027&utm_source=news#apply")
        == "https://example.edu/scholarships/csc?cycle=2027"
    )


def test_malformed_port_and_credentialed_urls_fail_closed() -> None:
    assert normalize_url("https://example.edu:not-a-port/csc") is None
    assert normalize_url("https://user:secret@example.edu/csc") is None
