"""Deterministic Phase 2 source-bundle roles and gap reporting.

This module does not fetch or extract facts.  It classifies already-normalized
official artifacts and describes which source objectives still need evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

ACQUISITION_BUNDLE_POLICY_VERSION = "official-source-bundle.v2"
MAX_ACCEPTED_ARTIFACTS = 60


class AcquisitionSourceRole(StrEnum):
    IDENTITY_OVERVIEW = "identity_overview"
    FUNDING_BENEFITS = "funding_benefits"
    ELIGIBILITY = "eligibility"
    DATES_CYCLE = "dates_cycle"
    APPLICATION_PROCESS = "application_process"
    REQUIRED_DOCUMENTS = "required_documents"
    COUNTRY_ROUTE = "country_route"
    PROGRAMME_COURSE_ANNEX = "programme_course_annex"
    UNKNOWN = "unknown"


CORE_SOURCE_ROLES: tuple[AcquisitionSourceRole, ...] = (
    AcquisitionSourceRole.IDENTITY_OVERVIEW,
    AcquisitionSourceRole.FUNDING_BENEFITS,
    AcquisitionSourceRole.ELIGIBILITY,
    AcquisitionSourceRole.DATES_CYCLE,
    AcquisitionSourceRole.APPLICATION_PROCESS,
    AcquisitionSourceRole.REQUIRED_DOCUMENTS,
)

_ROLE_GAP_NAMES = {
    AcquisitionSourceRole.IDENTITY_OVERVIEW: "identity_source",
    AcquisitionSourceRole.FUNDING_BENEFITS: "funding_source",
    AcquisitionSourceRole.ELIGIBILITY: "eligibility_source",
    AcquisitionSourceRole.DATES_CYCLE: "deadline_source",
    AcquisitionSourceRole.APPLICATION_PROCESS: "application_process_source",
    AcquisitionSourceRole.REQUIRED_DOCUMENTS: "required_documents_source",
}

_ROLE_PATTERNS: dict[AcquisitionSourceRole, tuple[re.Pattern[str], ...]] = {
    AcquisitionSourceRole.IDENTITY_OVERVIEW: (
        re.compile(r"\b(?:about|overview|scholarship|programme overview|program overview)\b", re.I),
    ),
    AcquisitionSourceRole.FUNDING_BENEFITS: (
        re.compile(r"\b(?:funding|benefits?|stipend|tuition|allowance|financial support)\b", re.I),
    ),
    AcquisitionSourceRole.ELIGIBILITY: (
        re.compile(
            r"\b(?:eligibility|eligible|academic requirements?|nationality|"
            r"language requirements?)\b",
            re.I,
        ),
    ),
    AcquisitionSourceRole.DATES_CYCLE: (
        re.compile(r"\b(?:deadline|dates?|timeline|application period|intake|cycle)\b", re.I),
    ),
    AcquisitionSourceRole.APPLICATION_PROCESS: (
        re.compile(
            r"\b(?:how to apply|application process|apply online|application portal|"
            r"submit an? application)\b",
            re.I,
        ),
    ),
    AcquisitionSourceRole.REQUIRED_DOCUMENTS: (
        re.compile(
            r"\b(?:required documents?|document checklist|supporting documents?|transcript|"
            r"reference letters?)\b",
            re.I,
        ),
    ),
    AcquisitionSourceRole.COUNTRY_ROUTE: (
        re.compile(
            r"\b(?:country route|country-specific|embassy route|national agency|"
            r"nominating authority)\b",
            re.I,
        ),
    ),
    AcquisitionSourceRole.PROGRAMME_COURSE_ANNEX: (
        re.compile(
            r"\b(?:course annex|programme annex|program annex|course catalogue|"
            r"programme directory|participating courses?|degree programmes?|"
            r"degree programs?|fields? of study|subject areas?|study areas?)\b",
            re.I,
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class AcquisitionRoleDecision:
    role: AcquisitionSourceRole
    deterministic_signals: tuple[str, ...]
    covered_roles: tuple[AcquisitionSourceRole, ...] = ()
    ambiguity_reason: str | None = None

    @property
    def requires_manual_review(self) -> bool:
        return self.role is AcquisitionSourceRole.UNKNOWN


def classify_acquisition_source(
    *, source_url: str, source_text: str, is_root: bool = False
) -> AcquisitionRoleDecision:
    """Choose one primary source objective using explainable lexical signals."""

    parsed_url = urlsplit(source_url)
    leaf = parsed_url.path.rstrip("/").rsplit("/", 1)[-1]
    url_text = f"{leaf} {parsed_url.query}".replace("-", " ").replace("_", " ")
    scores: dict[AcquisitionSourceRole, int] = {}
    signals: dict[AcquisitionSourceRole, list[str]] = {}
    for role, patterns in _ROLE_PATTERNS.items():
        role_signals: list[str] = []
        score = 0
        for pattern in patterns:
            url_match = pattern.search(url_text)
            body_match = pattern.search(source_text[:50_000])
            if url_match:
                score += 5
                role_signals.append(f"url:{url_match.group(0).casefold()}")
            if body_match:
                score += 1
                role_signals.append(f"text:{body_match.group(0).casefold()}")
        if score:
            scores[role] = score
            signals[role] = role_signals

    # An operator-supplied root is the identity anchor unless its URL clearly
    # identifies a more specific objective page.
    if is_root:
        scores[AcquisitionSourceRole.IDENTITY_OVERVIEW] = (
            scores.get(AcquisitionSourceRole.IDENTITY_OVERVIEW, 0) + 4
        )
        signals.setdefault(AcquisitionSourceRole.IDENTITY_OVERVIEW, []).append(
            "context:operator_root"
        )

    if not scores:
        return AcquisitionRoleDecision(
            role=AcquisitionSourceRole.UNKNOWN,
            deterministic_signals=(),
            covered_roles=(),
            ambiguity_reason="no_deterministic_role_signal",
        )
    best_score = max(scores.values())
    winners = [role for role, score in scores.items() if score == best_score]
    # A comprehensive official page or guideline commonly covers several roles.
    # Keep one deterministic primary role for display while preserving every
    # evidenced role for bundle completeness and downstream routing.
    role = next(candidate for candidate in AcquisitionSourceRole if candidate in winners)
    covered_roles = tuple(
        candidate for candidate in AcquisitionSourceRole if candidate in scores
    )
    return AcquisitionRoleDecision(
        role=role,
        deterministic_signals=tuple(
            sorted({signal for candidate in covered_roles for signal in signals[candidate]})
        ),
        covered_roles=covered_roles,
        ambiguity_reason=("multiple_supported_roles" if len(covered_roles) > 1 else None),
    )


def acquisition_role_metadata(decision: AcquisitionRoleDecision) -> dict[str, Any]:
    return {
        "classifier_version": ACQUISITION_BUNDLE_POLICY_VERSION,
        "role": decision.role.value,
        "covered_roles": [role.value for role in decision.covered_roles],
        "deterministic_signals": list(decision.deterministic_signals),
        "ambiguity_reason": decision.ambiguity_reason,
        "requires_manual_review": decision.requires_manual_review,
    }


def build_acquisition_bundle_summary(
    *,
    artifacts: list[dict[str, Any]],
    blocked_urls: list[tuple[str, str]] | None = None,
    budget_exhausted: bool = False,
) -> dict[str, Any]:
    """Return a stable JSON-safe coverage summary for an acquired bundle."""

    if len(artifacts) > MAX_ACCEPTED_ARTIFACTS:
        raise ValueError("acquisition artifact limit exceeded")
    covered: set[AcquisitionSourceRole] = set()
    known_roles = {role.value for role in AcquisitionSourceRole}
    for item in artifacts:
        values = item.get("covered_roles")
        if not isinstance(values, list):
            values = [item.get("role")]
        covered.update(
            AcquisitionSourceRole(str(value))
            for value in values
            if value in known_roles and value != AcquisitionSourceRole.UNKNOWN.value
        )
    blocked_by_role: dict[AcquisitionSourceRole, list[dict[str, str]]] = {}
    blocked_entries: list[dict[str, str]] = []
    for url, reason in blocked_urls or []:
        decision = classify_acquisition_source(source_url=url, source_text="")
        entry = {"url": url, "reason": reason, "role": decision.role.value}
        blocked_entries.append(entry)
        if decision.role is not AcquisitionSourceRole.UNKNOWN:
            blocked_by_role.setdefault(decision.role, []).append(entry)

    gaps: list[str] = []
    for role in CORE_SOURCE_ROLES:
        if role in covered:
            continue
        suffix = "blocked" if blocked_by_role.get(role) else "missing"
        gaps.append(f"{_ROLE_GAP_NAMES[role]}_{suffix}")
    if any(
        item.get("role") == AcquisitionSourceRole.UNKNOWN.value
        and not item.get("covered_roles")
        for item in artifacts
    ):
        gaps.append("source_role_unresolved")
    if budget_exhausted:
        gaps.append("acquisition_budget_exhausted")

    return {
        "policy_version": ACQUISITION_BUNDLE_POLICY_VERSION,
        "reviewable": bool(artifacts),
        "complete": not gaps,
        "accepted_artifact_count": len(artifacts),
        "covered_roles": sorted(role.value for role in covered),
        "gaps": sorted(set(gaps)),
        "artifacts": artifacts,
        "blocked_sources": blocked_entries,
    }


__all__ = [
    "ACQUISITION_BUNDLE_POLICY_VERSION",
    "CORE_SOURCE_ROLES",
    "MAX_ACCEPTED_ARTIFACTS",
    "AcquisitionRoleDecision",
    "AcquisitionSourceRole",
    "acquisition_role_metadata",
    "build_acquisition_bundle_summary",
    "classify_acquisition_source",
]
