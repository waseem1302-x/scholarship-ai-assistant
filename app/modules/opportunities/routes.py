import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorResponse
from app.db.session import get_db
from app.modules.auth.dependencies import require_admin_step_up, require_roles
from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.opportunity_publication_guard import (
    CatalogueAwareOpportunityService,
)
from app.modules.opportunities.calendar import (
    CalendarLinkResponse,
    generate_google_calendar_url,
    generate_opportunity_ics,
)
from app.modules.opportunities.checklist import (
    OpportunityChecklistResponse,
    build_opportunity_checklist,
)
from app.modules.opportunities.comparator import (
    ComparisonMatrixResponse,
    build_funding_comparison,
)
from app.modules.opportunities.cycle_rollover import CycleStateInfo, determine_cycle_state
from app.modules.opportunities.directory import (
    DirectoryScholarshipCard,
    PublicDirectoryResponse,
    _slugify,
    build_directory_card,
)
from app.modules.opportunities.evidence_models import (
    RequiredDocument,
    ScopedDeadline,
)
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.graph_schemas import OpportunityGraphResponse
from app.modules.opportunities.materialization_models import OpportunityEvent
from app.modules.opportunities.models import (
    ApplicationWindowState,
    DegreeLevel,
    FundingType,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    VerificationStatus,
)
from app.modules.opportunities.public_projection import build_public_projection
from app.modules.opportunities.schemas import (
    AdminOpportunityResponse,
    AdminOpportunitySearchResponse,
    DataQualityIssueSearchResponse,
    DuplicateSuggestionDecision,
    DuplicateSuggestionResponse,
    DuplicateSuggestionSearchResponse,
    OpportunityCreate,
    OpportunityDetailResponse,
    OpportunityImportRequest,
    OpportunityImportResponse,
    OpportunitySearchResponse,
    PublicFundingResponse,
    ReviewActionRequest,
    ReviewQueueResponse,
    SourceCheckRequest,
    SourceCheckResponse,
    VerificationUpdate,
)
from app.modules.opportunities.service import OpportunityService
from app.modules.opportunities.sitemap import generate_robots_txt, generate_sitemap_xml
from app.modules.opportunities.telemetry import (
    OutboundClickResponse,
    TrendingScholarshipItem,
    get_trending_scholarships,
    track_outbound_apply_click,
)

router = APIRouter(tags=["opportunities"])

VALIDATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "The request parameters or body failed validation.",
}
AUTHENTICATION_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication is required.",
}
FORBIDDEN_RESPONSE = {
    "model": ErrorResponse,
    "description": "The authenticated user does not have administrator access.",
}
NOT_FOUND_RESPONSE = {
    "model": ErrorResponse,
    "description": "The opportunity was not found.",
}
CONFLICT_RESPONSE = {
    "model": ErrorResponse,
    "description": "A duplicate opportunity already exists.",
}


def get_opportunity_service(
    session: Annotated[Session, Depends(get_db)],
) -> OpportunityService:
    # Manual opportunities retain the existing service behavior. Opportunities created by
    # catalogue ingestion gain an additional publication-readiness guard before the same
    # authorized review transition is invoked.
    return CatalogueAwareOpportunityService(session)


