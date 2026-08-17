from app.modules.catalogue_ingestion.classification import (
    IndependenceAssessment,
    IndependenceAuthorityType,
    decide_independence,
)
from app.modules.opportunities.evidence_models import EvidenceSupportType
from app.modules.opportunities.graph_models import RelationshipKind


def assessment(**overrides: object) -> IndependenceAssessment:
    values: dict[str, object] = {
        "proposed_relationship": RelationshipKind.UNRESOLVED,
        "official_name_evidence": EvidenceSupportType.EXPLICIT,
        "awarding_authority_evidence": EvidenceSupportType.EXPLICIT,
        "separate_application": True,
        "independent_award_decision": True,
        "current_official_source": True,
        "authority_type": IndependenceAuthorityType.UNIVERSITY,
        "conflicts": (),
    }
    values.update(overrides)
    return IndependenceAssessment(**values)


def test_all_mandatory_proofs_can_only_propose_independent_university_award() -> None:
    decision = decide_independence(assessment())

    assert decision.relationship == RelationshipKind.INDEPENDENT_UNIVERSITY_SCHOLARSHIP
    assert decision.reason_code == "independence_proven_pending_human_review"
    assert decision.proposes_independent_scholarship is True
    assert decision.requires_human_review is True
    assert decision.auto_publish_allowed is False


def test_government_and_foundation_authorities_map_to_correct_relationships() -> None:
    government = decide_independence(
        assessment(authority_type=IndependenceAuthorityType.GOVERNMENT)
    )
    foundation = decide_independence(
        assessment(authority_type=IndependenceAuthorityType.FOUNDATION)
    )

    assert government.relationship == RelationshipKind.INDEPENDENT_GOVERNMENT_SCHOLARSHIP
    assert foundation.relationship == RelationshipKind.INDEPENDENT_FOUNDATION_SCHOLARSHIP


def test_missing_official_name_proof_fails_closed() -> None:
    decision = decide_independence(
        assessment(official_name_evidence=EvidenceSupportType.PARTIAL)
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert "official_name" in decision.missing_mandatory_proofs
    assert decision.proposes_independent_scholarship is False


def test_missing_awarding_authority_proof_fails_closed() -> None:
    decision = decide_independence(
        assessment(awarding_authority_evidence=EvidenceSupportType.UNKNOWN)
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert "awarding_authority" in decision.missing_mandatory_proofs


def test_separate_application_and_independent_decision_are_both_mandatory() -> None:
    no_application = decide_independence(assessment(separate_application=False))
    unknown_decision = decide_independence(assessment(independent_award_decision=None))

    assert no_application.relationship == RelationshipKind.UNRESOLVED
    assert "separate_application" in no_application.missing_mandatory_proofs
    assert unknown_decision.relationship == RelationshipKind.UNRESOLVED
    assert "independent_award_decision" in unknown_decision.missing_mandatory_proofs


def test_current_official_source_is_mandatory() -> None:
    decision = decide_independence(assessment(current_official_source=False))

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert "current_official_source" in decision.missing_mandatory_proofs


def test_conflicts_block_independence_even_when_all_positive_signals_exist() -> None:
    decision = decide_independence(
        assessment(conflicts=("authority differs between official pages",))
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert decision.reason_code == "independence_conflict_requires_review"
    assert decision.proposes_independent_scholarship is False


def test_unknown_authority_type_cannot_create_independent_award() -> None:
    decision = decide_independence(
        assessment(authority_type=IndependenceAuthorityType.UNKNOWN)
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert "recognized_awarding_authority_type" in decision.missing_mandatory_proofs


def test_route_and_child_relationships_can_never_pass_through_independence_gate() -> None:
    relationships = (
        RelationshipKind.SAME_SCHOLARSHIP,
        RelationshipKind.SAME_SCHEME_TRACK,
        RelationshipKind.PARTICIPATING_INSTITUTION,
        RelationshipKind.ELIGIBLE_PROGRAMME,
        RelationshipKind.INSTITUTION_SPECIFIC_REQUIREMENT,
        RelationshipKind.INSTITUTION_SPECIFIC_DEADLINE,
        RelationshipKind.DUPLICATE,
    )

    for relationship in relationships:
        decision = decide_independence(assessment(proposed_relationship=relationship))
        assert decision.relationship == relationship
        assert decision.reason_code == "existing_or_child_relationship"
        assert decision.proposes_independent_scholarship is False
        assert decision.requires_human_review is True
        assert decision.auto_publish_allowed is False


def test_name_difference_or_separate_deadline_is_not_an_independence_proof() -> None:
    decision = decide_independence(
        assessment(
            awarding_authority_evidence=EvidenceSupportType.UNKNOWN,
            separate_application=None,
            independent_award_decision=None,
        )
    )

    assert decision.relationship == RelationshipKind.UNRESOLVED
    assert decision.proposes_independent_scholarship is False
    assert decision.auto_publish_allowed is False
