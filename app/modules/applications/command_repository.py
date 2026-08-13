from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationReminder,
    ApplicationTask,
    ReminderStatus,
    TaskStatus,
)
from app.modules.opportunities.models import Opportunity


class ApplicationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _detail_options():
        return (
            joinedload(Application.opportunity).joinedload(Opportunity.provider),
            joinedload(Application.opportunity).joinedload(Opportunity.university),
            joinedload(Application.opportunity).selectinload(Opportunity.sources),
            joinedload(Application.opportunity).selectinload(Opportunity.cycles),
            selectinload(Application.tasks),
            selectinload(Application.reminders),
            selectinload(Application.documents),
        )

    def get(self, application_id: uuid.UUID, user_id: uuid.UUID) -> Application | None:
        return self.session.scalar(
            select(Application)
            .where(
                Application.id == application_id,
                Application.user_id == user_id,
            )
            .options(*self._detail_options())
        )

    def get_by_opportunity(
        self, opportunity_id: uuid.UUID, user_id: uuid.UUID
    ) -> Application | None:
        return self.session.scalar(
            select(Application)
            .where(
                Application.opportunity_id == opportunity_id,
                Application.user_id == user_id,
            )
            .options(*self._detail_options())
        )

    def list(self, user_id: uuid.UUID, *, limit: int, offset: int) -> tuple[list[Application], int]:
        base = select(Application).where(Application.user_id == user_id)
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        items = (
            self.session.scalars(
                base.options(*self._detail_options())
                .order_by(
                    Application.personal_deadline.asc().nulls_last(),
                    Application.updated_at.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
            .unique()
            .all()
        )
        return items, total

    def tasks_for_dashboard(
        self, user_id: uuid.UUID, statuses: tuple[TaskStatus, ...]
    ) -> list[ApplicationTask]:
        return self.session.scalars(
            select(ApplicationTask)
            .join(Application)
            .where(
                Application.user_id == user_id,
                ApplicationTask.status.in_(statuses),
            )
            .order_by(
                ApplicationTask.due_at.asc().nulls_last(),
                ApplicationTask.priority.desc(),
            )
        ).all()

    def reminders_for_dashboard(self, user_id: uuid.UUID) -> list[ApplicationReminder]:
        return self.session.scalars(
            select(ApplicationReminder)
            .join(Application)
            .where(
                Application.user_id == user_id,
                ApplicationReminder.status.in_((ReminderStatus.SCHEDULED, ReminderStatus.SNOOZED)),
            )
            .order_by(ApplicationReminder.scheduled_at)
            .limit(20)
        ).all()

    def add_event(
        self,
        application_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        event_type: str,
        metadata: dict[str, object],
    ) -> ApplicationEvent:
        event = ApplicationEvent(
            application_id=application_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            metadata_json=metadata,
        )
        self.session.add(event)
        return event

    def events(
        self,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[ApplicationEvent], int]:
        owner = select(Application.id).where(
            Application.id == application_id, Application.user_id == user_id
        )
        base = select(ApplicationEvent).where(ApplicationEvent.application_id.in_(owner))
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        return self.session.scalars(
            base.order_by(ApplicationEvent.created_at.desc()).limit(limit).offset(offset)
        ).all(), total

    def get_task(
        self, application_id: uuid.UUID, task_id: uuid.UUID, user_id: uuid.UUID
    ) -> ApplicationTask | None:
        return self.session.scalar(
            select(ApplicationTask)
            .join(Application)
            .where(
                ApplicationTask.id == task_id,
                ApplicationTask.application_id == application_id,
                Application.user_id == user_id,
            )
        )

    def get_reminder(
        self,
        application_id: uuid.UUID,
        reminder_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ApplicationReminder | None:
        return self.session.scalar(
            select(ApplicationReminder)
            .join(Application)
            .where(
                ApplicationReminder.id == reminder_id,
                ApplicationReminder.application_id == application_id,
                Application.user_id == user_id,
            )
        )

    def get_document(
        self,
        application_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ApplicationDocument | None:
        return self.session.scalar(
            select(ApplicationDocument)
            .join(Application)
            .where(
                ApplicationDocument.id == document_id,
                ApplicationDocument.application_id == application_id,
                Application.user_id == user_id,
            )
        )
