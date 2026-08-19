"""Adversarial PostgreSQL proof for PR6 bundle ownership integrity.

A resolution owned by bundle A must never be able to consume an assessment
owned by bundle B, even when every referenced row exists.
"""

from __future__ import annotations

import uuid

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
    CatalogueClaimResolutionMember,
)
from app.modules.catalogue_ingestion.resolution_core import (
    ApplicabilityStatus,
    AuthorityStatus,
    EvidenceMatchStatus,
    ResolutionMemberRole,
    ResolutionOutcome,
    ScopeResolutionStatus,
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

# The imported fixtures are part of the proof module's pytest namespace.
assert postgres_engine is not None
assert db_session is not None


def _assessment(
    *,
    bundle_claim_id: uuid.UUID,
    bundle_id: uuid.UUID,
    candidate_id: uuid.UUID,
    claim_key_hash: str,
    policy_label: str,
) -> CatalogueClaimAssessment:
    return CatalogueClaimAssessment(
        id=uuid.uuid4(),
        bundle_claim_id=bundle_claim_id,
        bundle_id=bundle_id,
        policy_fingerprint=_hash(f"assessment-policy:{policy_label}"),
        scope_resolver_version="test-scope.v1",
        authority_policy_version="test-authority.v1",
        canonicalizer_version="test-canonicalizer.v1",
        cycle_policy_version="test-cycle.v1",
        evidence_status=EvidenceMatchStatus.MATCHED,
        scope_status=ScopeResolutionStatus.UNRESOLVED_SCOPE,
        authority_status=AuthorityStatus.AUTHORIZED,
        authority_priority=0,
        applicability_status=ApplicabilityStatus.CURRENT_APPLICABLE,
        canonical_field_path="application.deadline",
        collection_key="deadline",
        candidate_id=candidate_id,
        scholarship_id=None,
        normalized_value_json={
            "kind": "temporal",
            "precision": "date",
            "calendar_date": "2027-05-20",
        },
        normalized_value_hash=_hash("2027-05-20"),
        claim_key_hash=claim_key_hash,
        reason_codes=[],
    )


def test_database_rejects_resolution_member_assessment_from_another_bundle(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="cross-bundle-resolution-member")
    text = "Applications close on 20 May 2027."
    snapshot, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/cross-bundle-resolution",
        text=text,
        contract_label="cross-bundle-resolution",
    )
    persisted = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    db_session.flush()

    bundle_a = _create_bundle(db_session, candidate_id=candidate.id, label="resolution-a")
    bundle_b = _create_bundle(db_session, candidate_id=candidate.id, label="assessment-b")
    source_a = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_a,
        snapshot=snapshot,
        label="resolution-a",
    )
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_b,
        snapshot=snapshot,
        label="assessment-b",
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

    claim_key_hash = _hash("application.deadline:cross-bundle-proof")
    assessment_a = _assessment(
        bundle_claim_id=bundle_claim_a.id,
        bundle_id=bundle_a.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label="a",
    )
    assessment_b = _assessment(
        bundle_claim_id=bundle_claim_b.id,
        bundle_id=bundle_b.id,
        candidate_id=candidate.id,
        claim_key_hash=claim_key_hash,
        policy_label="b",
    )
    resolution_a = CatalogueClaimResolution(
        id=uuid.uuid4(),
        bundle_id=bundle_a.id,
        claim_key_hash=claim_key_hash,
        canonical_field_path="application.deadline",
        collection_key="deadline",
        scope_snapshot={"candidate_id": str(candidate.id)},
        resolver_family="temporal",
        policy_fingerprint=_hash("resolution-policy:a"),
        outcome=ResolutionOutcome.UNRESOLVED,
        effective_state=None,
        effective_value_json=None,
        effective_value_hash=None,
        reason_codes=["cross_bundle_integrity_proof"],
    )
    db_session.add_all([assessment_a, assessment_b, resolution_a])
    db_session.flush()

    # Control: same-bundle membership remains valid.
    db_session.add(
        CatalogueClaimResolutionMember(
            id=uuid.uuid4(),
            resolution_id=resolution_a.id,
            claim_assessment_id=assessment_a.id,
            bundle_id=bundle_a.id,
            role=ResolutionMemberRole.UNRESOLVED,
        )
    )
    db_session.flush()

    # Attack: resolution A attempts to consume assessment B while presenting A
    # as the ownership witness. The resolution FK matches A; the assessment FK
    # must reject B.
    db_session.add(
        CatalogueClaimResolutionMember(
            id=uuid.uuid4(),
            resolution_id=resolution_a.id,
            claim_assessment_id=assessment_b.id,
            bundle_id=bundle_a.id,
            role=ResolutionMemberRole.UNRESOLVED,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
