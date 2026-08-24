from datetime import date

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.source_routing import (
    SOURCE_ROUTER_VERSION,
    SourceContentRole,
    SourceCycle,
    classify_source,
    routed_objectives,
)


def test_funding_page_routes_only_unresolved_funding() -> None:
    decision = classify_source(
        source_url="https://example.edu/scholarship/funding",
        source_text="The stipend and tuition financial support are listed here for 2027.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.classifier_version == SOURCE_ROUTER_VERSION
    assert decision.role is SourceContentRole.FUNDING
    assert decision.cycle is SourceCycle.UPCOMING
    assert routed_objectives(
        decision,
        unresolved={ClaimObjective.FUNDING, ClaimObjective.DOCUMENTS_COUNTS},
    ) == (ClaimObjective.FUNDING,)


def test_document_checklist_never_routes_funding_or_programme_objectives() -> None:
    decision = classify_source(
        source_url="https://example.edu/checklist",
        source_text="Required documents: application form, transcript and certified translation.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.role is SourceContentRole.DOCUMENT_CHECKLIST
    assert ClaimObjective.FUNDING not in decision.applicable_objectives
    assert ClaimObjective.PROGRAMMES not in decision.applicable_objectives


def test_unknown_or_conflicting_source_role_fails_closed() -> None:
    unknown = classify_source(
        source_url="https://example.edu/page",
        source_text="Welcome to the official website.",
        observed_on=date(2026, 8, 24),
    )
    conflicting = classify_source(
        source_url="https://example.edu/page",
        source_text="Funding stipend and required documents checklist.",
        observed_on=date(2026, 8, 24),
    )

    assert unknown.role is SourceContentRole.UNKNOWN
    assert unknown.requires_manual_review is True
    assert routed_objectives(unknown, unresolved=set(ClaimObjective)) == ()
    assert conflicting.role is SourceContentRole.UNKNOWN
    assert conflicting.ambiguity_reason == "conflicting_role_signals"


def test_cycle_mixing_requires_manual_review() -> None:
    decision = classify_source(
        source_url="https://example.edu/guidelines",
        source_text="Required documents and application form for the 2025 and 2027 cycles.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.cycle is SourceCycle.AMBIGUOUS
    assert decision.requires_manual_review is True
    assert routed_objectives(decision, unresolved=set(ClaimObjective)) == ()


def test_evergreen_deadline_source_requires_cycle_resolution() -> None:
    decision = classify_source(
        source_url="https://example.edu/application-deadline",
        source_text="The application deadline is published on this page.",
        observed_on=date(2026, 8, 24),
    )

    assert decision.role is SourceContentRole.DEADLINE_TIMELINE
    assert decision.cycle is SourceCycle.EVERGREEN
    assert decision.requires_manual_review is True
    assert decision.ambiguity_reason == "deadline_cycle_unresolved"
    assert routed_objectives(decision, unresolved=set(ClaimObjective)) == ()
