"""Fail-closed human review, materialization, readiness, and publication workflow."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.auth.models import AuditLog, User
from app.modules.catalogue_ingestion.claim_schemas import (
    CLAIM_SCHEMA_VERSIONS,
    ClaimResolution,
    ScopedCoverageState,
)
from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    CatalogueIngestionRun,
)
from app.modules.catalogue_ingestion.review_models import (
    CatalogueCandidateReview,
    CatalogueProposalState,
)
from app.modules.catalogue_ingestion.review_schemas import (
    CatalogueCandidateReviewResponse,
    CataloguePublicationReadinessResponse,
)
from app.modules.catalogue_ingestion.rich_graph_materializer import (
    CATALOGUE_GRAPH_MATERIALIZER_VERSION,
    CatalogueGraphMaterializer,
)
from app.modules.catalogue_ingestion.topology_models import CatalogueCoverageCell
from app.modules.opportunities.evidence_models import EvidenceValidatorStatus, FieldEvidence
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.lifecycle import SOURCE_FRESHNESS_DAYS
from app.modules.opportunities.materialization_models import CatalogueMaterializedClaimLink
from app.modules.opportunities.models import (
    DuplicateSuggestion,
    DuplicateSuggestionStatus,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
)
from app.modules.opportunities.schemas import OpportunityCreate, ReviewAction, ReviewActionRequest
from app.modules.opportunities.service import OpportunityService

LEGACY_OPPORTUNITY_MATERIALIZER_VERSION = "catalogue-legacy-opportunity.v1"
_TERMINAL_COVERAGE_STATES = {
    ScopedCoverageState.COMPLETE,
    ScopedCoverageState.NOT_APPLICABLE,
}
_MUTABLE_PROPOSAL_STATES = {
    CatalogueProposalState.DRAFT,
    CatalogueProposalState.NEEDS_REVIEW,
    CatalogueProposalState.NEEDS_CHANGES,
    CatalogueProposalState.REJECTED,
}


class CatalogueReviewWorkflow:
    """Own the durable review boundary for one candidate proposal.

    Approval is persisted before materialization starts. Catalogue graph writes and the
    MATERIALIZED transition commit together. A failed graph write is rolled back before a safe
    failure receipt is stored on the still-approved proposal.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.opportunities = OpportunityService(session)

    def review(self, candidate_id: uuid.UUID) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=False)
        review = self.session.scalar(
            select(CatalogueCandidateReview).where(
                CatalogueCandidateReview.candidate_id == candidate.id
            )
        )
        return self._response(candidate, review)

    def submit(
        self,
        candidate_id: uuid.UUID,
        *,
        notes: str,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._ensure_review(candidate)
        review = self._sync_mutable_proposal(candidate, review)
        if review.state is CatalogueProposalState.SUBMITTED:
            self.session.commit()
            return self._response(candidate, review)
        if review.state not in _MUTABLE_PROPOSAL_STATES:
            raise AppError(
                "catalogue_proposal_not_submittable",
                f"Proposal cannot be submitted from state {review.state.value}",
                409,
            )
        if candidate.status not in {
            CandidateStatus.READY_FOR_REVIEW,
            CandidateStatus.NEEDS_REVIEW,
            CandidateStatus.REJECTED,
        }:
            raise AppError(
                "catalogue_candidate_not_ready",
                "Candidate has not reached the human review boundary",
                409,
            )
        review.state = CatalogueProposalState.SUBMITTED
        review.review_reason = notes.strip()[:2000]
        candidate.status = CandidateStatus.SUBMITTED_FOR_REVIEW
        self._audit(
            actor,
            "catalogue_proposal_submitted",
            candidate,
            review,
            {"proposal_hash": review.proposal_hash},
        )
        self.session.commit()
        return self._response(candidate, review)

    def approve(
        self,
        candidate_id: uuid.UUID,
        *,
        expected_proposal_hash: str,
        notes: str | None,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)

        if review.state in {
            CatalogueProposalState.PUBLICATION_READY,
            CatalogueProposalState.PUBLISHED,
        }:
            return self._response(candidate, review)
        if review.state is CatalogueProposalState.MATERIALIZED and candidate.opportunity_id:
            # Compatibility path for a legacy proposal materialized before the durable review row
            # existed. Human approval is still recorded explicitly before publication readiness.
            review.approved_proposal_hash = review.proposal_hash
            review.reviewed_by_user_id = actor.id
            review.reviewed_at = datetime.now(UTC)
            review.review_reason = (notes or "Legacy materialization approved").strip()[:2000]
            candidate.status = CandidateStatus.APPROVED
            self._audit(actor, "catalogue_proposal_approved", candidate, review)
            self.session.commit()
            return self._response(candidate, review)
        if review.state is not CatalogueProposalState.SUBMITTED:
            raise AppError(
                "catalogue_proposal_not_approvable",
                f"Proposal cannot be approved from state {review.state.value}",
                409,
            )

        review.state = CatalogueProposalState.APPROVED
        review.approved_proposal_hash = review.proposal_hash
        review.reviewed_by_user_id = actor.id
        review.reviewed_at = datetime.now(UTC)
        review.review_reason = (notes or "Approved for materialization").strip()[:2000]
        review.materialization_failure_code = None
        review.materialization_failure_reason = None
        candidate.status = CandidateStatus.APPROVED
        self._audit(actor, "catalogue_proposal_approved", candidate, review)
        self.session.commit()
        return self._attempt_materialization(candidate.id, actor=actor)

    def reject(
        self,
        candidate_id: uuid.UUID,
        *,
        expected_proposal_hash: str,
        reason: str,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)
        if review.state is CatalogueProposalState.REJECTED:
            return self._response(candidate, review)
        if review.state is not CatalogueProposalState.SUBMITTED:
            raise AppError(
                "catalogue_proposal_not_rejectable",
                f"Proposal cannot be rejected from state {review.state.value}",
                409,
            )
        if candidate.opportunity_id is not None:
            raise AppError(
                "catalogue_materialized_proposal_not_rejectable",
                "A materialized proposal cannot be rejected through the pre-materialization action",
                409,
            )
        review.state = CatalogueProposalState.REJECTED
        review.approved_proposal_hash = None
        review.reviewed_by_user_id = actor.id
        review.reviewed_at = datetime.now(UTC)
        review.review_reason = reason.strip()[:2000]
        candidate.status = CandidateStatus.REJECTED
        self._audit(actor, "catalogue_proposal_rejected", candidate, review)
        self.session.commit()
        return self._response(candidate, review)

    def request_changes(
        self,
        candidate_id: uuid.UUID,
        *,
        expected_proposal_hash: str,
        reason: str,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)
        if review.state is CatalogueProposalState.NEEDS_CHANGES:
            return self._response(candidate, review)
        if review.state not in {
            CatalogueProposalState.SUBMITTED,
            CatalogueProposalState.APPROVED,
        }:
            raise AppError(
                "catalogue_proposal_changes_not_requestable",
                f"Changes cannot be requested from state {review.state.value}",
                409,
            )
        if candidate.opportunity_id is not None:
            raise AppError(
                "catalogue_materialized_proposal_changes_require_refresh",
                "Materialized proposals require the change-aware refresh workflow",
                409,
            )
        review.state = CatalogueProposalState.NEEDS_CHANGES
        review.approved_proposal_hash = None
        review.reviewed_by_user_id = actor.id
        review.reviewed_at = datetime.now(UTC)
        review.review_reason = reason.strip()[:2000]
        review.materialization_failure_code = None
        review.materialization_failure_reason = None
        candidate.status = CandidateStatus.NEEDS_REVIEW
        self._audit(actor, "catalogue_proposal_changes_requested", candidate, review)
        self.session.commit()
        return self._response(candidate, review)

    def retry_materialization(
        self,
        candidate_id: uuid.UUID,
        *,
        expected_proposal_hash: str,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)
        if review.state in {
            CatalogueProposalState.MATERIALIZED,
            CatalogueProposalState.PUBLICATION_READY,
            CatalogueProposalState.PUBLISHED,
        } and candidate.opportunity_id is not None:
            return self._response(candidate, review)
        if review.state not in {
            CatalogueProposalState.APPROVED,
            CatalogueProposalState.MATERIALIZING,
        }:
            raise AppError(
                "catalogue_materialization_not_retryable",
                f"Materialization cannot run from state {review.state.value}",
                409,
            )
        self.session.rollback()
        return self._attempt_materialization(candidate_id, actor=actor)

    def publication_readiness(
        self, candidate_id: uuid.UUID
    ) -> CataloguePublicationReadinessResponse:
        candidate = self._candidate(candidate_id, for_update=False)
        review = self.session.scalar(
            select(CatalogueCandidateReview).where(
                CatalogueCandidateReview.candidate_id == candidate.id
            )
        )
        blockers, source_id = self._readiness(candidate, review)
        return CataloguePublicationReadinessResponse(
            candidate_id=candidate.id,
            opportunity_id=candidate.opportunity_id,
            proposal_hash=_proposal_hash(candidate.proposed_payload),
            ready=not blockers,
            blockers=blockers,
            official_source_id=source_id,
        )

    def mark_publication_ready(
        self,
        candidate_id: uuid.UUID,
        *,
        expected_proposal_hash: str,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)
        if review.state is CatalogueProposalState.PUBLICATION_READY:
            blockers, _ = self._readiness(candidate, review)
            if blockers:
                raise AppError(
                    "catalogue_publication_readiness_stale",
                    "Publication readiness is no longer valid: " + "; ".join(blockers[:8]),
                    409,
                )
            return self._response(candidate, review)
        if review.state is not CatalogueProposalState.MATERIALIZED:
            raise AppError(
                "catalogue_proposal_not_materialized",
                "Publication readiness can only be marked after successful materialization",
                409,
            )
        blockers, _ = self._readiness(candidate, review)
        if blockers:
            raise AppError(
                "catalogue_publication_not_ready",
                "Publication readiness gates failed: " + "; ".join(blockers[:8]),
                409,
            )
        review.state = CatalogueProposalState.PUBLICATION_READY
        review.publication_ready_at = datetime.now(UTC)
        self._audit(actor, "catalogue_proposal_publication_ready", candidate, review)
        self.session.commit()
        return self._response(candidate, review)

    def publish(
        self,
        candidate_id: uuid.UUID,
        *,
        expected_proposal_hash: str,
        notes: str | None,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)
        if review.state is CatalogueProposalState.PUBLISHED:
            return self._response(candidate, review)
        if review.state is not CatalogueProposalState.PUBLICATION_READY:
            raise AppError(
                "catalogue_proposal_not_publication_ready",
                "Proposal must be explicitly marked publication-ready before publishing",
                409,
            )
        run = self.session.get(CatalogueIngestionRun, candidate.run_id)
        if run is None:
            raise AppError("ingestion_run_not_found", "Ingestion run was not found", 404)
        if run.dry_run:
            raise AppError(
                "catalogue_dry_run_publish_forbidden",
                "Dry-run candidates can never transition to publication",
                409,
            )
        blockers, source_id = self._readiness(candidate, review)
        if blockers or source_id is None:
            raise AppError(
                "catalogue_publication_readiness_stale",
                "Publication readiness is no longer valid: " + "; ".join(blockers[:8]),
                409,
            )
        opportunity_id = candidate.opportunity_id
        if opportunity_id is None:
            raise AppError(
                "catalogue_materialized_opportunity_missing",
                "Materialized proposal has no associated opportunity",
                409,
            )

        # This is intentionally the existing authorized catalogue publication boundary. It owns
        # Opportunity/Source publication status and its verification/audit records.
        self.opportunities.apply_review_action(
            opportunity_id,
            ReviewActionRequest(
                action=ReviewAction.PUBLISH,
                source_id=source_id,
                notes=notes,
            ),
            reviewed_by=actor,
        )

        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        self._assert_expected_hash(candidate, review, expected_proposal_hash)
        review.state = CatalogueProposalState.PUBLISHED
        review.published_at = datetime.now(UTC)
        candidate.status = CandidateStatus.PUBLISHED
        self._audit(actor, "catalogue_proposal_published", candidate, review)
        self.session.commit()
        return self._response(candidate, review)

    def _attempt_materialization(
        self,
        candidate_id: uuid.UUID,
        *,
        actor: User,
    ) -> CatalogueCandidateReviewResponse:
        candidate = self._candidate(candidate_id, for_update=True)
        review = self._required_review(candidate)
        current_hash = self._assert_approved_current(candidate, review)
        if candidate.opportunity_id is not None and review.state in {
            CatalogueProposalState.MATERIALIZED,
            CatalogueProposalState.PUBLICATION_READY,
            CatalogueProposalState.PUBLISHED,
        }:
            return self._response(candidate, review)
        if review.state not in {
            CatalogueProposalState.APPROVED,
            CatalogueProposalState.MATERIALIZING,
        }:
            raise AppError(
                "catalogue_proposal_not_approved",
                "Only an approved proposal can be materialized",
                409,
            )

        review.state = CatalogueProposalState.MATERIALIZING
        review.materialization_attempt_count += 1
        review.materialization_failure_code = None
        review.materialization_failure_reason = None
        self._audit(actor, "catalogue_materialization_started", candidate, review)
        self.session.commit()

        try:
            candidate = self._candidate(candidate_id, for_update=True)
            review = self._required_review(candidate)
            current_hash = self._assert_approved_current(candidate, review)
            opportunity, materializer_version = self._materialize_current_proposal(
                candidate,
                review,
                current_hash,
            )
            candidate.opportunity_id = opportunity.id
            candidate.status = CandidateStatus.APPROVED
            review.state = CatalogueProposalState.MATERIALIZED
            review.materialization_revision = materializer_version
            review.materialization_failure_code = None
            review.materialization_failure_reason = None
            review.materialized_at = datetime.now(UTC)
            self._audit(
                actor,
                "catalogue_materialization_succeeded",
                candidate,
                review,
                {
                    "opportunity_id": str(opportunity.id),
                    "materialization_revision": materializer_version,
                },
            )
            # Catalogue graph writes and the durable MATERIALIZED receipt commit atomically.
            self.session.commit()
            return self._response(candidate, review)
        except Exception as exc:
            self.session.rollback()
            candidate = self._candidate(candidate_id, for_update=True)
            review = self._required_review(candidate)
            code, reason = _safe_materialization_failure(exc)
            if review.state is CatalogueProposalState.MATERIALIZING:
                review.state = CatalogueProposalState.APPROVED
            review.materialization_failure_code = code
            review.materialization_failure_reason = reason
            self._audit(
                actor,
                "catalogue_materialization_failed",
                candidate,
                review,
                {"failure_code": code},
            )
            self.session.commit()
            return self._response(candidate, review)

    def _materialize_current_proposal(
        self,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview,
        proposal_hash: str,
    ) -> tuple[Opportunity, str]:
        payload = candidate.proposed_payload
        if payload is None:
            raise ValueError("Candidate has no proposed payload")
        schema_version = payload.get("schema_version")
        if isinstance(schema_version, str) and schema_version in CLAIM_SCHEMA_VERSIONS:
            resolution = ClaimResolution.model_validate(payload)
            opportunity = CatalogueGraphMaterializer(self.session).materialize(
                candidate_id=candidate.id,
                review_id=review.id,
                proposal_hash=proposal_hash,
                resolution=resolution,
            )
            return opportunity, CATALOGUE_GRAPH_MATERIALIZER_VERSION

        legacy_payload = OpportunityCreate.model_validate(payload)
        response = self.opportunities.stage_opportunity_for_review(legacy_payload, commit=False)
        opportunity = self.session.get(Opportunity, response.id)
        if opportunity is None:
            raise RuntimeError("Legacy staged opportunity disappeared before materialization commit")
        return opportunity, LEGACY_OPPORTUNITY_MATERIALIZER_VERSION

    def _readiness(
        self,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview | None,
    ) -> tuple[list[str], uuid.UUID | None]:
        blockers: list[str] = []
        current_hash = _proposal_hash(candidate.proposed_payload)
        if review is None:
            return ["review_state_missing"], None
        if review.state not in {
            CatalogueProposalState.MATERIALIZED,
            CatalogueProposalState.PUBLICATION_READY,
            CatalogueProposalState.PUBLISHED,
        }:
            blockers.append(f"proposal_state:{review.state.value}")
        if current_hash is None:
            blockers.append("proposal_payload_missing")
        elif review.proposal_hash != current_hash:
            blockers.append("proposal_changed_since_review")
        if review.approved_proposal_hash is None or review.approved_proposal_hash != current_hash:
            blockers.append("approved_proposal_hash_mismatch")
        if review.reviewed_by_user_id is None or review.reviewed_at is None:
            blockers.append("human_approval_missing")
        if review.materialization_revision is None or candidate.opportunity_id is None:
            blockers.append("materialization_receipt_missing")

        run = self.session.get(CatalogueIngestionRun, candidate.run_id)
        if run is None:
            blockers.append("ingestion_run_missing")
        elif run.dry_run:
            blockers.append("dry_run_candidate")

        if candidate.validation_errors:
            blockers.append("candidate_validation_errors")
        if candidate.conflicts:
            blockers.append("candidate_conflicts_unresolved")

        resolution = self._claim_resolution(candidate)
        if resolution is not None:
            if resolution.conflicts:
                blockers.append("proposal_conflicts_unresolved")
            if resolution.rejected:
                blockers.append("proposal_claims_rejected_or_quarantined")
            if resolution.completeness_errors:
                blockers.append("proposal_completeness_unresolved")
            required_decisions = [item for item in resolution.scope_coverage if item.required]
            for item in required_decisions:
                if item.state not in _TERMINAL_COVERAGE_STATES:
                    blockers.append(
                        f"critical_coverage:{item.objective.value}:{item.scope_type}:"
                        f"{item.scope_key}:{item.state.value}"
                    )

            cells = list(
                self.session.scalars(
                    select(CatalogueCoverageCell).where(
                        CatalogueCoverageCell.candidate_id == candidate.id,
                        CatalogueCoverageCell.required.is_(True),
                    )
                )
            )
            if not cells:
                blockers.append("required_coverage_cells_missing")
            for cell in cells:
                if cell.state not in _TERMINAL_COVERAGE_STATES:
                    blockers.append(
                        f"critical_coverage_cell:{cell.objective.value}:{cell.state.value}"
                    )
            if review.proposal_hash:
                links = list(
                    self.session.scalars(
                        select(CatalogueMaterializedClaimLink).where(
                            CatalogueMaterializedClaimLink.candidate_id == candidate.id,
                            CatalogueMaterializedClaimLink.review_id == review.id,
                            CatalogueMaterializedClaimLink.proposal_hash == review.proposal_hash,
                        )
                    )
                )
                if len(links) < len(resolution.resolved):
                    blockers.append("materialized_claim_evidence_incomplete")
                evidence_ids = {link.field_evidence_id for link in links}
                evidence_rows = (
                    list(
                        self.session.scalars(
                            select(FieldEvidence).where(FieldEvidence.id.in_(evidence_ids))
                        )
                    )
                    if evidence_ids
                    else []
                )
                if len(evidence_rows) != len(evidence_ids):
                    blockers.append("field_evidence_missing")
                if any(
                    evidence.validator_status is not EvidenceValidatorStatus.PASSED
                    for evidence in evidence_rows
                ):
                    blockers.append("field_evidence_not_validated")

        source_id: uuid.UUID | None = None
        if candidate.opportunity_id is not None:
            opportunity = self.session.get(Opportunity, candidate.opportunity_id)
            if opportunity is None:
                blockers.append("materialized_opportunity_missing")
            else:
                if opportunity.status not in {OpportunityStatus.DRAFT, OpportunityStatus.ACTIVE}:
                    blockers.append(f"opportunity_status:{opportunity.status.value}")
                cycle = self.session.scalar(
                    select(OpportunityCycle).where(
                        OpportunityCycle.opportunity_id == opportunity.id
                    )
                )
                if cycle is None:
                    blockers.append("required_cycle_missing")
                if not opportunity.sources:
                    blockers.append("official_source_missing")
                else:
                    current_source = EvidencePolicy.select_current_official_source(
                        opportunity.sources,
                        require_fresh_days=SOURCE_FRESHNESS_DAYS,
                    )
                    if current_source is None:
                        blockers.append("fresh_verified_official_source_missing")
                    else:
                        source_id = current_source.id
                pending_duplicate = self.session.scalar(
                    select(DuplicateSuggestion).where(
                        DuplicateSuggestion.opportunity_id == opportunity.id,
                        DuplicateSuggestion.status == DuplicateSuggestionStatus.PENDING,
                    )
                )
                if pending_duplicate is not None:
                    blockers.append("duplicate_suggestion_pending")
                confirmed_duplicate = self.session.scalar(
                    select(DuplicateSuggestion).where(
                        DuplicateSuggestion.opportunity_id == opportunity.id,
                        DuplicateSuggestion.status == DuplicateSuggestionStatus.CONFIRMED_DUPLICATE,
                    )
                )
                if confirmed_duplicate is not None:
                    blockers.append("duplicate_suggestion_confirmed")

        return sorted(set(blockers)), source_id

    def _claim_resolution(self, candidate: CatalogueCandidate) -> ClaimResolution | None:
        payload = candidate.proposed_payload
        if payload is None:
            return None
        schema_version = payload.get("schema_version")
        if not isinstance(schema_version, str) or schema_version not in CLAIM_SCHEMA_VERSIONS:
            return None
        try:
            return ClaimResolution.model_validate(payload)
        except Exception:
            return None

    def _candidate(self, candidate_id: uuid.UUID, *, for_update: bool) -> CatalogueCandidate:
        statement = select(CatalogueCandidate).where(CatalogueCandidate.id == candidate_id)
        if for_update:
            statement = statement.with_for_update()
        candidate = self.session.scalar(statement)
        if candidate is None:
            raise AppError("catalogue_candidate_not_found", "Candidate was not found", 404)
        return candidate

    def _required_review(self, candidate: CatalogueCandidate) -> CatalogueCandidateReview:
        review = self.session.scalar(
            select(CatalogueCandidateReview)
            .where(CatalogueCandidateReview.candidate_id == candidate.id)
            .with_for_update()
        )
        if review is None:
            raise AppError(
                "catalogue_review_not_started",
                "Proposal must be submitted for review first",
                409,
            )
        return review

    def _ensure_review(self, candidate: CatalogueCandidate) -> CatalogueCandidateReview:
        review = self.session.scalar(
            select(CatalogueCandidateReview)
            .where(CatalogueCandidateReview.candidate_id == candidate.id)
            .with_for_update()
        )
        if review is not None:
            return review
        current_hash = _proposal_hash(candidate.proposed_payload)
        if current_hash is None:
            raise AppError(
                "catalogue_proposal_missing",
                "Candidate has no proposal to review",
                409,
            )
        state = _initial_review_state(candidate)
        review = CatalogueCandidateReview(
            candidate_id=candidate.id,
            state=state,
            proposal_schema_version=_proposal_schema_version(candidate.proposed_payload),
            proposal_hash=current_hash,
            approved_proposal_hash=(
                current_hash
                if state
                in {
                    CatalogueProposalState.MATERIALIZED,
                    CatalogueProposalState.PUBLICATION_READY,
                    CatalogueProposalState.PUBLISHED,
                }
                else None
            ),
            materialization_revision=(
                LEGACY_OPPORTUNITY_MATERIALIZER_VERSION
                if candidate.opportunity_id is not None
                else None
            ),
        )
        self.session.add(review)
        self.session.flush()
        return review

    def _sync_mutable_proposal(
        self,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview,
    ) -> CatalogueCandidateReview:
        current_hash = _proposal_hash(candidate.proposed_payload)
        if current_hash is None:
            raise AppError(
                "catalogue_proposal_missing",
                "Candidate has no proposal to review",
                409,
            )
        if review.proposal_hash == current_hash:
            return review
        if review.state not in _MUTABLE_PROPOSAL_STATES:
            raise AppError(
                "catalogue_proposal_changed_after_review",
                "Proposal changed after entering review; request changes and resubmit explicitly",
                409,
            )
        if review.proposal_hash is not None:
            review.review_revision += 1
        review.proposal_hash = current_hash
        review.proposal_schema_version = _proposal_schema_version(candidate.proposed_payload)
        review.approved_proposal_hash = None
        review.state = CatalogueProposalState.NEEDS_REVIEW
        review.reviewed_by_user_id = None
        review.reviewed_at = None
        review.review_reason = None
        review.materialization_failure_code = None
        review.materialization_failure_reason = None
        return review

    def _assert_expected_hash(
        self,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview,
        expected: str,
    ) -> str:
        current_hash = _proposal_hash(candidate.proposed_payload)
        if current_hash is None:
            raise AppError("catalogue_proposal_missing", "Candidate has no proposal", 409)
        if expected != current_hash:
            raise AppError(
                "catalogue_proposal_version_conflict",
                "Proposal changed since the administrator loaded it",
                409,
            )
        if review.proposal_hash != current_hash:
            raise AppError(
                "catalogue_proposal_changed_after_review",
                "Proposal changed after review submission; resubmit the new proposal before deciding",
                409,
            )
        return current_hash

    def _assert_approved_current(
        self,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview,
    ) -> str:
        current_hash = _proposal_hash(candidate.proposed_payload)
        if current_hash is None:
            raise AppError("catalogue_proposal_missing", "Candidate has no proposal", 409)
        if review.proposal_hash != current_hash or review.approved_proposal_hash != current_hash:
            raise AppError(
                "catalogue_approved_proposal_version_conflict",
                "Approved proposal no longer matches the candidate payload",
                409,
            )
        return current_hash

    def _response(
        self,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview | None,
    ) -> CatalogueCandidateReviewResponse:
        current_hash = _proposal_hash(candidate.proposed_payload)
        if review is None:
            return CatalogueCandidateReviewResponse(
                candidate_id=candidate.id,
                review_id=None,
                state=_initial_review_state(candidate),
                proposal_schema_version=_proposal_schema_version(candidate.proposed_payload),
                proposal_hash=None,
                current_proposal_hash=current_hash,
                approved_proposal_hash=None,
                proposal_changed_since_review=False,
                review_revision=0,
                reviewed_by_user_id=None,
                reviewed_at=None,
                review_reason=None,
                materialization_revision=None,
                materialization_attempt_count=0,
                materialization_failure_code=None,
                materialization_failure_reason=None,
                opportunity_id=candidate.opportunity_id,
                materialized_at=None,
                publication_ready_at=None,
                published_at=None,
                readiness_blockers=[],
            )
        readiness_blockers: list[str] = []
        if review.state in {
            CatalogueProposalState.MATERIALIZED,
            CatalogueProposalState.PUBLICATION_READY,
            CatalogueProposalState.PUBLISHED,
        }:
            readiness_blockers, _ = self._readiness(candidate, review)
        return CatalogueCandidateReviewResponse(
            candidate_id=candidate.id,
            review_id=review.id,
            state=review.state,
            proposal_schema_version=review.proposal_schema_version,
            proposal_hash=review.proposal_hash,
            current_proposal_hash=current_hash,
            approved_proposal_hash=review.approved_proposal_hash,
            proposal_changed_since_review=(
                current_hash is not None
                and review.proposal_hash is not None
                and current_hash != review.proposal_hash
            ),
            review_revision=review.review_revision,
            reviewed_by_user_id=review.reviewed_by_user_id,
            reviewed_at=review.reviewed_at,
            review_reason=review.review_reason,
            materialization_revision=review.materialization_revision,
            materialization_attempt_count=review.materialization_attempt_count,
            materialization_failure_code=review.materialization_failure_code,
            materialization_failure_reason=review.materialization_failure_reason,
            opportunity_id=candidate.opportunity_id,
            materialized_at=review.materialized_at,
            publication_ready_at=review.publication_ready_at,
            published_at=review.published_at,
            readiness_blockers=readiness_blockers,
        )

    def _audit(
        self,
        actor: User,
        action: str,
        candidate: CatalogueCandidate,
        review: CatalogueCandidateReview,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_user_id=actor.id,
                action=action,
                entity_type="catalogue_candidate",
                entity_id=str(candidate.id),
                metadata_json={
                    "review_id": str(review.id),
                    "state": review.state.value,
                    "review_revision": review.review_revision,
                    **(metadata or {}),
                },
            )
        )


