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
from urllib.parse import unquote, urlsplit

from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective

SOURCE_ROUTER_VERSION = "source-router.v6"


class SourceContentRole(StrEnum):
    PROVIDER_OVERVIEW = "provider_overview"
    CURRENT_CYCLE_GUIDELINE = "current_cycle_guideline"
    HISTORICAL_GUIDELINE = "historical_guideline"
    APPLICATION_ROUTE = "application_route"
    DEGREE_TRACK = "degree_track"
    PROGRAMME_DIRECTORY = "programme_directory"
    INSTITUTION = "institution"
    ELIGIBILITY = "eligibility"
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
        ClaimObjective.PROGRAMME_DETAILS,
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
    SourceContentRole.ELIGIBILITY: (
        ClaimObjective.ELIGIBILITY,
        ClaimObjective.ELIGIBILITY_CONTEXT,
    ),
    SourceContentRole.FUNDING: (ClaimObjective.FUNDING,),
    SourceContentRole.DOCUMENT_CHECKLIST: (
        ClaimObjective.DOCUMENTS_CORE,
        ClaimObjective.DOCUMENTS_REQUIREMENTS,
        ClaimObjective.DOCUMENTS_COUNTS,
        ClaimObjective.DOCUMENTS_FORMAT,
    ),
    SourceContentRole.DEADLINE_TIMELINE: (ClaimObjective.APPLICATION_TIMELINE,),
    SourceContentRole.APPLICATION_PORTAL: (ClaimObjective.ROUTES,),
    SourceContentRole.RESULT_NOTICE: (),
    SourceContentRole.UNKNOWN: (),
}

_ROLE_RULES: tuple[tuple[SourceContentRole, tuple[str, ...]], ...] = (
    (
        SourceContentRole.CURRENT_CYCLE_GUIDELINE,
        ("application guideline", "guideline", "guidelines"),
    ),
    (
        SourceContentRole.RESULT_NOTICE,
        ("results announcement", "winner announcement", "selected candidates list"),
    ),
    (
        SourceContentRole.FUNDING,
        ("funding", "stipend", "tuition", "financial support", "benefit"),
    ),
    (
        SourceContentRole.ELIGIBILITY,
        ("eligibility", "academic requirement", "nationality requirement"),
    ),
    (SourceContentRole.DOCUMENT_CHECKLIST, ("required document", "application form", "checklist")),
    (SourceContentRole.DEADLINE_TIMELINE, ("deadline", "dates", "application period", "schedule")),
    (
        SourceContentRole.APPLICATION_PORTAL,
        ("application portal", "apply online", "submit application"),
    ),
    (
        SourceContentRole.APPLICATION_ROUTE,
        (
            "application process",
            "how to apply",
            "embassy",
            "university recommendation",
            "application route",
        ),
    ),
    (
        SourceContentRole.PROGRAMME_DIRECTORY,
        ("programme directory", "program directory", "course catalogue"),
    ),
    (
        SourceContentRole.DEGREE_TRACK,
        (
            "bachelor's track",
            "bachelor\u2019s track",
            "master's track",
            "master\u2019s track",
            "master's and doctoral tracks",
            "master\u2019s and doctoral tracks",
            "doctoral track",
            "postdoctoral track",
            "degree track",
        ),
    ),
    (
        SourceContentRole.PROVIDER_OVERVIEW,
        ("overview", "scholarship overview", "programme overview", "program overview"),
    ),
)
_URL_ONLY_ROLE_RULES: tuple[tuple[SourceContentRole, tuple[str, ...]], ...] = (
    (SourceContentRole.APPLICATION_PORTAL, ("apply",)),
)
_AUTHORITATIVE_URL_ROLE_RULES: tuple[tuple[SourceContentRole, tuple[str, ...]], ...] = (
    (
        SourceContentRole.APPLICATION_ROUTE,
        ("how to apply", "instructions for chinese government scholarship"),
    ),
    (
        SourceContentRole.DOCUMENT_CHECKLIST,
        ("required documents", "document checklist", "physical examination form"),
    ),
    (
        SourceContentRole.ELIGIBILITY,
        ("eligibility criteria", "eligibility", "who can apply", "public notice"),
    ),
    (SourceContentRole.FUNDING, ("financial coverage", "funding coverage")),
    (
        SourceContentRole.PROGRAMME_DIRECTORY,
        (
            "program offered",
            "programme offered",
            "programs offered",
            "programmes offered",
            "degree program",
            "degree programme",
            "study area",
            "subject",
        ),
    ),
    (
        SourceContentRole.CURRENT_CYCLE_GUIDELINE,
        ("application guidelines", "application guideline"),
    ),
    (
        SourceContentRole.INSTITUTION,
        ("participating universities", "organizing universities", "university list"),
    ),
    (
        SourceContentRole.RESULT_NOTICE,
        ("score report", "results", "winners", "selected candidates"),
    ),
)
_NON_EVIDENCE_URL_LABELS = {"contact", "contact us", "privacy", "sitemap"}
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_CYCLE_CONTEXT = re.compile(
    r"\b(?:academic year|application|award year|cohort|cycle|deadline|fiscal|funding|"
    r"financial support|fy|guideline|intake|recruit(?:ment|ing)?|stipend|tuition)\b",
    re.I,
)
_PERSONAL_DATE_CONTEXT = re.compile(r"\b(?:age|birth|born)\b", re.I)
_PUBLICATION_DATE_CONTEXT = re.compile(
    r"(?:\b(?:published|posted|updated|last updated)\b\D{0,30}|"
    r"\bby\b.{0,50}\|\s*(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
    r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},?\s*)$",
    re.I,
)


