"""Deterministic source-role, cycle, and objective routing for catalogue work.

This module intentionally treats source text as untrusted data.  It records
explainable lexical signals but never lets a score or model confidence override
an ambiguous role/cycle decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective

SOURCE_ROUTER_VERSION = "source-router.v1"


class SourceContentRole(StrEnum):
    PROVIDER_OVERVIEW = "provider_overview"
    CURRENT_CYCLE_GUIDELINE = "current_cycle_guideline"
    HISTORICAL_GUIDELINE = "historical_guideline"
    APPLICATION_ROUTE = "application_route"
    DEGREE_TRACK = "degree_track"
    PROGRAMME_DIRECTORY = "programme_directory"
    INSTITUTION = "institution"
    FUNDING = "funding"
    DOCUMENT_CHECKLIST = "document_checklist"
    DEADLINE_TIMELINE = "deadline_timeline"
    APPLICATION_PORTAL = "application_portal"
    RESULT_NOTICE = "result_notice"
    UNKNOWN = "unknown"


class SourceCycle(StrEnum):
    CURRENT = "current"
    UPCOMING = "upcoming"
    HISTORICAL = "historical"
    EVERGREEN = "evergreen"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class SourceRoutingDecision:
    classifier_version: str
    role: SourceContentRole
    cycle: SourceCycle
    deterministic_signals: tuple[str, ...]
    confidence: float
    ambiguity_reason: str | None
    requires_manual_review: bool
    applicable_objectives: tuple[ClaimObjective, ...]


_ROLE_OBJECTIVES: dict[SourceContentRole, tuple[ClaimObjective, ...]] = {
    SourceContentRole.PROVIDER_OVERVIEW: (
        ClaimObjective.IDENTITY,
        ClaimObjective.PROGRAMMES,
        ClaimObjective.ROUTES,
        ClaimObjective.FUNDING,
    ),
    SourceContentRole.CURRENT_CYCLE_GUIDELINE: tuple(ClaimObjective),
    SourceContentRole.HISTORICAL_GUIDELINE: tuple(ClaimObjective),
    SourceContentRole.APPLICATION_ROUTE: (
        ClaimObjective.ROUTES,
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.ELIGIBILITY_CONTEXT,
        ClaimObjective.DOCUMENTS_CORE,
        ClaimObjective.DOCUMENTS_REQUIREMENTS,
        ClaimObjective.DOCUMENTS_COUNTS,
        ClaimObjective.DOCUMENTS_FORMAT,
        ClaimObjective.APPLICATION_TIMELINE,
    ),
    SourceContentRole.DEGREE_TRACK: (
        ClaimObjective.PROGRAMMES,
        ClaimObjective.PROGRAMME_DETAILS,
        ClaimObjective.ELIGIBILITY,
    ),
    SourceContentRole.PROGRAMME_DIRECTORY: (
        ClaimObjective.PROGRAMMES,
        ClaimObjective.PROGRAMME_DETAILS,
    ),
    SourceContentRole.INSTITUTION: (
        ClaimObjective.PROGRAMMES,
        ClaimObjective.PROGRAMME_DETAILS,
        ClaimObjective.ROUTES,
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.APPLICATION_TIMELINE,
    ),
    SourceContentRole.FUNDING: (ClaimObjective.FUNDING,),
    SourceContentRole.DOCUMENT_CHECKLIST: (
        ClaimObjective.DOCUMENTS_CORE,
        ClaimObjective.DOCUMENTS_REQUIREMENTS,
        ClaimObjective.DOCUMENTS_COUNTS,
        ClaimObjective.DOCUMENTS_FORMAT,
    ),
    SourceContentRole.DEADLINE_TIMELINE: (ClaimObjective.APPLICATION_TIMELINE,),
    SourceContentRole.APPLICATION_PORTAL: (
        ClaimObjective.ROUTES,
        ClaimObjective.DOCUMENTS_CORE,
        ClaimObjective.APPLICATION_TIMELINE,
    ),
    SourceContentRole.RESULT_NOTICE: (),
    SourceContentRole.UNKNOWN: (),
}

_ROLE_RULES: tuple[tuple[SourceContentRole, tuple[str, ...]], ...] = (
    (SourceContentRole.RESULT_NOTICE, ("result", "winner", "selected candidate")),
    (SourceContentRole.FUNDING, ("stipend", "tuition", "financial support", "benefit")),
    (SourceContentRole.DOCUMENT_CHECKLIST, ("required document", "application form", "checklist")),
    (SourceContentRole.DEADLINE_TIMELINE, ("deadline", "application period", "schedule")),
    (
        SourceContentRole.APPLICATION_PORTAL,
        ("application portal", "apply online", "submit application"),
    ),
    (
        SourceContentRole.APPLICATION_ROUTE,
        ("embassy", "university recommendation", "application route"),
    ),
    (
        SourceContentRole.PROGRAMME_DIRECTORY,
        ("programme directory", "program directory", "course catalogue"),
    ),
    (SourceContentRole.DEGREE_TRACK, ("bachelor", "master", "doctoral", "degree track")),
    (SourceContentRole.INSTITUTION, ("university", "institution", "faculty")),
)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def classify_source(
    *,
    source_url: str,
    source_text: str,
    observed_on: date | None = None,
) -> SourceRoutingDecision:
    """Classify one immutable source without making an extraction decision."""

    today = observed_on or date.today()
    haystack = f"{source_url}\n{source_text[:20_000]}".casefold()
    matches = [
        (role, keyword)
        for role, keywords in _ROLE_RULES
        for keyword in keywords
        if keyword in haystack
    ]
    roles = {role for role, _ in matches}
    signals = tuple(f"keyword:{keyword}" for _, keyword in matches)
    cycle, cycle_signals, cycle_reason = _classify_cycle(haystack, today.year)

    if len(roles) != 1:
        reason = "no_deterministic_role_signal" if not roles else "conflicting_role_signals"
        return SourceRoutingDecision(
            classifier_version=SOURCE_ROUTER_VERSION,
            role=SourceContentRole.UNKNOWN,
            cycle=cycle,
            deterministic_signals=signals + cycle_signals,
            confidence=0.0,
            ambiguity_reason=cycle_reason or reason,
            requires_manual_review=True,
            applicable_objectives=(),
        )

    role = next(iter(roles))
    deadline_cycle_unresolved = (
        role is SourceContentRole.DEADLINE_TIMELINE and cycle is SourceCycle.EVERGREEN
    )
    return SourceRoutingDecision(
        classifier_version=SOURCE_ROUTER_VERSION,
        role=role,
        cycle=cycle,
        deterministic_signals=signals + cycle_signals,
        confidence=1.0,
        ambiguity_reason=(
            cycle_reason if not deadline_cycle_unresolved else "deadline_cycle_unresolved"
        ),
        requires_manual_review=(cycle is SourceCycle.AMBIGUOUS or deadline_cycle_unresolved),
        applicable_objectives=_ROLE_OBJECTIVES[role],
    )


def routed_objectives(
    decision: SourceRoutingDecision,
    *,
    unresolved: set[ClaimObjective],
) -> tuple[ClaimObjective, ...]:
    """Return only unresolved objectives allowed by a non-ambiguous source."""

    if decision.requires_manual_review or decision.role is SourceContentRole.UNKNOWN:
        return ()
    return tuple(
        objective for objective in decision.applicable_objectives if objective in unresolved
    )


def _classify_cycle(
    text: str, current_year: int
) -> tuple[SourceCycle, tuple[str, ...], str | None]:
    years = sorted({int(value) for value in _YEAR.findall(text)})
    signals = tuple(f"year:{year}" for year in years)
    if any(token in text for token in ("archived", "previous cycle", "past year")):
        return SourceCycle.HISTORICAL, (*signals, "historical_marker"), None
    if not years:
        return SourceCycle.EVERGREEN, signals, None
    states = {
        SourceCycle.HISTORICAL
        if year < current_year
        else SourceCycle.CURRENT
        if year == current_year
        else SourceCycle.UPCOMING
        for year in years
    }
    if len(states) != 1:
        return SourceCycle.AMBIGUOUS, signals, "multiple_cycle_years"
    return next(iter(states)), signals, None


__all__ = [
    "SOURCE_ROUTER_VERSION",
    "SourceContentRole",
    "SourceCycle",
    "SourceRoutingDecision",
    "classify_source",
    "routed_objectives",
]
