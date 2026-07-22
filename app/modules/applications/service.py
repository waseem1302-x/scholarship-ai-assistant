import uuid

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError
from app.modules.applications.models import ApplicationStatus, SavedOpportunity
from app.modules.applications.repository import SavedOpportunityRepository
from app.modules.applications.schemas import (
    ChecklistItem,
    SavedOpportunityCreate,
    SavedOpportunityResponse,
    SavedOpportunityUpdate,
)
from app.modules.auth.models import User
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    SourceType,
    VerificationStatus,
)
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.service import OpportunityService


class SavedOpportunityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SavedOpportunityRepository(session)
        self.opportunities = OpportunityRepository(session)
        self.opportunity_service = OpportunityService(session)

    def create(self, payload: SavedOpportunityCreate, *, user: User) -> SavedOpportunityResponse:
        opportunity = self._get_public_verified_opportunity(payload.opportunity_id)
        if self.repository.get_by_user_and_opportunity(user.id, opportunity.id) is not None:
            raise ConflictError(
                "opportunity_already_saved",
                "This opportunity is already saved in your tracker",
            )

        saved = SavedOpportunity(
            user_id=user.id,
            opportunity_id=opportunity.id,
            status=payload.status,
            personal_notes=payload.personal_notes,
            personal_deadline=payload.personal_deadline,
            document_checklist=self._checklist_to_json(payload.document_checklist),
            recommendation_letters=self._checklist_to_json(payload.recommendation_letters),
            test_requirements=self._checklist_to_json(payload.test_requirements),
            submitted_at=payload.submitted_at,
            outcome_notes=payload.outcome_notes,
        )
        self.repository.add(saved)
        try:
            self.session.commit()
            self.session.refresh(saved)
            return self.to_response(saved)
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "opportunity_already_saved",
                "This opportunity is already saved in your tracker",
            ) from exc

    def list_for_user(
        self, user: User, *, status_filter: ApplicationStatus | None = None
    ) -> list[SavedOpportunityResponse]:
        return [
            self.to_response(saved)
            for saved in self.repository.list_for_user(user.id, status=status_filter)
        ]

    def get(self, saved_opportunity_id: uuid.UUID, *, user: User) -> SavedOpportunityResponse:
        saved = self.repository.get_for_user(saved_opportunity_id, user.id)
        if saved is None:
            raise AppError("saved_opportunity_not_found", "Saved opportunity was not found", 404)
        return self.to_response(saved)

    def update(
        self, saved_opportunity_id: uuid.UUID, payload: SavedOpportunityUpdate, *, user: User
    ) -> SavedOpportunityResponse:
        saved = self.repository.get_for_user(saved_opportunity_id, user.id)
        if saved is None:
            raise AppError("saved_opportunity_not_found", "Saved opportunity was not found", 404)

        changes = payload.model_dump(exclude_unset=True)
        next_status = changes.get("status", saved.status)
        next_submitted_at = changes.get("submitted_at", saved.submitted_at)
        if next_submitted_at is not None and next_status in self._pre_submission_statuses():
            raise AppError(
                "invalid_application_state",
                "submitted_at requires status to be submitted or later",
            )

        for field, value in changes.items():
            if field in {"document_checklist", "recommendation_letters", "test_requirements"}:
                setattr(saved, field, self._checklist_to_json(value))
            else:
                setattr(saved, field, value)

        self.session.commit()
        self.session.refresh(saved)
        return self.to_response(saved)

    def delete(self, saved_opportunity_id: uuid.UUID, *, user: User) -> None:
        saved = self.repository.get_for_user(saved_opportunity_id, user.id)
        if saved is None:
            raise AppError("saved_opportunity_not_found", "Saved opportunity was not found", 404)
        self.repository.delete(saved)
        self.session.commit()

    def to_response(self, saved: SavedOpportunity) -> SavedOpportunityResponse:
        return SavedOpportunityResponse(
            id=saved.id,
            status=saved.status,
            personal_notes=saved.personal_notes,
            personal_deadline=saved.personal_deadline,
            document_checklist=[
                ChecklistItem.model_validate(item) for item in saved.document_checklist
            ],
            recommendation_letters=[
                ChecklistItem.model_validate(item) for item in saved.recommendation_letters
            ],
            test_requirements=[
                ChecklistItem.model_validate(item) for item in saved.test_requirements
            ],
            submitted_at=saved.submitted_at,
            outcome_notes=saved.outcome_notes,
            created_at=saved.created_at,
            updated_at=saved.updated_at,
            opportunity=self.opportunity_service.to_summary_response(saved.opportunity),
        )

    def _get_public_verified_opportunity(self, opportunity_id: uuid.UUID) -> Opportunity:
        opportunity = self.opportunities.get_opportunity(opportunity_id)
        if opportunity is None or opportunity.status is not OpportunityStatus.ACTIVE:
            raise AppError(
                "opportunity_not_available",
                "Only active officially verified opportunities can be saved",
                status.HTTP_404_NOT_FOUND,
            )

        has_verified_official_source = any(
            source.source_type is SourceType.OFFICIAL
            and source.verification_status is VerificationStatus.OFFICIALLY_VERIFIED
            for source in opportunity.sources
        )
        if not has_verified_official_source:
            raise AppError(
                "opportunity_not_available",
                "Only active officially verified opportunities can be saved",
                status.HTTP_404_NOT_FOUND,
            )
        return opportunity

    @staticmethod
    def _checklist_to_json(
        items: list[ChecklistItem] | list[dict[str, object]] | None,
    ) -> list[dict[str, object]]:
        if items is None:
            return []
        return [item.model_dump() if isinstance(item, ChecklistItem) else item for item in items]

    @staticmethod
    def _pre_submission_statuses() -> set[ApplicationStatus]:
        return {
            ApplicationStatus.INTERESTED,
            ApplicationStatus.RESEARCHING,
            ApplicationStatus.PREPARING_DOCUMENTS,
            ApplicationStatus.WAITING_FOR_RECOMMENDATION,
            ApplicationStatus.READY_TO_APPLY,
        }