def classify_source(
    *,
    source_url: str,
    source_text: str,
    observed_on: date | None = None,
) -> SourceRoutingDecision:
    """Classify one immutable source without making an extraction decision."""

    today = observed_on or date.today()
    parsed_url = urlsplit(source_url)
    raw_url_label = unquote(parsed_url.path.rstrip("/").rsplit("/", 1)[-1])
    url_label = re.sub(r"[._-]+", " ", raw_url_label).casefold().strip()
    url_label = re.sub(r"\s+(?:aspx?|html?|php|pdf)$", "", url_label).strip()
    decoded_path = re.sub(r"[._/-]+", " ", unquote(parsed_url.path)).casefold()
    url_haystack = f"{decoded_path} {unquote(parsed_url.query)}".casefold()
    text_haystack = source_text[:20_000].casefold()
    if url_label in _NON_EVIDENCE_URL_LABELS:
        cycle, cycle_signals, cycle_reason = _classify_cycle(text_haystack, today.year)
        return SourceRoutingDecision(
            classifier_version=SOURCE_ROUTER_VERSION,
            role=SourceContentRole.UNKNOWN,
            cycle=cycle,
            deterministic_signals=("authoritative_url_role:non_evidence", *cycle_signals),
            confidence=1.0,
            ambiguity_reason=cycle_reason or "non_evidence_page",
            requires_manual_review=True,
            applicable_objectives=(),
        )
    authoritative_url_role = next(
        (
            role
            for role, labels in _AUTHORITATIVE_URL_ROLE_RULES
            if any(label in url_haystack for label in labels)
        ),
        None,
    )
    url_matches = [
        (role, keyword)
        for role, keywords in (*_ROLE_RULES, *_URL_ONLY_ROLE_RULES)
        for keyword in keywords
        if keyword in url_haystack
    ]
    text_matches = [
        (role, keyword)
        for role, keywords in _ROLE_RULES
        for keyword in keywords
        if keyword in text_haystack
    ]
    url_only_roles = {
        role
        for role, keywords in _URL_ONLY_ROLE_RULES
        for keyword in keywords
        if keyword in url_haystack
    }
    matches = url_matches + text_matches
    # A true action URL such as `/apply` is intentionally narrow. Other URL
    # labels (for example `/masters-scholarships`) describe the scheme, not the
    # full evidence coverage of a comprehensive official page, so body roles
    # must not be discarded.
    roles = (
        {authoritative_url_role}
        if authoritative_url_role is not None
        else url_only_roles
        if len(url_only_roles) == 1
        else {role for role, _ in matches}
    )
    signals = (
        (f"authoritative_url_role:{authoritative_url_role.value}",)
        if authoritative_url_role is not None
        else ()
    ) + tuple(f"keyword:{keyword}" for _, keyword in matches)
    cycle, cycle_signals, cycle_reason = _classify_cycle(text_haystack, today.year)

    if not roles:
        return SourceRoutingDecision(
            classifier_version=SOURCE_ROUTER_VERSION,
            role=SourceContentRole.UNKNOWN,
            cycle=cycle,
            deterministic_signals=signals + cycle_signals,
            confidence=0.0,
            ambiguity_reason=cycle_reason or "no_deterministic_role_signal",
            requires_manual_review=True,
            applicable_objectives=(),
        )

    if len(roles) >= 3 and cycle in {
        SourceCycle.CURRENT,
        SourceCycle.UPCOMING,
        SourceCycle.HISTORICAL,
        SourceCycle.AMBIGUOUS,
    }:
        role = (
            SourceContentRole.HISTORICAL_GUIDELINE
            if cycle is SourceCycle.HISTORICAL
            else SourceContentRole.CURRENT_CYCLE_GUIDELINE
        )
        applicable = tuple(ClaimObjective)
    else:
        role = next(
            candidate_role
            for candidate_role, _keywords in _ROLE_RULES
            if candidate_role in roles
        )
        applicable_set = {
            objective
            for candidate_role in roles
            for objective in _ROLE_OBJECTIVES[candidate_role]
        }
        applicable = tuple(
            objective for objective in ClaimObjective if objective in applicable_set
        )
    if role is SourceContentRole.CURRENT_CYCLE_GUIDELINE and cycle is SourceCycle.HISTORICAL:
        role = SourceContentRole.HISTORICAL_GUIDELINE
    multiple_roles = len(roles) > 1
    deadline_cycle_unresolved = (
        roles == {SourceContentRole.DEADLINE_TIMELINE}
        and cycle is SourceCycle.EVERGREEN
    )
    requires_manual_review = (
        cycle is SourceCycle.AMBIGUOUS and authoritative_url_role is None
    ) or deadline_cycle_unresolved
    ambiguity_reason = cycle_reason or (
        "deadline_cycle_unresolved"
        if deadline_cycle_unresolved
        else "multiple_supported_content_roles"
        if multiple_roles
        else None
    )
    return SourceRoutingDecision(
        classifier_version=SOURCE_ROUTER_VERSION,
        role=role,
        cycle=cycle,
        deterministic_signals=signals + cycle_signals,
        confidence=0.8 if multiple_roles else 1.0,
        ambiguity_reason=ambiguity_reason,
        requires_manual_review=requires_manual_review,
        applicable_objectives=applicable,
    )


