import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.modules.applications.models import ApplicationStatus, SavedOpportunity
from app.modules.opportunities.models import Opportunity


class SavedOpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, saved_opportunity: SavedOpportunity) -> None:
        self.session.add(saved_opportunity)

    def get_for_user(
        self, saved_opportunity_id: uuid.UUID, user_id: uuid.UUID
    ) -> SavedOpportunity | None:
        return self.session.scalar(
            select(SavedOpportunity)
            .where(
                SavedOpportunity.id == saved_opportunity_id,
                SavedOpportunity.user_id == user_id,
            )
            .options(
                joinedload(SavedOpportunity.opportunity).joinedload(Opportunity.provider),
                joinedload(SavedOpportunity.opportunity).joinedload(Opportunity.university),
                joinedload(SavedOpportunity.opportunity).selectinload(Opportunity.sources),
            )
        )

    def get_by_user_and_opportunity(
        self, user_id: uuid.UUID, opportunity_id: uuid.UUID
    ) -> SavedOpportunity | None:
        return self.session.scalar(
            select(SavedOpportunity).where(
                SavedOpportunity.user_id == user_id,
                SavedOpportunity.opportunity_id == opportunity_id,
            )
        )

    def list_for_user(
        self, user_id: uuid.UUID, *, status: ApplicationStatus | None = None
    ) -> list[SavedOpportunity]:
        statement = (
            select(SavedOpportunity)
            .where(SavedOpportunity.user_id == user_id)
            .options(
                joinedload(SavedOpportunity.opportunity).joinedload(Opportunity.provider),
                joinedload(SavedOpportunity.opportunity).joinedload(Opportunity.university),
                joinedload(SavedOpportunity.opportunity).selectinload(Opportunity.sources),
            )
            .order_by(
                SavedOpportunity.personal_deadline.asc().nulls_last(),
                SavedOpportunity.updated_at.desc(),
            )
        )
        if status is not None:
            statement = statement.where(SavedOpportunity.status == status)
        return list(self.session.scalars(statement))

    def delete(self, saved_opportunity: SavedOpportunity) -> None:
        self.session.delete(saved_opportunity)
