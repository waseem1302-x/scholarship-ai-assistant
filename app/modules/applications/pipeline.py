"""Application Kanban Pipeline Tracker for organizing multi-scholarship workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel

from app.modules.applications.models import Application, ApplicationLifecycle, ApplicationStatus
from app.modules.opportunities.models import Opportunity


class KanbanLaneName(StrEnum):
    SAVED = "saved"
    PREPARING = "preparing"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    INTERVIEW = "interview"
    DECISION_RECEIVED = "decision_received"


class PipelineCard(BaseModel):
    application_id: str
    opportunity_id: str
    opportunity_name: str
    country: str
    degree_level: str
    funding_type: str
    lane: KanbanLaneName
    status: str
    deadline_iso: str | None
    days_remaining: int | None
    urgency_color: str  # "emerald", "amber", "rose", "gray"
    tasks_completed: int
    tasks_total: int


class PipelineLaneSummary(BaseModel):
    lane: KanbanLaneName
    lane_title: str
    count: int
    cards: list[PipelineCard]


class PipelineSummaryResponse(BaseModel):
    total_active_applications: int
    urgent_deadlines_count: int
    lanes: list[PipelineLaneSummary]


def _map_lifecycle_to_lane(
    lifecycle: ApplicationLifecycle | None, status: ApplicationStatus | None
) -> KanbanLaneName:
    if status == ApplicationStatus.INTERVIEW_STAGE:
        return KanbanLaneName.INTERVIEW
    if status in (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED):
        return KanbanLaneName.DECISION_RECEIVED
    if status == ApplicationStatus.SUBMITTED or lifecycle == ApplicationLifecycle.SUBMITTED:
        return KanbanLaneName.SUBMITTED
    if (
        status == ApplicationStatus.READY_TO_APPLY
        or lifecycle == ApplicationLifecycle.READY_TO_SUBMIT
    ):
        return KanbanLaneName.READY_TO_SUBMIT
    if (
        status
        in (ApplicationStatus.PREPARING_DOCUMENTS, ApplicationStatus.WAITING_FOR_RECOMMENDATION)
        or lifecycle == ApplicationLifecycle.PREPARING
    ):
        return KanbanLaneName.PREPARING
    return KanbanLaneName.SAVED


def build_pipeline_summary(
    applications_data: list[tuple[Application, Opportunity, int, int]],
    *,
    reference_dt: datetime | None = None,
) -> PipelineSummaryResponse:
    """Group student applications into interactive Kanban pipeline lanes."""
    now = reference_dt or datetime.now(UTC)

    lane_cards: dict[KanbanLaneName, list[PipelineCard]] = {lane: [] for lane in KanbanLaneName}

    urgent_count = 0

    for app, opp, done_tasks, total_tasks in applications_data:
        app_status = getattr(app, "status", None)
        app_lifecycle = getattr(app, "lifecycle", None)
        lane = _map_lifecycle_to_lane(app_lifecycle, app_status)

        # Calculate deadline urgency
        deadline_iso = None
        days_left = None
        urgency = "gray"

        if opp.application_deadline:
            dl_utc = (
                opp.application_deadline.astimezone(UTC)
                if opp.application_deadline.tzinfo
                else opp.application_deadline.replace(tzinfo=UTC)
            )
            deadline_iso = dl_utc.isoformat()
            days_left = int((dl_utc - now).total_seconds() / 86400)

            if days_left < 0:
                urgency = "gray"
            elif days_left <= 7:
                urgency = "rose"
                urgent_count += 1
            elif days_left <= 21:
                urgency = "amber"
            else:
                urgency = "emerald"

        display_status = (
            app_status.value if app_status else (app_lifecycle.value if app_lifecycle else "saved")
        )

        card = PipelineCard(
            application_id=str(app.id),
            opportunity_id=str(opp.id),
            opportunity_name=opp.name,
            country=opp.country or "International",
            degree_level=opp.degree_level.value.upper(),
            funding_type=opp.funding_type.value.upper(),
            lane=lane,
            status=display_status,
            deadline_iso=deadline_iso,
            days_remaining=days_left,
            urgency_color=urgency,
            tasks_completed=done_tasks,
            tasks_total=total_tasks,
        )
        lane_cards[lane].append(card)

    lane_titles = {
        KanbanLaneName.SAVED: "Shortlisted / Saved",
        KanbanLaneName.PREPARING: "Preparing Documents",
        KanbanLaneName.READY_TO_SUBMIT: "Ready to Submit",
        KanbanLaneName.SUBMITTED: "Submitted",
        KanbanLaneName.INTERVIEW: "Interview Stage",
        KanbanLaneName.DECISION_RECEIVED: "Decisions & Offers",
    }

    lane_summaries = [
        PipelineLaneSummary(
            lane=lane,
            lane_title=lane_titles[lane],
            count=len(lane_cards[lane]),
            cards=lane_cards[lane],
        )
        for lane in KanbanLaneName
    ]

    return PipelineSummaryResponse(
        total_active_applications=len(applications_data),
        urgent_deadlines_count=urgent_count,
        lanes=lane_summaries,
    )
