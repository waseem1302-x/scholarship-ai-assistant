import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentUser
from app.modules.matching.exporter import StudentStrategyReport, build_match_strategy_report
from app.modules.matching.guest_matcher import (
    GuestMatchRequest,
    GuestMatchResponse,
    evaluate_guest_matches,
)
from app.modules.matching.schemas import MatchListResponse
from app.modules.matching.service import MatchingService
from app.modules.opportunities.calendar import (
    DeadlineMilestone,
    OpportunityTimelineResponse,
    generate_google_calendar_url,
)
from app.modules.opportunities.evidence_models import ScopedDeadline
from app.modules.opportunities.materialization_models import OpportunityEvent
from app.modules.opportunities.models import Opportunity, OpportunityCycle
from app.modules.opportunities.repository import OpportunityRepository
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.profiles.strength import (
    ProfileStrengthResponse,
    evaluate_profile_strength,
)

router = APIRouter(prefix="/matches", tags=["matching"])

AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication is required.",
}
PROFILE_REQUIRED_RESPONSE = {
    "model": ErrorResponse,
    "description": "A student profile is required before matching.",
}


def get_matching_service(
    session: Annotated[Session, Depends(get_db)],
) -> MatchingService:
    return MatchingService(
        StudentProfileRepository(session),
        OpportunityRepository(session),
    )


@router.post(
    "/quick",
    response_model=GuestMatchResponse,
    summary="Anonymous top-of-funnel quick matching for website visitors",
)
def quick_match(
    request: GuestMatchRequest,
    session: Annotated[Session, Depends(get_db)],
) -> GuestMatchResponse:
    return evaluate_guest_matches(session, request)


@router.get(
    "/profile/strength",
    response_model=ProfileStrengthResponse,
    responses={400: PROFILE_REQUIRED_RESPONSE, 401: AUTHENTICATION_RESPONSE},
    summary="Calculate profile strength score and dynamic scholarship unlock tips",
)
def get_my_profile_strength(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
) -> ProfileStrengthResponse:
    profile_repo = StudentProfileRepository(session)
    profile = profile_repo.get_by_user_id(user.id)
    if profile is None:
        raise HTTPException(
            status_code=400, detail="A student profile is required before evaluating strength."
        )
    return evaluate_profile_strength(profile)


@router.get(
    "/me",
    response_model=MatchListResponse,
    responses={400: PROFILE_REQUIRED_RESPONSE, 401: AUTHENTICATION_RESPONSE},
)
def match_my_profile(
    user: CurrentUser,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> MatchListResponse:
    return service.match_for_user(user.id)


@router.delete(
    "/me/evaluations/{evaluation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: AUTHENTICATION_RESPONSE, 404: {"model": ErrorResponse}},
)
def delete_my_match_evaluation(
    evaluation_id: uuid.UUID,
    user: CurrentUser,
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> Response:
    service.delete_evaluation(evaluation_id, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me/report",
    response_model=StudentStrategyReport,
    responses={400: PROFILE_REQUIRED_RESPONSE, 401: AUTHENTICATION_RESPONSE},
    summary="Generate personalized downloadable scholarship strategy & match report",
)
def get_my_match_strategy_report(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> StudentStrategyReport:
    profile_repo = StudentProfileRepository(session)
    profile = profile_repo.get_by_user_id(user.id)
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="A student profile is required before generating a strategy report.",
        )

    match_result = service.match_for_user(user.id)
    return build_match_strategy_report(profile, match_result.items)


@router.get(
    "/me/timeline",
    response_model=list[OpportunityTimelineResponse],
    responses={400: PROFILE_REQUIRED_RESPONSE, 401: AUTHENTICATION_RESPONSE},
    summary="Get visual deadline radar timeline for student matched scholarships",
)
def get_my_match_timeline(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_db)],
    service: Annotated[MatchingService, Depends(get_matching_service)],
) -> list[OpportunityTimelineResponse]:
    match_result = service.match_for_user(user.id)
    timelines: list[OpportunityTimelineResponse] = []
    now = datetime.now(UTC)

    for item in match_result.items:
        opp_id = item.opportunity.id
        opp = session.scalar(select(Opportunity).where(Opportunity.id == opp_id))
        if opp is None:
            continue

        cycle = session.scalar(
            select(OpportunityCycle).where(OpportunityCycle.opportunity_id == opp_id)
        )
        deadlines = list(
            session.scalars(select(ScopedDeadline).where(ScopedDeadline.scholarship_id == opp_id))
        )
        events = list(
            session.scalars(
                select(OpportunityEvent).where(OpportunityEvent.scholarship_id == opp_id)
            )
        )

        milestones: list[DeadlineMilestone] = []

        # 1. Main Application Deadline
        deadline_dt = cycle.application_deadline if cycle else None
        if not deadline_dt and deadlines:
            for d in deadlines:
                if d.deadline_at:
                    deadline_dt = d.deadline_at
                    break

        if deadline_dt:
            deadline_utc = (
                deadline_dt.astimezone(UTC)
                if deadline_dt.tzinfo
                else deadline_dt.replace(tzinfo=UTC)
            )
            diff_days = int((deadline_utc - now).days)
            urgency = (
                "critical"
                if diff_days <= 3
                else ("soon" if diff_days <= 14 else ("upcoming" if diff_days > 0 else "closed"))
            )
            milestones.append(
                DeadlineMilestone(
                    title="Application Submission Deadline",
                    date_iso=deadline_utc.isoformat(),
                    days_remaining=diff_days,
                    milestone_type="application_deadline",
                    urgency_badge=urgency,
                    notes=f"Closing time: {deadline_utc.strftime('%H:%M UTC')}",
                )
            )

        # 2. Supplementary Events
        for ev in events:
            if ev.starts_at:
                ev_utc = (
                    ev.starts_at.astimezone(UTC)
                    if ev.starts_at.tzinfo
                    else ev.starts_at.replace(tzinfo=UTC)
                )
                diff_days = int((ev_utc - now).days)
                urgency = (
                    "critical"
                    if diff_days <= 3
                    else (
                        "soon" if diff_days <= 14 else ("upcoming" if diff_days > 0 else "closed")
                    )
                )
                milestones.append(
                    DeadlineMilestone(
                        title=ev.label or ev.event_type.title(),
                        date_iso=ev_utc.isoformat(),
                        days_remaining=diff_days,
                        milestone_type=ev.event_type,
                        urgency_badge=urgency,
                        notes=ev.notes,
                    )
                )

        target_dt = deadline_dt or now
        google_url = generate_google_calendar_url(
            title=f"DEADLINE: {opp.name}",
            start_dt=target_dt,
            end_dt=target_dt,
            details=f"Application deadline for {opp.name} ({opp.country}).",
            location=opp.country or "International",
        )

        timelines.append(
            OpportunityTimelineResponse(
                opportunity_id=str(opp.id),
                opportunity_name=opp.name,
                country=opp.country or "International",
                intake_year=opp.intake_year,
                milestones=milestones,
                status=opp.status.value,
                google_calendar_url=google_url,
            )
        )

    return timelines
