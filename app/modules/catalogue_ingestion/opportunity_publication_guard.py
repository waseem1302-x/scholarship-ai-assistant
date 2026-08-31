"""Catalogue-aware guard around the existing authorized opportunity publication service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.catalogue_ingestion.models import CatalogueCandidate
from app.modules.catalogue_ingestion.review_models import (
    CatalogueCandidateReview,
    CatalogueProposalState,
)
from app.modules.catalogue_ingestion.review_workflow import CatalogueReviewWorkflow
from app.modules.opportunities.schemas import (
    AdminOpportunityResponse,
    ReviewAction,
    ReviewActionRequest,
)
from app.modules.opportunities.service import OpportunityService


class CatalogueAwareOpportunityService(OpportunityService):
    """Preserve normal opportunity behavior while blocking catalogue-ingestion publish bypasses."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def apply_review_action(
        self,
        opportunity_id: uuid.UUID,
        payload: ReviewActionRequest,
        *,
        reviewed_by: User,
    ) -> AdminOpportunityResponse:
        candidate: CatalogueCandidate | None = None
        review: CatalogueCandidateReview | None = None
        activating = payload.action in {ReviewAction.PUBLISH, ReviewAction.RESOLVE_CONFLICT}
        if activating:
            candidate = self.session.scalar(
                select(CatalogueCandidate).where(
                    CatalogueCandidate.opportunity_id == opportunity_id
                )
            )
            if candidate is not None:
                review = self.session.scalar(
                    select(CatalogueCandidateReview).where(
                        CatalogueCandidateReview.candidate_id == candidate.id
                    )
                )
                if review is None or review.state not in {
                    CatalogueProposalState.PUBLICATION_READY,
                    CatalogueProposalState.PUBLISHED,
                }:
                    raise AppError(
                        "catalogue_publication_workflow_required",
                        "Catalogue-ingestion opportunities must pass the candidate "
                        "publication-readiness workflow before activation",
                        409,
                    )
                readiness = CatalogueReviewWorkflow(self.session).publication_readiness(
                    candidate.id
                )
                if not readiness.ready:
                    raise AppError(
                        "catalogue_publication_readiness_stale",
                        "Catalogue publication readiness is no longer valid: "
                        + "; ".join(readiness.blockers[:8]),
                        409,
                    )

        result = super().apply_review_action(
            opportunity_id,
            payload,
            reviewed_by=reviewed_by,
        )

        if activating and candidate is not None and review is not None:
            # The base service commits the authorized opportunity/source transition. Keep the
            # ingestion review receipt convergent so publishing from either admin surface is
            # idempotent and does not leave a stale PUBLICATION_READY record behind.
            review = self.session.scalar(
                select(CatalogueCandidateReview)
                .where(CatalogueCandidateReview.id == review.id)
                .with_for_update()
            )
            if review is not None and review.state is not CatalogueProposalState.PUBLISHED:
                review.state = CatalogueProposalState.PUBLISHED
                review.published_at = datetime.now(UTC)
                self.session.commit()
        return result


__all__ = ["CatalogueAwareOpportunityService"]
