import json
from pathlib import Path

from app.modules.catalogue_ingestion.classification import (
    CandidateRelationshipContext,
    DeterministicRelationshipClassifier,
    IndependenceAssessment,
    IndependenceAuthorityType,
    decide_independence,
)
from app.modules.opportunities.evidence_models import EvidenceSupportType
from app.modules.opportunities.graph_models import RelationshipKind

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scholarship_graph"


def load_fixture(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert payload["fixture_type"] == "structural_regression"
    assert payload["publication_evidence"] is False
    return payload


def relationship(value: str) -> RelationshipKind:
    return RelationshipKind(value)


def test_csc_280_universities_never_inflate_scholarship_count() -> None:
    fixture = load_fixture("csc_280_universities.json")
    canonical = fixture["canonical_scholarship"]
    assert isinstance(canonical, dict)
    count = fixture["synthetic_participating_institution_count"]
    assert isinstance(count, int)

    classifier = DeterministicRelationshipClassifier()
    decisions = []
    for index in range(1, count + 1):
        decisions.append(
            classifier.classify(
                CandidateRelationshipContext(
                    candidate_name=str(fixture["candidate_name_template"]).format(index=index),
                    canonical_name=str(canonical["name"]),
                    aliases=tuple(canonical["aliases"]),
                    candidate_provider_id=str(canonical["provider_id"]),
                    canonical_provider_id=str(canonical["provider_id"]),
                    candidate_application_url=f"https://synthetic-university-{index}.example/csc/apply",
                    canonical_application_urls=(str(canonical["application_url"]),),
                    candidate_source_url=f"https://synthetic-university-{index}.example/csc",
                    canonical_source_urls=(str(canonical["source_url"]),),
                    source_is_official=True,
                    parent_scheme_explicit=True,
                    explicit_relationship=relationship(str(fixture["expected_relationship"])),
                )
            )
        )

    assert len(decisions) == 280
    assert all(
        decision.relationship == RelationshipKind.PARTICIPATING_INSTITUTION
        for decision in decisions
    )
    assert all(decision.proposes_independent_scholarship is False for decision in decisions)
    assert fixture["expected_canonical_scholarship_count"] == 1
    assert fixture["expected_independent_scholarship_count"] == 0


def test_mext_routes_remain_tracks_under_one_canonical_scholarship() -> None:
    fixture = load_fixture("mext_routes.json")
    canonical = fixture["canonical_scholarship"]
    routes = fixture["routes"]
    assert isinstance(canonical, dict)
    assert isinstance(routes, list)

    classifier = DeterministicRelationshipClassifier()
    for index, route in enumerate(routes, start=1):
        assert isinstance(route, dict)
        decision = classifier.classify(
            CandidateRelationshipContext(
                candidate_name=str(route["name"]),
                canonical_name=str(canonical["name"]),
                aliases=tuple(canonical["aliases"]),
                candidate_provider_id=str(canonical["provider_id"]),
                canonical_provider_id=str(canonical["provider_id"]),
                candidate_application_url=f"https://example.go.jp/mext/route-{index}",
                canonical_application_urls=(str(canonical["application_url"]),),
                candidate_source_url=f"https://example.go.jp/mext/route-{index}",
                canonical_source_urls=(str(canonical["source_url"]),),
                source_is_official=True,
                parent_scheme_explicit=True,
                explicit_relationship=relationship(str(route["expected_relationship"])),
            )
        )
        assert decision.relationship == RelationshipKind.SAME_SCHEME_TRACK
        assert decision.proposes_independent_scholarship is False

    assert fixture["expected_canonical_scholarship_count"] == 1
    assert fixture["expected_independent_scholarship_count"] == 0


def test_chevening_country_pages_resolve_to_same_scholarship_identity() -> None:
    fixture = load_fixture("chevening_country_pages.json")
    canonical = fixture["canonical_scholarship"]
    pages = fixture["country_pages"]
    assert isinstance(canonical, dict)
    assert isinstance(pages, list)

    classifier = DeterministicRelationshipClassifier()
    for page in pages:
        assert isinstance(page, dict)
        decision = classifier.classify(
            CandidateRelationshipContext(
                candidate_name=str(page["name"]),
                canonical_name=str(canonical["name"]),
                aliases=tuple(canonical["aliases"]),
                candidate_provider_id=str(canonical["provider_id"]),
                canonical_provider_id=str(canonical["provider_id"]),
                candidate_application_url=str(canonical["application_url"]),
                canonical_application_urls=(str(canonical["application_url"]),),
                candidate_source_url=str(page["source_url"]),
                canonical_source_urls=(str(canonical["source_url"]),),
                source_is_official=True,
                parent_scheme_explicit=True,
            )
        )
        assert decision.relationship == RelationshipKind.SAME_SCHOLARSHIP
        assert decision.proposes_independent_scholarship is False

    assert fixture["expected_canonical_scholarship_count"] == 1
    assert fixture["expected_independent_scholarship_count"] == 0


def test_university_csc_child_and_own_award_are_not_conflated() -> None:
    fixture = load_fixture("university_csc_plus_own_award.json")
    canonical = fixture["canonical_scholarship"]
    cases = fixture["cases"]
    assert isinstance(canonical, dict)
    assert isinstance(cases, list)

    csc_case = cases[0]
    own_award = cases[1]
    assert isinstance(csc_case, dict)
    assert isinstance(own_award, dict)

    child = DeterministicRelationshipClassifier().classify(
        CandidateRelationshipContext(
            candidate_name=str(csc_case["name"]),
            canonical_name=str(canonical["name"]),
            aliases=tuple(canonical["aliases"]),
            candidate_provider_id=str(canonical["provider_id"]),
            canonical_provider_id=str(canonical["provider_id"]),
            source_is_official=bool(csc_case["source_is_official"]),
            parent_scheme_explicit=bool(csc_case["parent_scheme_explicit"]),
            explicit_relationship=relationship(str(csc_case["explicit_relationship"])),
        )
    )
    assert child.relationship == RelationshipKind.PARTICIPATING_INSTITUTION
    assert child.proposes_independent_scholarship is False

    independence = own_award["independence"]
    assert isinstance(independence, dict)
    independent = decide_independence(
        IndependenceAssessment(
            official_name_evidence=EvidenceSupportType(str(independence["official_name_evidence"])),
            awarding_authority_evidence=EvidenceSupportType(
                str(independence["awarding_authority_evidence"])
            ),
            separate_application=bool(independence["separate_application"]),
            independent_award_decision=bool(independence["independent_award_decision"]),
            current_official_source=bool(independence["current_official_source"]),
            authority_type=IndependenceAuthorityType(str(independence["authority_type"])),
        )
    )
    assert independent.relationship == RelationshipKind.INDEPENDENT_UNIVERSITY_SCHOLARSHIP
    assert independent.proposes_independent_scholarship is True
    assert independent.requires_human_review is True
    assert independent.auto_publish_allowed is False


def test_registered_translation_resolves_but_unregistered_translation_stays_unresolved() -> None:
    fixture = load_fixture("name_translation_duplicate.json")
    canonical = fixture["canonical_scholarship"]
    cases = fixture["cases"]
    assert isinstance(canonical, dict)
    assert isinstance(cases, list)

    classifier = DeterministicRelationshipClassifier()
    for index, case in enumerate(cases, start=1):
        assert isinstance(case, dict)
        application_url = (
            str(canonical["application_url"])
            if bool(case["application_matches"])
            else f"https://example.edu/other-application-{index}"
        )
        decision = classifier.classify(
            CandidateRelationshipContext(
                candidate_name=str(case["name"]),
                canonical_name=str(canonical["name"]),
                aliases=tuple(canonical["aliases"]),
                candidate_provider_id=str(canonical["provider_id"]),
                canonical_provider_id=str(canonical["provider_id"]),
                candidate_application_url=application_url,
                canonical_application_urls=(str(canonical["application_url"]),),
                candidate_source_url=f"https://www.campuschina.org/alias-{index}",
                canonical_source_urls=(str(canonical["source_url"]),),
                source_is_official=bool(case["source_is_official"]),
                parent_scheme_explicit=False,
            )
        )
        assert decision.relationship == relationship(str(case["expected_relationship"]))
        assert decision.auto_publish_allowed is False


def test_local_deadline_fixture_is_scoped_child_not_independent_award() -> None:
    fixture = load_fixture("local_deadline_override.json")
    canonical = fixture["canonical_scholarship"]
    candidate = fixture["candidate"]
    assert isinstance(canonical, dict)
    assert isinstance(candidate, dict)

    decision = DeterministicRelationshipClassifier().classify(
        CandidateRelationshipContext(
            candidate_name=str(candidate["name"]),
            canonical_name=str(canonical["name"]),
            aliases=tuple(canonical["aliases"]),
            candidate_provider_id=str(canonical["provider_id"]),
            canonical_provider_id=str(canonical["provider_id"]),
            source_is_official=bool(candidate["source_is_official"]),
            parent_scheme_explicit=bool(candidate["parent_scheme_explicit"]),
            explicit_relationship=relationship(str(candidate["explicit_relationship"])),
        )
    )

    assert decision.relationship == RelationshipKind.INSTITUTION_SPECIFIC_DEADLINE
    assert decision.proposes_independent_scholarship is False
    assert fixture["expected_canonical_scholarship_count"] == 1
    assert fixture["expected_independent_scholarship_count"] == 0
