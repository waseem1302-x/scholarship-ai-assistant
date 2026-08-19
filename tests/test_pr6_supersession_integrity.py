"""Adversarial PostgreSQL proofs for PR6 supersession semantic integrity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.evidence_ledger import (
    bind_claim_to_bundle,
    persist_source_claim,
)
from app.modules.catalogue_ingestion.evidence_ledger_models import (
    CatalogueClaimAssessment,
    CatalogueClaimResolution,
    CatalogueConflictReviewDecision,
    CatalogueConflictSet,
    CatalogueGraphMaterialization,
    ConflictReviewDecisionType,
    MaterializationOperation,
)
from app.modules.catalogue_ingestion.resolution_core import ResolutionOutcome
from tests.test_pr6_bundle_ownership_integrity import _assessment
from tests.test_pr6_conflict_ownership_integrity import (
    _conflict_set,
    _seed_conflict_context,
)
from tests.test_pr6_evidence_ledger_persistence import (
    _add_candidate_artifact,
    _attach_candidate_snapshot,
    _create_bundle,
    _create_candidate,
    _deadline_claim,
    _hash,
    db_session,
    postgres_engine,
)

# The imported fixtures are part of this proof module's pytest namespace.
assert postgres_engine is not None
assert db_session is not None


@dataclass(frozen=True)
class _AssessmentSupersessionContext:
    bundle_id: uuid.UUID
    candidate_id: uuid.UUID
    bundle_claim_a_id: uuid.UUID
    assessment_a: CatalogueClaimAssessment
    assessment_b: CatalogueClaimAssessment
    claim_key_hash: str


def _seed_two_claims_in_one_bundle(
    db_session: Session,
    *,
    label: str,
) -> _AssessmentSupersessionContext:
    candidate = _create_candidate(db_session, label=label)
    text_a = "Applications close on 20 May 2027."
    text_b = "The application deadline is 20 May 2027."
    snapshot_a, extraction_a = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url=f"https://official.example/{label}/provider",
        text=text_a,
        contract_label=f"{label}-provider",
    )
    snapshot_b, extraction_b = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url=f"https://official.example/{label}/embassy",
        text=text_b,
        contract_label=f"{label}-embassy",
    )
    claim_a = persist_source_claim(
        db_session,
        extraction_id=extraction_a.id,
        ordinal=0,
        claim=_deadline_claim(text_a),
    )
    claim_b = persist_source_claim(
        db_session,
        extraction_id=extraction_b.id,
        ordinal=0,
        claim=_deadline_claim(text_b),
    )
    db_session.flush()

    bundle = _create_bundle(db_session, candidate_id=candidate.id, label=label)
    source_a = _attach_candidate_snapshot(
        db_session,
        bundle=bundle,
        snapshot=snapshot_a,
        label=f"{label}-provider",
    )
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle,
        snapshot=snapshot_b,
        label=f"{label}-embassy",
    )
    db_session.flush()

    bundle_claim_a = bind_claim_to_bundle(
        db_session,
        bundle_id=bundle.id,
        bundle_source_id=source_a.id,
        claim_id=claim_a.claim.id,
    )
    bundle_claim_b = bind_claim_to_bundle(
        db_session,
        bundle_id=bundle.id,
        bundle_source_id=source_b.id,
        claim_id=claim_b.claim.id,
    )
    db_session.flush()

    claim_key_hash = _hash(f"application.deadline:{label}")
    assessment_a = _assessment(
        bundle_claim_id=bundle_claim_a.id,
        bundle_id=bundle.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label=f"{label}-claim-a",
    )
    assessment_b = _assessment(
        bundle_claim_id=bundle_claim_b.id,
        bundle_id=bundle.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label=f"{label}-claim-b",
    )
    db_session.add_all([assessment_a, assessment_b])
    db_session.flush()

    return _AssessmentSupersessionContext(
        bundle_id=bundle.id,
        candidate_id=candidate.id,
        bundle_claim_a_id=bundle_claim_a.id,
        assessment_a=assessment_a,
        assessment_b=assessment_b,
        claim_key_hash=claim_key_hash,
    )


def _resolution(
    *,
    bundle_id: uuid.UUID,
    candidate_id: uuid.UUID,
    claim_key_hash: str,
    policy_label: str,
    supersedes_resolution_id: uuid.UUID | None,
) -> CatalogueClaimResolution:
    return CatalogueClaimResolution(
        id=uuid.uuid4(),
        bundle_id=bundle_id,
        supersedes_resolution_id=supersedes_resolution_id,
        claim_key_hash=claim_key_hash,
        canonical_field_path="application.deadline",
        collection_key="deadline",
        scope_snapshot={"candidate_id": str(candidate_id)},
        resolver_family="temporal",
        policy_fingerprint=_hash(f"resolution-policy:{policy_label}"),
        outcome=ResolutionOutcome.UNRESOLVED,
        effective_state=None,
        effective_value_json=None,
        effective_value_hash=None,
        reason_codes=["supersession_integrity_proof"],
    )


def _review_decision(
    *,
    conflict_set_id: uuid.UUID,
    supersedes_decision_id: uuid.UUID | None,
    label: str,
    row_id: uuid.UUID | None = None,
) -> CatalogueConflictReviewDecision:
    return CatalogueConflictReviewDecision(
        id=row_id or uuid.uuid4(),
        conflict_set_id=conflict_set_id,
        supersedes_decision_id=supersedes_decision_id,
        decision=ConflictReviewDecisionType.KEEP_UNRESOLVED,
        selected_claim_assessment_id=None,
        resolution_notes=f"Supersession integrity proof: {label}.",
        reviewer_id=uuid.uuid4(),
        reviewer_identity_snapshot={"source": "adversarial-test"},
    )


def _materialization(
    *,
    resolution_id: uuid.UUID,
    entity_id: uuid.UUID,
    field_path: str,
    label: str,
    previous_materialization_id: uuid.UUID | None,
    row_id: uuid.UUID | None = None,
) -> CatalogueGraphMaterialization:
    return CatalogueGraphMaterialization(
        id=row_id or uuid.uuid4(),
        resolution_id=resolution_id,
        materializer_version="test-materializer.v1",
        operation=MaterializationOperation.UPDATE,
        entity_type="candidate",
        entity_id=entity_id,
        field_path=field_path,
        target_state_fingerprint=_hash(f"target:{label}"),
        resulting_state_fingerprint=_hash(f"result:{label}"),
        previous_materialization_id=previous_materialization_id,
        idempotency_key=_hash(f"materialization:{label}"),
    )


def test_database_rejects_assessment_superseding_different_bundle_claim(
    db_session: Session,
) -> None:
    context = _seed_two_claims_in_one_bundle(db_session, label="assessment-claim-identity")

    control = _assessment(
        bundle_claim_id=context.bundle_claim_a_id,
        bundle_id=context.bundle_id,
        candidate_id=context.candidate_id,
        claim_key_hash=context.claim_key_hash,
        policy_label="assessment-control",
    )
    control.supersedes_assessment_id = context.assessment_a.id
    db_session.add(control)
    db_session.flush()

    attack = _assessment(
        bundle_claim_id=context.bundle_claim_a_id,
        bundle_id=context.bundle_id,
        candidate_id=context.candidate_id,
        claim_key_hash=context.claim_key_hash,
        policy_label="assessment-cross-claim-attack",
    )
    attack.supersedes_assessment_id = context.assessment_b.id
    db_session.add(attack)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_assessment_superseding_itself(db_session: Session) -> None:
    context = _seed_two_claims_in_one_bundle(db_session, label="assessment-self")
    row = _assessment(
        bundle_claim_id=context.bundle_claim_a_id,
        bundle_id=context.bundle_id,
        candidate_id=context.candidate_id,
        claim_key_hash=context.claim_key_hash,
        policy_label="assessment-self-attack",
    )
    row.supersedes_assessment_id = row.id
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_resolution_superseding_different_claim_key(
    db_session: Session,
) -> None:
    context = _seed_conflict_context(db_session, label="resolution-key-identity")
    candidate_id = context.assessment_member_a.candidate_id
    assert candidate_id is not None

    control = _resolution(
        bundle_id=context.bundle_a_id,
        candidate_id=candidate_id,
        claim_key_hash=context.claim_key_hash,
        policy_label="resolution-control",
        supersedes_resolution_id=context.resolution_a.id,
    )
    db_session.add(control)
    db_session.flush()

    attack = _resolution(
        bundle_id=context.bundle_a_id,
        candidate_id=candidate_id,
        claim_key_hash=_hash("application.deadline:different-claim-key"),
        policy_label="resolution-cross-key-attack",
        supersedes_resolution_id=context.resolution_a.id,
    )
    db_session.add(attack)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_resolution_superseding_itself(db_session: Session) -> None:
    context = _seed_conflict_context(db_session, label="resolution-self")
    candidate_id = context.assessment_member_a.candidate_id
    assert candidate_id is not None
    row_id = uuid.uuid4()
    row = _resolution(
        bundle_id=context.bundle_a_id,
        candidate_id=candidate_id,
        claim_key_hash=context.claim_key_hash,
        policy_label="resolution-self-attack",
        supersedes_resolution_id=row_id,
    )
    row.id = row_id
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_review_decision_superseding_another_conflict_set(
    db_session: Session,
) -> None:
    context = _seed_conflict_context(db_session, label="review-conflict-identity")
    conflict_a = _conflict_set(context, reason_code="supersession_conflict_a")
    db_session.add(conflict_a)
    db_session.flush()

    candidate_id = context.assessment_member_a.candidate_id
    assert candidate_id is not None
    resolution_b = _resolution(
        bundle_id=context.bundle_a_id,
        candidate_id=candidate_id,
        claim_key_hash=_hash("application.deadline:second-conflict-key"),
        policy_label="second-conflict-resolution",
        supersedes_resolution_id=None,
    )
    db_session.add(resolution_b)
    db_session.flush()
    conflict_b = CatalogueConflictSet(
        id=uuid.uuid4(),
        bundle_id=context.bundle_a_id,
        resolution_id=resolution_b.id,
        claim_key_hash=resolution_b.claim_key_hash,
        severity=conflict_a.severity,
        status=conflict_a.status,
        reason_code="supersession_conflict_b",
        resolved_at=None,
    )
    db_session.add(conflict_b)
    db_session.flush()

    first = _review_decision(
        conflict_set_id=conflict_a.id,
        supersedes_decision_id=None,
        label="first-decision",
    )
    db_session.add(first)
    db_session.flush()

    control = _review_decision(
        conflict_set_id=conflict_a.id,
        supersedes_decision_id=first.id,
        label="same-conflict-control",
    )
    db_session.add(control)
    db_session.flush()

    attack = _review_decision(
        conflict_set_id=conflict_b.id,
        supersedes_decision_id=first.id,
        label="cross-conflict-attack",
    )
    db_session.add(attack)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_review_decision_superseding_itself(db_session: Session) -> None:
    context = _seed_conflict_context(db_session, label="review-self")
    conflict = _conflict_set(context, reason_code="review_self_supersession")
    db_session.add(conflict)
    db_session.flush()

    row_id = uuid.uuid4()
    row = _review_decision(
        conflict_set_id=conflict.id,
        supersedes_decision_id=row_id,
        label="review-self-attack",
        row_id=row_id,
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_previous_materialization_for_different_target(
    db_session: Session,
) -> None:
    context = _seed_conflict_context(db_session, label="materialization-target-identity")
    entity_id = context.assessment_member_a.candidate_id
    assert entity_id is not None

    first = _materialization(
        resolution_id=context.resolution_a.id,
        entity_id=entity_id,
        field_path="application.deadline",
        label="materialization-first",
        previous_materialization_id=None,
    )
    db_session.add(first)
    db_session.flush()

    control = _materialization(
        resolution_id=context.resolution_a.id,
        entity_id=entity_id,
        field_path="application.deadline",
        label="materialization-same-target-control",
        previous_materialization_id=first.id,
    )
    db_session.add(control)
    db_session.flush()

    attack = _materialization(
        resolution_id=context.resolution_a.id,
        entity_id=entity_id,
        field_path="application.opening",
        label="materialization-cross-target-attack",
        previous_materialization_id=first.id,
    )
    db_session.add(attack)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_materialization_previous_link_to_itself(
    db_session: Session,
) -> None:
    context = _seed_conflict_context(db_session, label="materialization-self")
    entity_id = context.assessment_member_a.candidate_id
    assert entity_id is not None
    row_id = uuid.uuid4()
    row = _materialization(
        resolution_id=context.resolution_a.id,
        entity_id=entity_id,
        field_path="application.deadline",
        label="materialization-self-attack",
        previous_materialization_id=row_id,
        row_id=row_id,
    )
    db_session.add(row)
    with pytest.raises(IntegrityError):
        db_session.flush()
