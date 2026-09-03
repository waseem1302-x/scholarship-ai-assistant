"""Evidence-gated public projection of the Scholarship Intelligence Graph."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.opportunities.evidence_models import (
    ApplicationStep,
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    FundingComponent,
    RequiredDocument,
    ScopedDeadline,
    SourceSnapshot,
)
from app.modules.opportunities.evidence_policy import EvidencePolicy
from app.modules.opportunities.graph_models import ApplicationTrack
from app.modules.opportunities.lifecycle import effective_application_window
from app.modules.opportunities.materialization_models import (
    OpportunityEvent,
    OpportunityResource,
    ScholarshipEligibilityRule,
    ScholarshipProgramme,
)
from app.modules.opportunities.models import Opportunity, OpportunityCycle, Source
from app.modules.opportunities.schemas import (
    PublicApplicationStepResponse,
    PublicCycleResponse,
    PublicDeadlineResponse,
    PublicDocumentResponse,
    PublicEligibilityResponse,
    PublicEventResponse,
    PublicEvidenceReferenceResponse,
    PublicFactScopeResponse,
    PublicFundingResponse,
    PublicProgrammeResponse,
    PublicResourceResponse,
    PublicScholarshipProjectionResponse,
    PublicTrackResponse,
)

_PUBLIC_DIMENSIONS = (
    "cycle",
    "tracks",
    "programmes",
    "eligibility",
    "deadlines",
    "funding",
    "documents",
    "steps",
    "events",
    "resources",
)

_ENTITY_TYPE_ALIASES: dict[type[object], tuple[str, ...]] = {
    OpportunityCycle: ("cycle", "opportunity_cycle"),
    ApplicationTrack: ("track", "application_track"),
    ScholarshipProgramme: ("programme", "scholarship_programme"),
    ScholarshipEligibilityRule: ("eligibility", "scholarship_eligibility_rule"),
    ScopedDeadline: ("deadline", "scoped_deadline"),
    FundingComponent: ("funding", "funding_component"),
    RequiredDocument: ("document", "required_document"),
    ApplicationStep: ("step", "application_step"),
    OpportunityEvent: ("event", "opportunity_event"),
    OpportunityResource: ("resource", "opportunity_resource"),
}


@dataclass(frozen=True, slots=True)
class _EvidenceRow:
    evidence: FieldEvidence
    snapshot: SourceSnapshot
    source: Source


def build_public_projection(
    session: Session,
    opportunity: Opportunity,
) -> PublicScholarshipProjectionResponse:
    """Build a field-level, evidence-gated projection for one scholarship.

    Structural identifiers and scope are retained so consumers can join facts. A
    user-facing value is populated only when that exact field has passed explicit
    evidence from an officially verified source. A conflicting or expired official
    source suppresses the whole projection, matching the existing publication policy.
    """

    sources = list(
        session.scalars(select(Source).where(Source.opportunity_id == opportunity.id)).all()
    )
    official_source = EvidencePolicy.select_current_official_source(sources)
    if official_source is None:
        return _empty_projection()

    cycles = list(
        session.scalars(
            select(OpportunityCycle).where(OpportunityCycle.opportunity_id == opportunity.id)
        ).all()
    )
    cycle = _select_effective_cycle(opportunity, official_source, cycles)
    if cycle is None:
        return _empty_projection()

    records = _load_current_records(session, opportunity.id, cycle.id)
    records["cycle"] = [cycle]
    evidence_by_entity = _load_publishable_evidence(
        session,
        opportunity_id=opportunity.id,
        source_ids={source.id for source in sources if EvidencePolicy.source_can_publish(source)},
        records=records,
    )

    public_cycle = _cycle_response(cycle, evidence_by_entity)
    tracks = _responses(records["tracks"], evidence_by_entity, _track_response)
    programmes = _responses(records["programmes"], evidence_by_entity, _programme_response)
    eligibility = _responses(records["eligibility"], evidence_by_entity, _eligibility_response)
    deadlines = _responses(records["deadlines"], evidence_by_entity, _deadline_response)
    funding = _responses(records["funding"], evidence_by_entity, _funding_response)
    documents = _responses(records["documents"], evidence_by_entity, _document_response)
    steps = _responses(records["steps"], evidence_by_entity, _step_response)
    events = _responses(records["events"], evidence_by_entity, _event_response)
    resources = _responses(records["resources"], evidence_by_entity, _resource_response)

    exposed_records: list[PublicScopedFactResponseType] = [
        *([public_cycle] if public_cycle is not None else []),
        *tracks,
        *programmes,
        *eligibility,
        *deadlines,
        *funding,
        *documents,
        *steps,
        *events,
        *resources,
    ]
    exposed_evidence_ids = {
        evidence_id for record in exposed_records for evidence_id in record.evidence_ids
    }
    public_evidence = sorted(
        (
            _evidence_response(row)
            for rows in evidence_by_entity.values()
            for row in rows
            if row.evidence.id in exposed_evidence_ids
        ),
        key=lambda item: (item.entity_type, item.field_path, str(item.id)),
    )
    dimensions: dict[str, object] = {
        "cycle": public_cycle,
        "tracks": tracks,
        "programmes": programmes,
        "eligibility": eligibility,
        "deadlines": deadlines,
        "funding": funding,
        "documents": documents,
        "steps": steps,
        "events": events,
        "resources": resources,
    }
    return PublicScholarshipProjectionResponse(
        cycle=public_cycle,
        tracks=tracks,
        programmes=programmes,
        eligibility=eligibility,
        deadlines=deadlines,
        funding=funding,
        documents=documents,
        steps=steps,
        events=events,
        resources=resources,
        evidence=public_evidence,
        known_unknowns=[name for name in _PUBLIC_DIMENSIONS if not dimensions[name]],
    )


PublicScopedFactResponseType = (
    PublicCycleResponse
    | PublicTrackResponse
    | PublicProgrammeResponse
    | PublicEligibilityResponse
    | PublicDeadlineResponse
    | PublicFundingResponse
    | PublicDocumentResponse
    | PublicApplicationStepResponse
    | PublicEventResponse
    | PublicResourceResponse
)


def _empty_projection() -> PublicScholarshipProjectionResponse:
    return PublicScholarshipProjectionResponse(known_unknowns=list(_PUBLIC_DIMENSIONS))


def _select_effective_cycle(
    opportunity: Opportunity,
    official_source: Source,
    cycles: list[OpportunityCycle],
) -> OpportunityCycle | None:
    if opportunity.current_cycle_id is not None:
        selected = next(
            (
                cycle
                for cycle in cycles
                if cycle.id == opportunity.current_cycle_id and not cycle.is_archived
            ),
            None,
        )
        if selected is not None:
            return selected
    selected = next((cycle for cycle in cycles if cycle.is_current and not cycle.is_archived), None)
    if selected is not None:
        return selected
    return effective_application_window(opportunity, official_source).cycle


def _load_current_records(
    session: Session,
    scholarship_id: uuid.UUID,
    cycle_id: uuid.UUID,
) -> dict[str, list[Any]]:
    cycle_only: tuple[tuple[str, type[Any], tuple[Any, ...]], ...] = (
        ("tracks", ApplicationTrack, (ApplicationTrack.display_order, ApplicationTrack.name)),
        (
            "programmes",
            ScholarshipProgramme,
            (ScholarshipProgramme.display_order, ScholarshipProgramme.name),
        ),
        (
            "eligibility",
            ScholarshipEligibilityRule,
            (ScholarshipEligibilityRule.display_order, ScholarshipEligibilityRule.rule_key),
        ),
        (
            "events",
            OpportunityEvent,
            (OpportunityEvent.display_order, OpportunityEvent.event_key),
        ),
        (
            "resources",
            OpportunityResource,
            (OpportunityResource.display_order, OpportunityResource.resource_key),
        ),
    )
    scoped: tuple[tuple[str, type[Any], tuple[Any, ...]], ...] = (
        ("deadlines", ScopedDeadline, (ScopedDeadline.deadline_at, ScopedDeadline.id)),
        ("funding", FundingComponent, (FundingComponent.component_type, FundingComponent.id)),
        (
            "documents",
            RequiredDocument,
            (RequiredDocument.display_order, RequiredDocument.name),
        ),
        ("steps", ApplicationStep, (ApplicationStep.display_order, ApplicationStep.title)),
    )
    records: dict[str, list[Any]] = {}
    for name, model, order_by in cycle_only:
        records[name] = list(
            session.scalars(
                select(model)
                .where(model.scholarship_id == scholarship_id, model.cycle_id == cycle_id)
                .order_by(*order_by)
            ).all()
        )
    for name, model, order_by in scoped:
        records[name] = list(
            session.scalars(
                select(model)
                .where(
                    model.scholarship_id == scholarship_id,
                    or_(model.cycle_id == cycle_id, model.cycle_id.is_(None)),
                )
                .order_by(*order_by)
            ).all()
        )
    return records


def _load_publishable_evidence(
    session: Session,
    *,
    opportunity_id: uuid.UUID,
    source_ids: set[uuid.UUID],
    records: dict[str, list[Any]],
) -> dict[tuple[str, uuid.UUID], list[_EvidenceRow]]:
    entity_ids = {record.id for values in records.values() for record in values}
    if not entity_ids or not source_ids:
        return {}
    rows = session.execute(
        select(FieldEvidence, SourceSnapshot, Source)
        .join(SourceSnapshot, SourceSnapshot.id == FieldEvidence.source_snapshot_id)
        .join(Source, Source.id == SourceSnapshot.source_id)
        .where(
            FieldEvidence.entity_id.in_(entity_ids),
            FieldEvidence.support_type == EvidenceSupportType.EXPLICIT,
            FieldEvidence.validator_status == EvidenceValidatorStatus.PASSED,
            Source.id.in_(source_ids),
            Source.opportunity_id == opportunity_id,
        )
        .order_by(FieldEvidence.entity_type, FieldEvidence.field_path, FieldEvidence.id)
    ).all()
    grouped: dict[tuple[str, uuid.UUID], list[_EvidenceRow]] = {}
    for evidence, snapshot, source in rows:
        grouped.setdefault((evidence.entity_type, evidence.entity_id), []).append(
            _EvidenceRow(evidence=evidence, snapshot=snapshot, source=source)
        )
    return grouped


def _entity_evidence(
    record: object,
    evidence_by_entity: dict[tuple[str, uuid.UUID], list[_EvidenceRow]],
) -> list[_EvidenceRow]:
    entity_id = record.id
    rows: list[_EvidenceRow] = []
    for entity_type in _ENTITY_TYPE_ALIASES[type(record)]:
        rows.extend(evidence_by_entity.get((entity_type, entity_id), []))
    return sorted(rows, key=lambda row: (row.evidence.field_path, str(row.evidence.id)))


def _supported(
    record: object,
    field_path: str,
    evidence: list[_EvidenceRow],
    *,
    attribute: str | None = None,
    default: Any = None,
) -> Any:
    if not any(row.evidence.field_path == field_path for row in evidence):
        return default
    return getattr(record, attribute or field_path)


def _scope(record: object, *, own_programme: bool = False) -> PublicFactScopeResponse:
    return PublicFactScopeResponse(
        cycle_id=getattr(record, "cycle_id", None),
        track_id=getattr(record, "id", None)
        if isinstance(record, ApplicationTrack)
        else getattr(record, "track_id", None),
        institution_id=getattr(record, "institution_id", None),
        programme_id=getattr(record, "id", None)
        if own_programme
        else getattr(record, "programme_id", None),
        scholarship_programme_id=getattr(record, "scholarship_programme_id", None),
    )


def _evidence_ids(evidence: list[_EvidenceRow]) -> list[uuid.UUID]:
    return [row.evidence.id for row in evidence]


def _responses(records: Iterable[Any], evidence_by_entity: dict, factory: Any) -> list[Any]:
    responses = []
    for record in records:
        evidence = _entity_evidence(record, evidence_by_entity)
        if evidence:
            responses.append(factory(record, evidence))
    return responses


def _cycle_response(
    cycle: OpportunityCycle,
    evidence_by_entity: dict[tuple[str, uuid.UUID], list[_EvidenceRow]],
) -> PublicCycleResponse | None:
    evidence = _entity_evidence(cycle, evidence_by_entity)
    if not evidence:
        return None
    return PublicCycleResponse(
        id=cycle.id,
        scope=PublicFactScopeResponse(cycle_id=cycle.id),
        evidence_ids=_evidence_ids(evidence),
        label=_supported(cycle, "label", evidence),
        intake_year=_supported(cycle, "intake_year", evidence),
        application_opening_date=_supported(cycle, "application_opening_date", evidence),
        application_deadline=_supported(cycle, "application_deadline", evidence),
        status=_supported(cycle, "status", evidence),
        timezone=_supported(cycle, "timezone", evidence),
        is_rolling=_supported(cycle, "is_rolling", evidence),
    )


def _track_response(track: ApplicationTrack, evidence: list[_EvidenceRow]) -> PublicTrackResponse:
    return PublicTrackResponse(
        id=track.id,
        scope=_scope(track),
        evidence_ids=_evidence_ids(evidence),
        code=track.code,
        parent_track_id=_supported(
            track, "parent_track_key", evidence, attribute="parent_track_id"
        ),
        name=_supported(track, "name", evidence),
        track_type=_supported(track, "track_type", evidence),
        application_method=_supported(track, "application_method", evidence),
        application_url=_supported(track, "application_url", evidence),
        status=_supported(track, "status", evidence),
        display_order=_supported(track, "display_order", evidence, default=0),
    )


def _programme_response(
    programme: ScholarshipProgramme, evidence: list[_EvidenceRow]
) -> PublicProgrammeResponse:
    return PublicProgrammeResponse(
        id=programme.id,
        scope=_scope(programme, own_programme=True),
        evidence_ids=_evidence_ids(evidence),
        programme_key=programme.programme_key,
        name=_supported(programme, "name", evidence),
        programme_type=_supported(programme, "programme_type", evidence),
        degree_levels=_supported(programme, "degree_levels", evidence, default=[]),
        fields_of_study=_supported(programme, "fields_of_study", evidence, default=[]),
        duration=_supported(programme, "duration", evidence),
        description=_supported(programme, "description", evidence),
        application_route_keys=_supported(
            programme, "application_route_keys", evidence, default=[]
        ),
        display_order=_supported(programme, "display_order", evidence, default=0),
    )


def _eligibility_response(
    rule: ScholarshipEligibilityRule, evidence: list[_EvidenceRow]
) -> PublicEligibilityResponse:
    return PublicEligibilityResponse(
        id=rule.id,
        scope=_scope(rule),
        evidence_ids=_evidence_ids(evidence),
        rule_key=rule.rule_key,
        rule_type=_supported(rule, "rule_type", evidence),
        operator=_supported(rule, "operator", evidence),
        value=_supported(rule, "value", evidence, attribute="value_json"),
        unit=_supported(rule, "unit", evidence),
        required=_supported(rule, "required", evidence),
        condition=_supported(rule, "condition", evidence),
        is_exclusion=_supported(rule, "is_exclusion", evidence),
        critical=_supported(rule, "critical", evidence),
        original_text=_supported(rule, "original_text", evidence),
        notes=_supported(rule, "notes", evidence),
        display_order=_supported(rule, "display_order", evidence, default=0),
    )


def _deadline_response(
    deadline: ScopedDeadline, evidence: list[_EvidenceRow]
) -> PublicDeadlineResponse:
    deadline_at = _supported(deadline, "deadline_at", evidence)
    return PublicDeadlineResponse(
        id=deadline.id,
        scope=_scope(deadline),
        evidence_ids=_evidence_ids(evidence),
        deadline_type=_supported(deadline, "deadline_type", evidence),
        deadline_at=deadline_at,
        deadline_text=_supported(deadline, "deadline_text", evidence),
        local_date=deadline.local_date if deadline_at is not None else None,
        precision=_supported(deadline, "precision", evidence, attribute="deadline_precision"),
        timezone=_supported(deadline, "timezone", evidence),
        varies_by=_supported(deadline, "varies_by", evidence),
        label=_supported(deadline, "label", evidence),
        notes=_supported(deadline, "notes", evidence),
    )


def _funding_response(
    funding: FundingComponent, evidence: list[_EvidenceRow]
) -> PublicFundingResponse:
    return PublicFundingResponse(
        id=funding.id,
        scope=_scope(funding),
        evidence_ids=_evidence_ids(evidence),
        component_type=_supported(funding, "component_type", evidence),
        coverage_status=_supported(funding, "coverage_status", evidence),
        amount=_supported(funding, "amount", evidence),
        currency=_supported(funding, "currency", evidence),
        frequency=_supported(funding, "frequency", evidence),
        unit=_supported(funding, "unit", evidence),
        qualifier=_supported(funding, "qualifier", evidence),
        original_text=_supported(funding, "original_text", evidence),
        description=_supported(funding, "description", evidence),
    )


def _document_response(
    document: RequiredDocument, evidence: list[_EvidenceRow]
) -> PublicDocumentResponse:
    return PublicDocumentResponse(
        id=document.id,
        scope=_scope(document),
        evidence_ids=_evidence_ids(evidence),
        document_key=document.document_key,
        name=_supported(document, "name", evidence),
        required=_supported(document, "required", evidence),
        condition=_supported(document, "condition", evidence),
        submission_stage=_supported(document, "submission_stage", evidence),
        original_count=_supported(document, "original_count", evidence),
        copy_count=_supported(document, "copy_count", evidence),
        translation_requirement=_supported(document, "translation_requirement", evidence),
        certification_requirement=_supported(document, "certification_requirement", evidence),
        form_year=_supported(document, "form_year", evidence),
        notes=_supported(document, "notes", evidence),
        display_order=_supported(document, "display_order", evidence, default=0),
    )


def _step_response(
    step: ApplicationStep, evidence: list[_EvidenceRow]
) -> PublicApplicationStepResponse:
    return PublicApplicationStepResponse(
        id=step.id,
        scope=_scope(step),
        evidence_ids=_evidence_ids(evidence),
        step_code=step.step_code,
        title=_supported(step, "title", evidence),
        stage_type=_supported(step, "stage_type", evidence),
        required=_supported(step, "required", evidence),
        actor_type=_supported(step, "actor_type", evidence),
        actor_name=_supported(step, "actor_name", evidence),
        outcome=_supported(step, "outcome", evidence),
        original_text=_supported(step, "original_text", evidence),
        description=_supported(step, "description", evidence),
        application_url=_supported(step, "application_url", evidence),
        display_order=_supported(step, "display_order", evidence, default=0),
    )


def _event_response(event: OpportunityEvent, evidence: list[_EvidenceRow]) -> PublicEventResponse:
    return PublicEventResponse(
        id=event.id,
        scope=_scope(event),
        evidence_ids=_evidence_ids(evidence),
        event_key=event.event_key,
        event_type=_supported(event, "event_type", evidence),
        starts_at=_supported(event, "starts_at", evidence),
        ends_at=_supported(event, "ends_at", evidence),
        date_text=_supported(event, "date_text", evidence),
        precision=_supported(event, "precision", evidence),
        timezone=_supported(event, "timezone", evidence),
        label=_supported(event, "label", evidence),
        notes=_supported(event, "notes", evidence),
        display_order=_supported(event, "display_order", evidence, default=0),
    )


def _resource_response(
    resource: OpportunityResource, evidence: list[_EvidenceRow]
) -> PublicResourceResponse:
    return PublicResourceResponse(
        id=resource.id,
        scope=_scope(resource),
        evidence_ids=_evidence_ids(evidence),
        resource_key=resource.resource_key,
        title=_supported(resource, "title", evidence),
        resource_type=_supported(resource, "resource_type", evidence),
        url=_supported(resource, "url", evidence),
        contact_type=_supported(resource, "contact_type", evidence),
        organization=_supported(resource, "organization", evidence),
        contact_name=_supported(resource, "contact_name", evidence),
        email=_supported(resource, "email", evidence),
        phone=_supported(resource, "phone", evidence),
        address=_supported(resource, "address", evidence),
        original_text=_supported(resource, "original_text", evidence),
        required=_supported(resource, "required", evidence),
        notes=_supported(resource, "notes", evidence),
        display_order=_supported(resource, "display_order", evidence, default=0),
    )


def _evidence_response(row: _EvidenceRow) -> PublicEvidenceReferenceResponse:
    return PublicEvidenceReferenceResponse(
        id=row.evidence.id,
        entity_type=row.evidence.entity_type,
        entity_id=row.evidence.entity_id,
        field_path=row.evidence.field_path,
        source_snapshot_id=row.snapshot.id,
        source_title=row.source.title,
        source_url=row.source.url,
        content_hash=row.snapshot.content_hash,
        excerpt=row.evidence.excerpt,
        excerpt_start=row.evidence.excerpt_start,
        excerpt_end=row.evidence.excerpt_end,
        last_verified_at=row.source.last_verified_at,
        verification_status=row.source.verification_status,
    )


__all__ = ["build_public_projection"]