AdminUser = Annotated[User, Depends(require_admin_step_up)]
AdminReader = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.post(
    "/admin/opportunities",
    response_model=AdminOpportunityResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def create_opportunity(
    payload: OpportunityCreate,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> AdminOpportunityResponse:
    return service.create_opportunity(payload, created_by=admin)


@router.get(
    "/admin/opportunities",
    response_model=AdminOpportunitySearchResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_admin_opportunities(
    _admin: AdminReader,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    country: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    degree_level: DegreeLevel | None = None,
    status: OpportunityStatus | None = None,
    verification_status: VerificationStatus | None = None,
    needs_review: bool | None = None,
    provider_query: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    search_query: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    deadline_after: datetime | None = None,
    deadline_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminOpportunitySearchResponse:
    return service.list_admin_opportunities(
        country=country,
        degree_level=degree_level,
        status=status,
        verification_status=verification_status,
        needs_review=needs_review,
        provider_query=provider_query,
        search_query=search_query,
        deadline_after=deadline_after,
        deadline_before=deadline_before,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/opportunities/{opportunity_id}/graph",
    response_model=OpportunityGraphResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE, 404: NOT_FOUND_RESPONSE},
)
def get_admin_opportunity_graph(
    opportunity_id: uuid.UUID,
    _admin: AdminReader,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> OpportunityGraphResponse:
    return service.get_admin_graph(opportunity_id)


@router.get(
    "/admin/review-queue",
    response_model=ReviewQueueResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_review_queue(
    _admin: AdminReader,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewQueueResponse:
    return service.list_review_queue(limit=limit, offset=offset)


@router.get(
    "/admin/data-quality-issues",
    response_model=DataQualityIssueSearchResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_data_quality_issues(
    _admin: AdminReader,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DataQualityIssueSearchResponse:
    return service.list_data_quality_issues(limit=limit, offset=offset)


@router.get(
    "/admin/duplicate-suggestions",
    response_model=DuplicateSuggestionSearchResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE},
)
def list_duplicate_suggestions(
    _admin: AdminReader,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DuplicateSuggestionSearchResponse:
    return service.list_duplicate_suggestions(limit=limit, offset=offset)


@router.post(
    "/admin/duplicate-suggestions/{suggestion_id}/decision",
    response_model=DuplicateSuggestionResponse,
    responses={401: AUTHENTICATION_RESPONSE, 403: FORBIDDEN_RESPONSE, 404: NOT_FOUND_RESPONSE},
)
def review_duplicate_suggestion(
    suggestion_id: uuid.UUID,
    payload: DuplicateSuggestionDecision,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> DuplicateSuggestionResponse:
    return service.review_duplicate_suggestion(suggestion_id, payload, reviewed_by=admin)


@router.post(
    "/admin/opportunities/import",
    response_model=OpportunityImportResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def import_opportunities(
    payload: OpportunityImportRequest,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> OpportunityImportResponse:
    return service.import_opportunities(payload, created_by=admin)


@router.post(
    "/admin/opportunities/{opportunity_id}/review-actions",
    response_model=AdminOpportunityResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def apply_review_action(
    opportunity_id: uuid.UUID,
    payload: ReviewActionRequest,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> AdminOpportunityResponse:
    return service.apply_review_action(opportunity_id, payload, reviewed_by=admin)


@router.post(
    "/admin/sources/{source_id}/checks",
    response_model=SourceCheckResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def record_source_check(
    source_id: uuid.UUID,
    payload: SourceCheckRequest,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> SourceCheckResponse:
    return service.record_source_check(source_id, payload, checked_by=admin)


@router.patch(
    "/admin/opportunities/{opportunity_id}/verification",
    response_model=AdminOpportunityResponse,
    responses={
        401: AUTHENTICATION_RESPONSE,
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
def update_verification(
    opportunity_id: uuid.UUID,
    payload: VerificationUpdate,
    admin: AdminUser,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> AdminOpportunityResponse:
    return service.verify_source(opportunity_id, payload, checked_by=admin)


@router.get(
    "/opportunities",
    response_model=OpportunitySearchResponse,
    responses={422: VALIDATION_RESPONSE},
)
def search_opportunities(
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    degree_level: DegreeLevel | None = None,
    funding_type: FundingType | None = None,
    field: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    nationality: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    intake_year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    deadline_after: datetime | None = None,
    deadline_before: datetime | None = None,
    funding_coverage: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    application_fee: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    english_requirement: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    verified_after: datetime | None = None,
    open_now: bool = False,
    application_window_state: ApplicationWindowState | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunitySearchResponse:
    return service.list_public_opportunities(
        q=q,
        country=country,
        degree_level=degree_level,
        funding_type=funding_type,
        field=field,
        nationality=nationality,
        intake_year=intake_year,
        deadline_after=deadline_after,
        deadline_before=deadline_before,
        funding_coverage=funding_coverage,
        application_fee=application_fee,
        english_requirement=english_requirement,
        verified_after=verified_after,
        open_now=open_now,
        application_window_state=application_window_state,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityDetailResponse,
    responses={404: NOT_FOUND_RESPONSE},
)
def get_opportunity(
    opportunity_id: uuid.UUID,
    service: Annotated[OpportunityService, Depends(get_opportunity_service)],
) -> OpportunityDetailResponse:
    return service.get_public_opportunity(opportunity_id)


# ==============================================================================
# MVP MODULE 1: CALENDAR & DEADLINE RADAR (.ics & Google Calendar)
# ==============================================================================


@router.get(
    "/opportunities/{opportunity_id}/calendar.ics",
    responses={404: NOT_FOUND_RESPONSE},
    summary="Download RFC 5545 .ics calendar event file for a scholarship",
)
def get_opportunity_calendar_ics(
    opportunity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    opportunity = session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    cycle = session.scalar(
        select(OpportunityCycle).where(OpportunityCycle.opportunity_id == opportunity_id)
    )
    deadlines = list(
        session.scalars(
            select(ScopedDeadline).where(ScopedDeadline.scholarship_id == opportunity_id)
        )
    )
    events = list(
        session.scalars(
            select(OpportunityEvent).where(OpportunityEvent.scholarship_id == opportunity_id)
        )
    )

    ics_payload = generate_opportunity_ics(
        opportunity, cycle=cycle, deadlines=deadlines, events=events
    )
    slug = _slugify(opportunity.name)

    return Response(
        content=ics_payload,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-deadline.ics"',
        },
    )


@router.get(
    "/opportunities/{opportunity_id}/calendar-links",
    response_model=CalendarLinkResponse,
    responses={404: NOT_FOUND_RESPONSE},
    summary="Get 1-click Google Calendar & Outlook Web addition links",
)
def get_opportunity_calendar_links(
    opportunity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CalendarLinkResponse:
    opportunity = session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    cycle = session.scalar(
        select(OpportunityCycle).where(OpportunityCycle.opportunity_id == opportunity_id)
    )
    deadline_dt = cycle.application_deadline if cycle else None
    if not deadline_dt:
        deadline_obj = session.scalar(
            select(ScopedDeadline).where(ScopedDeadline.scholarship_id == opportunity_id)
        )
        if deadline_obj and deadline_obj.deadline_at:
            deadline_dt = deadline_obj.deadline_at

    if not deadline_dt:
        deadline_dt = datetime.now()

    google_url = generate_google_calendar_url(
        title=f"DEADLINE: {opportunity.name}",
        start_dt=deadline_dt,
        end_dt=deadline_dt,
        details=f"Official application deadline for {opportunity.name} ({opportunity.country}).",
        location=opportunity.country or "International",
    )

    return CalendarLinkResponse(
        google_calendar_url=google_url,
        outlook_web_url=google_url,
        yahoo_calendar_url=google_url,
        ics_download_url=f"/api/v1/opportunities/{opportunity_id}/calendar.ics",
    )


# ==============================================================================
# MVP MODULE 2: APPLICATION DOCUMENT CHECKLIST
# ==============================================================================


@router.get(
    "/opportunities/{opportunity_id}/checklist",
    response_model=OpportunityChecklistResponse,
    responses={404: NOT_FOUND_RESPONSE},
    summary="Get application required documents and readiness checklist",
)
def get_opportunity_checklist(
    opportunity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> OpportunityChecklistResponse:
    opportunity = session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    docs = list(
        session.scalars(
            select(RequiredDocument).where(RequiredDocument.scholarship_id == opportunity_id)
        )
    )
    return build_opportunity_checklist(opportunity, docs)


# ==============================================================================
# MVP MODULE 3: SCHOLARSHIP FUNDING & BENEFITS COMPARATOR
# ==============================================================================


class CompareOpportunitiesRequest(BaseModel):
    opportunity_ids: list[uuid.UUID] = Field(min_length=1, max_length=5)


@router.post(
    "/opportunities/compare",
    response_model=ComparisonMatrixResponse,
    summary="Compare funding components and financial benefits across 1-5 scholarships",
)
def compare_opportunities(
    payload: CompareOpportunitiesRequest,
    session: Annotated[Session, Depends(get_db)],
) -> ComparisonMatrixResponse:
    data: list[tuple[Opportunity, list[PublicFundingResponse]]] = []
    for opp_id in payload.opportunity_ids:
        opp = session.scalar(select(Opportunity).where(Opportunity.id == opp_id))
        if (
            opp is None
            or opp.status is not OpportunityStatus.ACTIVE
            or EvidencePolicy.select_current_official_source(opp.sources) is None
        ):
            continue
        projection = build_public_projection(session, opp)
        data.append((opp, projection.funding))

    if not data:
        raise HTTPException(
            status_code=404, detail="None of the specified opportunities were found"
        )

    return build_funding_comparison(data)


# ==============================================================================
# MVP MODULE 6: PUBLIC DIRECTORY & SCHEMA.ORG SEO PAGES
# ==============================================================================


@router.get(
    "/directory/scholarships",
    response_model=PublicDirectoryResponse,
    summary="Get public SEO scholarship directory list with Schema.org JSON-LD metadata",
)
def get_public_directory(
    session: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    country: str | None = None,
    degree_level: str | None = None,
    funding_type: str | None = None,
) -> PublicDirectoryResponse:
    query = select(Opportunity).where(Opportunity.status == OpportunityStatus.ACTIVE)
    count_query = select(func.count(Opportunity.id)).where(
        Opportunity.status == OpportunityStatus.ACTIVE
    )
    if country:
        query = query.where(Opportunity.country.ilike(f"%{country}%"))
        count_query = count_query.where(Opportunity.country.ilike(f"%{country}%"))
    if degree_level:
        query = query.where(Opportunity.degree_level == degree_level)
        count_query = count_query.where(Opportunity.degree_level == degree_level)
    if funding_type:
        query = query.where(Opportunity.funding_type == funding_type)
        count_query = count_query.where(Opportunity.funding_type == funding_type)

    total_count = session.scalar(count_query) or 0
    start = (page - 1) * page_size
    page_items = list(
        session.scalars(query.order_by(Opportunity.name).offset(start).limit(page_size))
    )
    cards = [build_directory_card(opp) for opp in page_items]

    active_filter = Opportunity.status == OpportunityStatus.ACTIVE
    countries = sorted(
        [
            c
            for c in session.scalars(
                select(Opportunity.country).where(active_filter).distinct()
            ).all()
            if c
        ]
    )
    degree_levels = sorted(
        [
            d.value
            for d in session.scalars(
                select(Opportunity.degree_level).where(active_filter).distinct()
            ).all()
            if d
        ]
    )
    funding_types = sorted(
        [
            f.value
            for f in session.scalars(
                select(Opportunity.funding_type).where(active_filter).distinct()
            ).all()
            if f
        ]
    )

    total_pages = max(1, (total_count + page_size - 1) // page_size)

    return PublicDirectoryResponse(
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        available_countries=countries,
        available_degree_levels=degree_levels,
        available_funding_types=funding_types,
        scholarships=cards,
    )


@router.get(
    "/directory/scholarships/{country}/{slug}",
    response_model=DirectoryScholarshipCard,
    responses={404: NOT_FOUND_RESPONSE},
    summary="Get single public scholarship landing page card with Schema.org JSON-LD",
)
def get_public_directory_scholarship(
    country: str,
    slug: str,
    session: Annotated[Session, Depends(get_db)],
) -> DirectoryScholarshipCard:
    active_query = select(Opportunity).where(Opportunity.status == OpportunityStatus.ACTIVE)
    if country:
        active_query = active_query.where(Opportunity.country.ilike(f"%{country}%"))
    opportunities = list(session.scalars(active_query))
    matched = None
    for opp in opportunities:
        if _slugify(opp.name) == slug.strip().lower():
            matched = opp
            break

    if matched is None:
        raise HTTPException(status_code=404, detail="Scholarship not found in public directory")

    return build_directory_card(matched)


# ==============================================================================
# PRODUCTION LAUNCH: DYNAMIC SITEMAP.XML & ROBOTS.TXT (SEO ENGINE)
# ==============================================================================


@router.get(
    "/sitemap.xml",
    summary="Dynamic XML Sitemap indexing all active scholarships and category hubs",
)
def get_sitemap(
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    xml_content = generate_sitemap_xml(session)
    return Response(content=xml_content, media_type="application/xml")


@router.get(
    "/robots.txt",
    summary="Search engine crawlers directive file",
)
def get_robots() -> Response:
    robots_content = generate_robots_txt()
    return Response(content=robots_content, media_type="text/plain")


# ==============================================================================
# PRODUCTION LAUNCH: OUTBOUND CLICK TELEMETRY & POPULARITY ANALYTICS
# ==============================================================================


@router.get(
    "/opportunities/{opportunity_id}/apply-click",
    response_model=OutboundClickResponse,
    responses={404: NOT_FOUND_RESPONSE},
    summary="Track student outbound application click to official portal",
)
def track_apply_click(
    opportunity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> OutboundClickResponse:
    opp = session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id))
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return track_outbound_apply_click(opp)


@router.get(
    "/opportunities/analytics/trending",
    response_model=list[TrendingScholarshipItem],
    summary="Get trending scholarships sorted by student application engagement",
)
def get_trending(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=10, ge=1, le=50),
) -> list[TrendingScholarshipItem]:
    return get_trending_scholarships(session, limit=limit)


# ==============================================================================
# PRODUCTION LAUNCH: ANNUAL CYCLE AUTO-ROLLOVER & NEXT INTAKE ESTIMATION
# ==============================================================================


@router.get(
    "/opportunities/{opportunity_id}/cycle-state",
    response_model=CycleStateInfo,
    responses={404: NOT_FOUND_RESPONSE},
    summary="Get real-time annual cycle status, days remaining, or next intake estimations",
)
def get_opportunity_cycle_state(
    opportunity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db)],
) -> CycleStateInfo:
    opp = session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id))
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    cycle = session.scalar(
        select(OpportunityCycle).where(OpportunityCycle.opportunity_id == opportunity_id)
    )
    return determine_cycle_state(opp, cycle=cycle)
