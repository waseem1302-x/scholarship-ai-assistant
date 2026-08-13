from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError
from app.modules.applications.command_repository import ApplicationRepository
from app.modules.applications.deadlines import urgency_for_deadline
from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationLifecycle,
    ApplicationNotificationPreference,
    ApplicationReminder,
    ApplicationTask,
    DeadlineState,
    ReminderStatus,
    ReminderWorkerHealth,
    SavedOpportunity,
    TaskCategory,
    TaskPriority,
    TaskStatus,
)
from app.modules.applications.schemas import (
    ApplicationCreate,
    ApplicationDocumentCreate,
    ApplicationDocumentResponse,
    ApplicationDocumentUpdate,
    ApplicationEventResponse,
    ApplicationNotificationPreferenceResponse,
    ApplicationNotificationPreferenceUpdate,
    ApplicationOperationalReportResponse,
    ApplicationReminderCreate,
    ApplicationReminderResponse,
    ApplicationReminderUpdate,
    ApplicationResponse,
    ApplicationTaskCreate,
    ApplicationTaskResponse,
    ApplicationTaskUpdate,
    ApplicationUpdate,
    CommandCentreResponse,
    ReminderWorkerHealthResponse,
)
from app.modules.auth.models import User, utc_now
from app.modules.matching.models import (
    MatchEvaluation,
    MatchEvaluationResult,
    MatchRuleOutcome,
)
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.lifecycle import effective_application_window
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    Source,
)
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.opportunities.service import OpportunityService