def routed_objectives(
    decision: SourceRoutingDecision,
    *,
    unresolved: set[ClaimObjective] | None = None,
) -> tuple[ClaimObjective, ...]:
    """Return objectives supported by a usable source.

    ``unresolved`` remains available to callers that intentionally want first-source-wins
    behaviour. Full catalogue ingestion omits it so specialist pages can add facts even
    after an overview page returned a locally complete result.
    """

    if decision.requires_manual_review or decision.role is SourceContentRole.UNKNOWN:
        return ()
    if unresolved is None:
        return decision.applicable_objectives
    return tuple(
        objective for objective in decision.applicable_objectives if objective in unresolved
    )


def _classify_cycle(
    text: str, current_year: int
) -> tuple[SourceCycle, tuple[str, ...], str | None]:
    years: list[int] = []
    for match in _YEAR.finditer(text):
        nearby = text[max(0, match.start() - 100) : match.end() + 100]
        personal_context = text[max(0, match.start() - 45) : match.end() + 45]
        if _PERSONAL_DATE_CONTEXT.search(personal_context):
            continue
        publication_context = text[max(0, match.start() - 100) : match.start()]
        if _PUBLICATION_DATE_CONTEXT.search(publication_context):
            continue
        if _CYCLE_CONTEXT.search(nearby):
            years.append(int(match.group(1)))
    years = sorted(set(years))
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
    # A current application deadline for the next intake is one coherent cycle,
    # not a historical/current conflict (for example: apply in 2026 for 2027 entry).
    if states <= {SourceCycle.CURRENT, SourceCycle.UPCOMING}:
        return (
            SourceCycle.UPCOMING if SourceCycle.UPCOMING in states else SourceCycle.CURRENT,
            signals,
            None,
        )
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
