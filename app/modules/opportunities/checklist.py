"""Interactive Application Document Checklist & Readiness Tracker."""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.opportunities.evidence_models import RequiredDocument
from app.modules.opportunities.models import Opportunity


class DocumentChecklistItem(BaseModel):
    document_key: str
    name: str
    required: bool = True
    submission_stage: str = "application"
    original_count: int | None = 1
    copy_count: int | None = 0
    translation_requirement: str | None = None
    certification_requirement: str | None = None
    notes: str | None = None
    completed: bool = False
    priority_level: str = "critical"  # "critical", "standard", "optional"


class OpportunityChecklistResponse(BaseModel):
    opportunity_id: str
    opportunity_name: str
    country: str
    degree_level: str
    total_documents: int
    required_count: int
    completed_count: int
    readiness_percentage: int
    is_ready_for_submission: bool
    critical_missing: list[str]
    items: list[DocumentChecklistItem]


def build_opportunity_checklist(
    opportunity: Opportunity,
    required_docs: list[RequiredDocument],
    completed_keys: set[str] | None = None,
) -> OpportunityChecklistResponse:
    """Build a structured document checklist with real-time readiness scoring."""
    completed = completed_keys or set()
    items: list[DocumentChecklistItem] = []

    # Sort documents: required first, then by display_order
    sorted_docs = sorted(
        required_docs,
        key=lambda doc: (not doc.required, doc.display_order or 0, doc.name),
    )

    completed_required = 0
    total_required = 0
    critical_missing: list[str] = []

    for doc in sorted_docs:
        is_done = doc.document_key in completed
        is_req = bool(doc.required)

        # Classify priority
        priority = "critical" if is_req else "optional"
        if is_req:
            total_required += 1
            if is_done:
                completed_required += 1
            else:
                critical_missing.append(doc.name)

        items.append(
            DocumentChecklistItem(
                document_key=doc.document_key,
                name=doc.name,
                required=is_req,
                submission_stage=doc.submission_stage or "application",
                original_count=doc.original_count,
                copy_count=doc.copy_count,
                translation_requirement=doc.translation_requirement,
                certification_requirement=doc.certification_requirement,
                notes=doc.notes,
                completed=is_done,
                priority_level=priority,
            )
        )

    readiness = (
        int((completed_required / max(1, total_required)) * 100) if total_required > 0 else 100
    )
    is_ready = (completed_required == total_required) and total_required > 0

    return OpportunityChecklistResponse(
        opportunity_id=str(opportunity.id),
        opportunity_name=opportunity.name,
        country=opportunity.country or "International",
        degree_level=opportunity.degree_level.value,
        total_documents=len(items),
        required_count=total_required,
        completed_count=completed_required,
        readiness_percentage=readiness,
        is_ready_for_submission=is_ready,
        critical_missing=critical_missing,
        items=items,
    )
