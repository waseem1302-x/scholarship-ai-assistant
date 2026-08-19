"""Adversarial PostgreSQL proofs for PR6 conflict ownership integrity."""

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
    CatalogueConflictClaim,
    CatalogueConflictReviewDecision,
    CatalogueConflictSet,
    ConflictReviewDecisionType,
    ConflictSetStatus,
    ConflictSeverity,
)
from app.modules.catalogue_ingestion.resolution_core import ResolutionMemberRole, ResolutionOutcome
from tests.test_pr6_bundle_ownership_integrity import _assessment
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
class _ConflictContext:
    bundle_a_id: uuid.UUID
    assessment_member_a: CatalogueClaimAssessment
    assessment_nonmember_a: CatalogueClaimAssessment
    assessment_b: CatalogueClaimAssessment
    resolution_a: CatalogueClaimResolution
    claim_key_hash: str


def _seed_conflict_context(db_session: Session, *, label: str) -> _ConflictContext:
    candidate = _create_candidate(db_session, label=label)
    text = "Applications close on 20 May 2027."
    snapshot, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url=f"https://official.example/{label}",
        text=text,
        contract_label=label,
    )
    persisted = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    db_session.flush()

    bundle_a = _create_bundle(db_session, candidate_id=candidate.id, label=f"{label}-a")
    bundle_b = _create_bundle(db_session, candidate_id=candidate.id, label=f"{label}-b")
    source_a = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_a,
        snapshot=snapshot,
        label=f"{label}-a",
    )
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_b,
        snapshot=snapshot,
        label=f"{label}-b",
    )
    db_session.flush()

    bundle_claim_a = bind_claim_to_bundle(
        db_session,
        bundle_id=bundle_a.id,
        bundle_source_id=source_a.id,
        claim_id=persisted.claim.id,
    )
    bundle_claim_b = bind_claim_to_bundle(
        db_session,
        bundle_id=bundle_b.id,
        bundle_source_id=source_b.id,
        claim_id=persisted.claim.id,
    )
    db_session.flush()

    claim_key_hash = _hash(f"application.deadline:{label}")
    assessment_member_a = _assessment(
        bundle_claim_id=bundle_claim_a.id,
        bundle_id=bundle_a.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label=f"{label}-member-a",
    )
    assessment_nonmember_a = _assessment(
        bundle_claim_id=bundle_claim_a.id,
        bundle_id=bundle_a.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label=f"{label}-nonmember-a",
    )
    assessment_b = _assessment(
        bundle_claim_id=bundle_claim_b.id,
        bundle_id=bundle_b.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label=f"{label}-b",
    )
    resolution_a = CatalogueClaimResolution(
        id=uuid.uuid4(),
        bundle_id=bundle_a.id,
        claim_key_hash=claim_key_hash,
        canonical_field_path="application.deadline",
        collection_key="deadline",
        scope_snapshot={"candidate_id": str(candidate.id)},
        resolver_family="temporal",
        policy_fingerprint=_hash(f"resolution-policy:{label}"),
        outcome=ResolutionOutcome.CONFLICT_REVIEW_REQUIRED,
        effective_state=None,
        effective_value_json=None,
        effective_value_hash=None,
        reason_codes=["conflict_ownership_integrity_proof"],
    )
    db_session.add_all(
        [
            assessment_member_a,
            assessment_nonmember_a,
            assessment_b,
            resolution_a,
        ]
    )
    db_session.flush()

    return _ConflictContext(
        bundle_a_id=bundle_a.id,
        assessment_member_a=assessment_member_a,
        assessment_nonmember_a=assessment_nonmember_a,
        assessment_b=assessment_b,
        resolution_a=resolution_a,
        claim_key_hash=claim_key_hash,
    )


def _conflict_set(context: _ConflictContext, *, reason_code: str) -> CatalogueConflictSet:
    return CatalogueConflictSet(
        id=uuid.uuid4(),
        bundle_id=context.bundle_a_id,
        resolution_id=context.resolution_a.id,
        claim_key_hash=context.claim_key_hash,
        severity=ConflictSeverity.BLOCKING,
        status=ConflictSetStatus.OPEN,
        reason_code=reason_code,
        resolved_at=None,
    )


def test_database_rejects_conflict_claim_assessment_from_another_bundle(
    db_session: Session,
) -> None:
    context = _seed_conflict_context(db_session, label="cross-bundle-conflict-claim")
    conflict = _conflict_set(context, reason_code="cross_bundle_conflict_claim")
    db_session.add(conflict)
    db_session.flush()

    # Control: a same-bundle assessment can be a member of the conflict set.
    db_session.add(
        CatalogueConflictClaim(
            id=uuid.uuid4(),
            conflict_set_id=conflict.id,
            claim_assessment_id=context.assessment_member_a.id,
            role=ResolutionMemberRole.COMPETING,
        )
    )
    db_session.flush()

    # Attack: conflict set A attempts to consume assessment B.
    db_session.add(
        CatalogueConflictClaim(
            id=uuid.uuid4(),
            conflict_set_id=conflict.id,
            claim_assessment_id=context.assessment_b.id,
            role=ResolutionMemberRole.COMPETING,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_review_selection_not_in_conflict_set(
    db_session: Session,
) -> None:
    context = _seed_conflict_context(db_session, label="review-selection-membership")
    conflict = _conflict_set(context, reason_code="review_selection_membership")
    db_session.add(conflict)
    db_session.flush()

    # The conflict contains only assessment_member_a.
    db_session.add(
        CatalogueConflictClaim(
            id=uuid.uuid4(),
            conflict_set_id=conflict.id,
            claim_assessment_id=context.assessment_member_a.id,
            role=ResolutionMemberRole.COMPETING,
        )
    )
    db_session.flush()

    # Attack: this assessment belongs to bundle A but is not a member of this
    # conflict set. A SELECT_CLAIM review must not be able to select it.
    db_session.add(
        CatalogueConflictReviewDecision(
            id=uuid.uuid4(),
            conflict_set_id=conflict.id,
            supersedes_decision_id=None,
            decision=ConflictReviewDecisionType.SELECT_CLAIM,
            selected_claim_assessment_id=context.assessment_nonmember_a.id,
            resolution_notes="Adversarial proof: selected assessment is not in this conflict set.",
            reviewer_id=uuid.uuid4(),
            reviewer_identity_snapshot={"source": "adversarial-test"},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