def _initial_review_state(candidate: CatalogueCandidate) -> CatalogueProposalState:
    if candidate.status is CandidateStatus.PUBLISHED:
        return CatalogueProposalState.PUBLISHED
    if candidate.opportunity_id is not None:
        return CatalogueProposalState.MATERIALIZED
    if candidate.status is CandidateStatus.APPROVED:
        return CatalogueProposalState.APPROVED
    if candidate.status is CandidateStatus.SUBMITTED_FOR_REVIEW:
        return CatalogueProposalState.SUBMITTED
    if candidate.status is CandidateStatus.REJECTED:
        return CatalogueProposalState.REJECTED
    if candidate.status in {CandidateStatus.READY_FOR_REVIEW, CandidateStatus.NEEDS_REVIEW}:
        return CatalogueProposalState.NEEDS_REVIEW
    return CatalogueProposalState.DRAFT


def _proposal_hash(payload: dict[str, object] | None) -> str | None:
    if payload is None:
        return None
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _proposal_schema_version(payload: dict[str, object] | None) -> str | None:
    if payload is None:
        return None
    value = payload.get("schema_version")
    return str(value)[:100] if isinstance(value, str) else LEGACY_OPPORTUNITY_MATERIALIZER_VERSION


def _safe_materialization_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AppError):
        return str(exc.code)[:100], str(exc.message)[:1000]
    if isinstance(exc, ValueError):
        return "materialization_validation_failed", str(exc)[:1000]
    return "materialization_failed", "Materialization failed without committing catalogue writes"


__all__ = ["CatalogueReviewWorkflow", "LEGACY_OPPORTUNITY_MATERIALIZER_VERSION"]