class ApplicationCommandService:
    def __init__(self, session: Session, *, now: datetime | None = None) -> None:
        self.session = session
        self.now = now
        self.repository = ApplicationRepository(session)
        self.opportunities = OpportunityRepository(session)
        self.opportunity_service = OpportunityService(session)

    def create(self, payload: ApplicationCreate, *, user: User) -> ApplicationResponse:
        if self.repository.get_by_opportunity(payload.opportunity_id, user.id):
            raise ConflictError(
                "application_already_exists",
                "An application already exists for this opportunity",
            )
        opportunity = self._verified_opportunity(payload.opportunity_id)
        saved = (
            self.session.query(SavedOpportunity)
            .filter_by(user_id=user.id, opportunity_id=opportunity.id)
            .one_or_none()
        )
        source = self._official_source(opportunity)
        official_deadline, official_timezone = self._official_deadline_context(opportunity, source)
        application = Application(
            user_id=user.id,
            opportunity_id=opportunity.id,
            saved_opportunity_id=saved.id if saved else None,
            lifecycle=self._legacy_lifecycle(saved.status) if saved else ApplicationLifecycle.SAVED,
            official_deadline=official_deadline,
            official_deadline_state=DeadlineState.KNOWN
            if official_deadline and source
            else DeadlineState.UNCERTAIN,
            official_deadline_source_id=source.id if source else None,
            official_deadline_verified_at=source.last_verified_at if source else None,
            personal_deadline=payload.personal_deadline
            if payload.personal_deadline is not None
            else (saved.personal_deadline if saved else None),
            official_deadline_timezone=official_timezone,
            personal_deadline_timezone=payload.personal_deadline_timezone,
            notes=saved.personal_notes if saved else None,
            submitted_at=saved.submitted_at if saved else None,
            decision_notes=saved.outcome_notes if saved else None,
        )
        self.session.add(application)
        self.session.flush()
        self.repository.add_event(
            application.id,
            user.id,
            "application.created",
            {"opportunity_id": str(opportunity.id)},
        )
        self._generate_starter_tasks(application, opportunity, source)
        self.session.commit()
        self.session.refresh(application)
        return self.to_response(self.repository.get(application.id, user.id) or application)

    def list(self, user: User, *, limit: int, offset: int) -> tuple[list[ApplicationResponse], int]:
        records, total = self.repository.list(user.id, limit=limit, offset=offset)
        self._sync_deadlines(records, user)
        return [self.to_response(item) for item in records], total

    def get(self, application_id: uuid.UUID, *, user: User) -> ApplicationResponse:
        application = self._application(application_id, user)
        self._sync_deadlines([application], user)
        return self.to_response(application)

    def update(
        self,
        application_id: uuid.UUID,
        payload: ApplicationUpdate,
        *,
        user: User,
    ) -> ApplicationResponse:
        application = self._application(application_id, user)
        values = payload.model_dump(exclude_unset=True)
        expected = values.pop("expected_version", None)
        if expected is not None and expected != application.version:
            raise ConflictError(
                "application_version_conflict",
                "This application was updated elsewhere; refresh and try again",
            )
        lifecycle = values.get("lifecycle")
        if lifecycle is not None and lifecycle != application.lifecycle:
            previous_lifecycle = application.lifecycle
            self._validate_transition(previous_lifecycle, lifecycle)
            application.lifecycle = lifecycle
            if lifecycle is ApplicationLifecycle.SUBMITTED and application.submitted_at is None:
                application.submitted_at = self._current_time()
            self.repository.add_event(
                application.id,
                user.id,
                "application.lifecycle_changed",
                {"from": str(previous_lifecycle), "to": str(lifecycle)},
            )
        for field, value in values.items():
            if field != "lifecycle":
                setattr(application, field, value)
        application.version += 1
        self.repository.add_event(
            application.id,
            user.id,
            "application.updated",
            {"fields": sorted(values)},
        )
        self.session.commit()
        self.session.refresh(application)
        return self.to_response(self.repository.get(application.id, user.id) or application)

    def delete(self, application_id: uuid.UUID, *, user: User) -> None:
        application = self._application(application_id, user)
        self.session.delete(application)
        self.session.commit()

    def delete_all_application_data(self, *, user: User) -> None:
        """Delete the normalized workspace and the legacy tracker it supersedes."""
        applications, _ = self.repository.list(user.id, limit=500, offset=0)
        for application in applications:
            self.session.delete(application)
        for item in self.session.query(SavedOpportunity).filter_by(user_id=user.id).all():
            self.session.delete(item)
        self.session.commit()

    def notification_preference(self, *, user: User) -> ApplicationNotificationPreferenceResponse:
        preference = self.session.get(ApplicationNotificationPreference, user.id)
        if preference is None:
            preference = ApplicationNotificationPreference(user_id=user.id)
            self.session.add(preference)
            self.session.commit()
            self.session.refresh(preference)
        return ApplicationNotificationPreferenceResponse.model_validate(preference)

    def update_notification_preference(
        self, payload: ApplicationNotificationPreferenceUpdate, *, user: User
    ) -> ApplicationNotificationPreferenceResponse:
        preference = self.session.get(ApplicationNotificationPreference, user.id)
        if preference is None:
            preference = ApplicationNotificationPreference(user_id=user.id)
            self.session.add(preference)
        preference.in_app_enabled = payload.in_app_enabled
        if not payload.in_app_enabled:
            reminders = self.session.scalars(
                select(ApplicationReminder)
                .join(Application)
                .where(
                    Application.user_id == user.id,
                    ApplicationReminder.status.in_(
                        (ReminderStatus.SCHEDULED, ReminderStatus.SNOOZED)
                    ),
                )
            ).all()
            for reminder in reminders:
                reminder.status = ReminderStatus.CANCELLED
        self.session.commit()
        self.session.refresh(preference)
        return ApplicationNotificationPreferenceResponse.model_validate(preference)

    def reminder_worker_health(self) -> ReminderWorkerHealthResponse:
        record = self.session.get(ReminderWorkerHealth, "default")
        if record is None:
            return ReminderWorkerHealthResponse(
                last_started_at=None,
                last_completed_at=None,
                processed_count=0,
                failed_count=0,
                is_healthy=False,
            )
        return ReminderWorkerHealthResponse(
            last_started_at=record.last_started_at,
            last_completed_at=record.last_completed_at,
            processed_count=record.processed_count,
            failed_count=record.failed_count,
            is_healthy=record.last_completed_at is not None
            and self._as_utc(record.last_completed_at)
            >= self._as_utc(self._current_time()) - timedelta(minutes=5),
        )

    def create_task(
        self,
        application_id: uuid.UUID,
        payload: ApplicationTaskCreate,
        *,
        user: User,
    ) -> ApplicationTaskResponse:
        application = self._application(application_id, user)
        self._validate_evidence(
            application.opportunity_id,
            payload.source_id,
            payload.source_excerpt_id,
        )
        task = ApplicationTask(application_id=application.id, **payload.model_dump())
        self.session.add(task)
        try:
            self.session.flush()
            self.repository.add_event(
                application.id,
                user.id,
                "task.created",
                {"task_id": str(task.id), "category": str(task.category)},
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "duplicate_application_task",
                "An active task with this category and title already exists for the application",
            ) from exc
        self.session.refresh(task)
        return ApplicationTaskResponse.model_validate(task)

    def update_task(
        self,
        application_id: uuid.UUID,
        task_id: uuid.UUID,
        payload: ApplicationTaskUpdate,
        *,
        user: User,
    ) -> ApplicationTaskResponse:
        task = self.repository.get_task(application_id, task_id, user.id)
        if task is None:
            raise self._not_found("task")
        values = payload.model_dump(exclude_unset=True)
        application = self._application(application_id, user)
        self._validate_evidence(
            application.opportunity_id,
            values.get("source_id", task.source_id),
            values.get("source_excerpt_id", task.source_excerpt_id),
        )
        if values.get("status") is TaskStatus.COMPLETED:
            task.completed_at = self._current_time()
        elif "status" in values and values["status"] is not TaskStatus.COMPLETED:
            task.completed_at = None
        for field, value in values.items():
            setattr(task, field, value)
        self.repository.add_event(
            application_id,
            user.id,
            "task.updated",
            {"task_id": str(task.id), "fields": sorted(values)},
        )
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "duplicate_application_task",
                "An active task with this category and title already exists for the application",
            ) from exc
        self.session.refresh(task)
        return ApplicationTaskResponse.model_validate(task)

    def delete_task(self, application_id: uuid.UUID, task_id: uuid.UUID, *, user: User) -> None:
        task = self.repository.get_task(application_id, task_id, user.id)
        if task is None:
            raise self._not_found("task")
        self.repository.add_event(
            application_id, user.id, "task.deleted", {"task_id": str(task.id)}
        )
        self.session.delete(task)
        self.session.commit()

    def create_reminder(
        self,
        application_id: uuid.UUID,
        payload: ApplicationReminderCreate,
        *,
        user: User,
    ) -> ApplicationReminderResponse:
        application = self._application(application_id, user)
        if payload.task_id and not self.repository.get_task(
            application_id, payload.task_id, user.id
        ):
            raise self._not_found("task")
        key = payload.idempotency_key or self._reminder_key(
            application_id,
            payload.task_id,
            payload.scheduled_at,
            payload.message,
        )
        existing = (
            self.session.query(ApplicationReminder).filter_by(idempotency_key=key).one_or_none()
        )
        if existing:
            return ApplicationReminderResponse.model_validate(existing)
        reminder = ApplicationReminder(
            application_id=application.id,
            idempotency_key=key,
            **payload.model_dump(exclude={"idempotency_key"}),
        )
        self.session.add(reminder)
        self.session.flush()
        self.repository.add_event(
            application.id,
            user.id,
            "reminder.created",
            {"reminder_id": str(reminder.id)},
        )
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.query(ApplicationReminder).filter_by(idempotency_key=key).one()
            return ApplicationReminderResponse.model_validate(existing)
        self.session.refresh(reminder)
        return ApplicationReminderResponse.model_validate(reminder)

    def update_reminder(
        self,
        application_id: uuid.UUID,
        reminder_id: uuid.UUID,
        payload: ApplicationReminderUpdate,
        *,
        user: User,
    ) -> ApplicationReminderResponse:
        reminder = self.repository.get_reminder(application_id, reminder_id, user.id)
        if reminder is None:
            raise self._not_found("reminder")
        values = payload.model_dump(exclude_unset=True)
        status = values.get("status")
        if status is ReminderStatus.READ:
            reminder.read_at = self._current_time()
        if status is ReminderStatus.SCHEDULED:
            reminder.delivered_at = None
            reminder.read_at = None
        for field, value in values.items():
            setattr(reminder, field, value)
        self.repository.add_event(
            application_id,
            user.id,
            "reminder.updated",
            {"reminder_id": str(reminder.id), "fields": sorted(values)},
        )
        self.session.commit()
        self.session.refresh(reminder)
        return ApplicationReminderResponse.model_validate(reminder)

    def create_document(
        self,
        application_id: uuid.UUID,
        payload: ApplicationDocumentCreate,
        *,
        user: User,
    ) -> ApplicationDocumentResponse:
        application = self._application(application_id, user)
        if payload.task_id and not self.repository.get_task(
            application_id, payload.task_id, user.id
        ):
            raise self._not_found("task")
        document = ApplicationDocument(application_id=application.id, **payload.model_dump())
        self.session.add(document)
        self.session.flush()
        self.repository.add_event(
            application.id,
            user.id,
            "document.created",
            {"document_id": str(document.id)},
        )
        self.session.commit()
        self.session.refresh(document)
        return ApplicationDocumentResponse.model_validate(document)

    def update_document(
        self,
        application_id: uuid.UUID,
        document_id: uuid.UUID,
        payload: ApplicationDocumentUpdate,
        *,
        user: User,
    ) -> ApplicationDocumentResponse:
        document = self.repository.get_document(application_id, document_id, user.id)
        if document is None:
            raise self._not_found("document")
        values = payload.model_dump(exclude_unset=True)
        if values.get("task_id") and not self.repository.get_task(
            application_id, values["task_id"], user.id
        ):
            raise self._not_found("task")
        for field, value in values.items():
            setattr(document, field, value)
        self.repository.add_event(
            application_id,
            user.id,
            "document.updated",
            {"document_id": str(document.id), "fields": sorted(values)},
        )
        self.session.commit()
        self.session.refresh(document)
        return ApplicationDocumentResponse.model_validate(document)

    def dashboard(self, user: User) -> CommandCentreResponse:
        applications, _ = self.repository.list(user.id, limit=100, offset=0)
        self._sync_deadlines(applications, user)
        now = self._as_utc(self._current_time())
        soon = now + timedelta(days=14)
        tasks = self.repository.tasks_for_dashboard(
            user.id,
            (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED),
        )
        urgent = [
            task
            for task in tasks
            if task.due_at
            and self._as_utc(task.due_at) <= soon
            and task.status is not TaskStatus.BLOCKED
        ]
        blocked = [task for task in tasks if task.status is TaskStatus.BLOCKED]
        return CommandCentreResponse(
            urgent_tasks=[ApplicationTaskResponse.model_validate(task) for task in urgent[:20]],
            blocked_tasks=[ApplicationTaskResponse.model_validate(task) for task in blocked[:20]],
            blocked_applications=[
                self.to_response(item)
                for item in applications
                if any(task.status is TaskStatus.BLOCKED for task in item.tasks)
            ][:20],
            approaching_deadlines=[
                self.to_response(item)
                for item in applications
                if item.official_deadline and self._as_utc(item.official_deadline) <= soon
            ][:20],
            submitted_applications=[
                self.to_response(item)
                for item in applications
                if item.lifecycle
                in {
                    ApplicationLifecycle.SUBMITTED,
                    ApplicationLifecycle.DECISION_RECEIVED,
                    ApplicationLifecycle.ACCEPTED,
                    ApplicationLifecycle.DECLINED,
                }
            ][:20],
            upcoming_reminders=[
                ApplicationReminderResponse.model_validate(item)
                for item in self.repository.reminders_for_dashboard(user.id)
            ],
            recently_changed_opportunities=[
                self.to_response(item)
                for item in applications
                if item.official_deadline_state is not DeadlineState.KNOWN
            ][:20],
        )

    def operational_report(self) -> ApplicationOperationalReportResponse:
        """Return aggregate health counters without returning private student text."""
        now = self._as_utc(self._current_time())
        tasks = self.session.scalars(select(ApplicationTask)).all()
        reminders = self.session.scalars(select(ApplicationReminder)).all()
        open_statuses = {
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
        }
        open_tasks = [task for task in tasks if task.status in open_statuses]
        overdue = [task for task in open_tasks if task.due_at and self._as_utc(task.due_at) < now]
        delivered = sum(reminder.status is ReminderStatus.DELIVERED for reminder in reminders)
        failed = sum(reminder.status is ReminderStatus.FAILED for reminder in reminders)
        attempted = delivered + failed
        health = self.session.get(ReminderWorkerHealth, "default")
        return ApplicationOperationalReportResponse(
            generated_at=now,
            reminder_delivery_rate=round(delivered / attempted, 4) if attempted else None,
            reminders_delivered=delivered,
            reminders_failed=failed,
            overdue_open_tasks=len(overdue),
            open_tasks=len(open_tasks),
            task_completion_funnel={
                "total": len(tasks),
                "todo": sum(task.status is TaskStatus.TODO for task in tasks),
                "in_progress": sum(task.status is TaskStatus.IN_PROGRESS for task in tasks),
                "blocked": sum(task.status is TaskStatus.BLOCKED for task in tasks),
                "completed": sum(task.status is TaskStatus.COMPLETED for task in tasks),
                "dismissed": sum(task.status is TaskStatus.DISMISSED for task in tasks),
            },
            failure_counts={
                "failed_reminders": failed,
                "worker_failures": health.failed_count if health else 0,
            },
        )

    def events(
        self, application_id: uuid.UUID, *, user: User, limit: int, offset: int
    ) -> tuple[list[ApplicationEventResponse], int]:
        events, total = self.repository.events(application_id, user.id, limit=limit, offset=offset)
        return [ApplicationEventResponse.model_validate(event) for event in events], total

    def export(self, user: User) -> dict[str, object]:
        applications, _ = self.repository.list(user.id, limit=500, offset=0)
        result: list[dict[str, object]] = []
        for application in applications:
            events, _ = self.repository.events(application.id, user.id, limit=1000, offset=0)
            value = self.to_response(application).model_dump(mode="json")
            value["events"] = [
                ApplicationEventResponse.model_validate(event).model_dump(mode="json")
                for event in events
            ]
            result.append(value)
        return {
            "exported_at": self._current_time().isoformat(),
            "applications": result,
        }

    def to_response(self, application: Application) -> ApplicationResponse:
        return ApplicationResponse(
            id=application.id,
            lifecycle=application.lifecycle,
            official_deadline=application.official_deadline,
            official_deadline_timezone=application.official_deadline_timezone,
            official_deadline_state=application.official_deadline_state,
            official_deadline_source_id=application.official_deadline_source_id,
            official_deadline_excerpt_id=application.official_deadline_excerpt_id,
            official_deadline_verified_at=application.official_deadline_verified_at,
            personal_deadline=application.personal_deadline,
            personal_deadline_timezone=application.personal_deadline_timezone,
            deadline_urgency=urgency_for_deadline(
                application.official_deadline,
                deadline_changed=application.official_deadline_state is DeadlineState.CHANGED,
                deadline_uncertain=application.official_deadline_state is DeadlineState.UNCERTAIN,
                now=self._current_time(),
            ),
            notes=application.notes,
            submitted_at=application.submitted_at,
            decision_notes=application.decision_notes,
            version=application.version,
            created_at=application.created_at,
            updated_at=application.updated_at,
            opportunity=self.opportunity_service.to_private_application_summary_response(
                application.opportunity
            ),
            tasks=[ApplicationTaskResponse.model_validate(task) for task in application.tasks],
            reminders=[
                ApplicationReminderResponse.model_validate(reminder)
                for reminder in application.reminders
            ],
            documents=[
                ApplicationDocumentResponse.model_validate(document)
                for document in application.documents
            ],
        )

    def _application(self, application_id: uuid.UUID, user: User) -> Application:
        application = self.repository.get(application_id, user.id)
        if application is None:
            raise self._not_found("application")
        return application

    def _verified_opportunity(self, opportunity_id: uuid.UUID) -> Opportunity:
        opportunity = self.opportunities.get_opportunity(opportunity_id)
        if (
            not opportunity
            or opportunity.status is not OpportunityStatus.ACTIVE
            or not self._official_source(opportunity)
        ):
            raise AppError(
                "opportunity_not_available",
                "Only active, officially verified opportunities can be added",
                404,
            )
        return opportunity

    @staticmethod
    def _official_source(opportunity: Opportunity) -> Source | None:
        return EvidencePolicy.select_current_official_source(opportunity.sources)

    def _generate_starter_tasks(
        self,
        application: Application,
        opportunity: Opportunity,
        source: Source | None,
    ) -> None:
        generated: set[tuple[TaskCategory, str]] = set()

        def add_task(
            category: TaskCategory,
            title: str,
            priority: TaskPriority,
            *,
            source_id: uuid.UUID | None = None,
            source_excerpt_id: uuid.UUID | None = None,
        ) -> None:
            normalized_title = title.strip()
            key = (category, normalized_title.casefold())
            if not normalized_title or key in generated:
                return
            generated.add(key)
            self.session.add(
                ApplicationTask(
                    application_id=application.id,
                    category=category,
                    title=normalized_title,
                    priority=priority,
                    source_id=source_id
                    if source_id is not None
                    else (source.id if source else None),
                    source_excerpt_id=source_excerpt_id,
                    is_generated=True,
                )
            )

        for name in opportunity.required_documents:
            category = (
                TaskCategory.RECOMMENDATION
                if any(token in name.casefold() for token in ("recommend", "referee", "reference"))
                else TaskCategory.DOCUMENT
            )
            add_task(category, name, TaskPriority.NORMAL)
        if opportunity.english_language_requirement or opportunity.standardized_test_requirement:
            add_task(
                TaskCategory.TEST,
                "Confirm test requirement",
                TaskPriority.HIGH,
            )
        if opportunity.application_fee_info:
            add_task(
                TaskCategory.FUNDING,
                "Confirm application fee or waiver",
                TaskPriority.NORMAL,
            )
        if application.official_deadline_state is DeadlineState.UNCERTAIN:
            add_task(
                TaskCategory.OFFICIAL_VERIFICATION,
                "Verify official application deadline",
                TaskPriority.HIGH,
            )
        readiness_actions = self.session.scalars(
            select(MatchRuleOutcome)
            .join(MatchEvaluationResult)
            .join(MatchEvaluation)
            .where(
                MatchEvaluation.user_id == application.user_id,
                MatchEvaluationResult.opportunity_id == opportunity.id,
            )
            .order_by(MatchEvaluation.evaluated_at.desc())
        ).all()
        for outcome in readiness_actions:
            category = (
                TaskCategory.OFFICIAL_VERIFICATION
                if outcome.source_id or outcome.source_excerpt_id
                else TaskCategory.PERSONAL
            )
            for action in outcome.next_actions_json:
                add_task(
                    category,
                    action,
                    TaskPriority.NORMAL,
                    source_id=outcome.source_id,
                    source_excerpt_id=outcome.source_excerpt_id,
                )

    def _sync_deadlines(self, applications: list[Application], user: User) -> None:
        changed = False
        for application in applications:
            opportunity = application.opportunity
            source = self._official_source(opportunity)
            official_deadline, official_timezone = self._official_deadline_context(
                opportunity, source
            )
            state = DeadlineState.KNOWN if official_deadline and source else DeadlineState.UNCERTAIN
            if (
                application.official_deadline != official_deadline
                or application.official_deadline_state != state
                or application.official_deadline_timezone != official_timezone
            ):
                application.official_deadline_state = (
                    DeadlineState.UNCERTAIN
                    if state is DeadlineState.UNCERTAIN
                    else (
                        DeadlineState.CHANGED
                        if application.official_deadline and official_deadline
                        else DeadlineState.KNOWN
                    )
                )
                application.official_deadline = official_deadline
                application.official_deadline_timezone = official_timezone
                application.official_deadline_source_id = source.id if source else None
                application.official_deadline_verified_at = (
                    source.last_verified_at if source else None
                )
                self.repository.add_event(
                    application.id,
                    user.id,
                    "deadline.changed",
                    {"state": str(application.official_deadline_state)},
                )
                changed = True
        if changed:
            self.session.commit()

    def _official_deadline_context(
        self, opportunity: Opportunity, source: Source | None
    ) -> tuple[datetime | None, str]:
        cycle = effective_application_window(opportunity, source, now=self._current_time()).cycle
        if cycle is not None:
            return cycle.application_deadline, cycle.timezone
        return opportunity.application_deadline, "UTC"

    def _current_time(self) -> datetime:
        return self.now or utc_now()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @staticmethod
    def _legacy_lifecycle(status: object) -> ApplicationLifecycle:
        values = {
            "interested": "saved",
            "researching": "preparing",
            "preparing_documents": "preparing",
            "waiting_for_recommendation": "preparing",
            "ready_to_apply": "ready_to_submit",
            "submitted": "submitted",
            "interview_stage": "decision_received",
            "accepted": "accepted",
            "rejected": "declined",
            "withdrawn": "withdrawn",
            "expired": "withdrawn",
        }
        return ApplicationLifecycle(values[str(status)])

    @staticmethod
    def _validate_transition(current: ApplicationLifecycle, target: ApplicationLifecycle) -> None:
        allowed = {
            ApplicationLifecycle.SAVED: {
                ApplicationLifecycle.PREPARING,
                ApplicationLifecycle.WITHDRAWN,
            },
            ApplicationLifecycle.PREPARING: {
                ApplicationLifecycle.SAVED,
                ApplicationLifecycle.READY_TO_SUBMIT,
                ApplicationLifecycle.WITHDRAWN,
            },
            ApplicationLifecycle.READY_TO_SUBMIT: {
                ApplicationLifecycle.PREPARING,
                ApplicationLifecycle.SUBMITTED,
                ApplicationLifecycle.WITHDRAWN,
            },
            ApplicationLifecycle.SUBMITTED: {
                ApplicationLifecycle.DECISION_RECEIVED,
                ApplicationLifecycle.WITHDRAWN,
            },
            ApplicationLifecycle.DECISION_RECEIVED: {
                ApplicationLifecycle.ACCEPTED,
                ApplicationLifecycle.DECLINED,
                ApplicationLifecycle.WITHDRAWN,
            },
            ApplicationLifecycle.ACCEPTED: set(),
            ApplicationLifecycle.DECLINED: set(),
            ApplicationLifecycle.WITHDRAWN: set(),
        }
        if target not in allowed[current]:
            raise AppError(
                "invalid_application_transition",
                f"Cannot move from {current} to {target}",
            )

    def _validate_evidence(
        self,
        opportunity_id: uuid.UUID,
        source_id: uuid.UUID | None,
        source_excerpt_id: uuid.UUID | None,
    ) -> None:
        if (
            source_id
            and not self.session.query(Source)
            .filter_by(id=source_id, opportunity_id=opportunity_id)
            .one_or_none()
        ):
            raise AppError(
                "invalid_source_reference",
                "Source does not belong to this opportunity",
                422,
            )
        if source_excerpt_id:
            from app.modules.opportunities.models import SourceExcerpt

            excerpt = (
                self.session.query(SourceExcerpt).filter_by(id=source_excerpt_id).one_or_none()
            )
            if (
                not excerpt
                or not self.session.query(Source)
                .filter_by(id=excerpt.source_id, opportunity_id=opportunity_id)
                .one_or_none()
            ):
                raise AppError(
                    "invalid_source_reference",
                    "Excerpt does not belong to this opportunity",
                    422,
                )

    @staticmethod
    def _reminder_key(
        application_id: uuid.UUID,
        task_id: uuid.UUID | None,
        scheduled_at: datetime,
        message: str | None,
    ) -> str:
        return hashlib.sha256(
            f"{application_id}:{task_id}:{scheduled_at.isoformat()}:{message or ''}".encode()
        ).hexdigest()

    @staticmethod
    def _not_found(name: str) -> AppError:
        return AppError(f"{name}_not_found", f"{name.capitalize()} was not found", 404)
