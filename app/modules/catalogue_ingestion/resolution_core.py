"""Deterministic PR6 claim resolution primitives.

This module has no database, network, or model dependency. It resolves already
validated source assertions by exact graph scope, field-specific authority
priority, applicability, and typed value semantics. It does not publish or
materialize graph facts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.modules.catalogue_ingestion.claim_core import (
    ClaimType,
    ClaimValueState,
    DegreeClaimValue,
    EligibilityClaimValue,
    FundingClaimValue,
    SourceClaim,
    TemporalClaimValue,
    TemporalPrecision,
    clean_text,
)

RESOLUTION_CORE_VERSION = "pr6-resolution-core.v1"


class EvidenceMatchStatus(StrEnum):
    MATCHED = "matched"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class ScopeResolutionStatus(StrEnum):
    RESOLVED_EXISTING = "resolved_existing"
    PROPOSED_NEW_SCOPE = "proposed_new_scope"
    AMBIGUOUS_SCOPE = "ambiguous_scope"
    UNRESOLVED_SCOPE = "unresolved_scope"
    OUT_OF_TARGET_SCOPE = "out_of_target_scope"


class AuthorityStatus(StrEnum):
    AUTHORIZED = "authorized"
    UNSUPPORTED_AUTHORITY = "unsupported_authority"
    UNRESOLVED_AUTHORITY = "unresolved_authority"
    SOURCE_BLOCKED = "source_blocked"


class ApplicabilityStatus(StrEnum):
    CURRENT_APPLICABLE = "current_applicable"
    HISTORICAL_APPLICABLE = "historical_applicable"
    FUTURE_APPLICABLE = "future_applicable"
    STALE = "stale"
    UNRESOLVED_APPLICABILITY = "unresolved_applicability"
    NOT_APPLICABLE = "not_applicable"


class ResolutionOutcome(StrEnum):
    CORROBORATED = "corroborated"
    RESOLVED_SINGLE_SOURCE = "resolved_single_source"
    RESOLVED_BY_SCOPE = "resolved_by_scope"
    RESOLVED_BY_AUTHORITY = "resolved_by_authority"
    RESOLVED_BY_SUPERSESSION = "resolved_by_supersession"
    PARTIAL_SUPPORT = "partial_support"
    UNSUPPORTED_AUTHORITY = "unsupported_authority"
    STALE_ONLY = "stale_only"
    CONFLICT_REVIEW_REQUIRED = "conflict_review_required"
    UNRESOLVED = "unresolved"


class ResolutionMemberRole(StrEnum):
    EFFECTIVE = "effective"
    CORROBORATING = "corroborating"
    COMPETING = "competing"
    REJECTED_AUTHORITY = "rejected_authority"
    STALE = "stale"
    OUT_OF_SCOPE = "out_of_scope"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


_APPLICABLE = {
    ApplicabilityStatus.CURRENT_APPLICABLE,
    ApplicabilityStatus.HISTORICAL_APPLICABLE,
    ApplicabilityStatus.FUTURE_APPLICABLE,
}

_FIELD_PATHS = {
    ClaimType.DEGREE_LEVEL: "study.degree_level",
    ClaimType.APPLICATION_OPENING: "application.opening",
    ClaimType.APPLICATION_DEADLINE: "application.deadline",
    ClaimType.FUNDING_COMPONENT: "funding.component",
    ClaimType.ELIGIBILITY_RULE: "eligibility.rule",
}


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    """System-resolved target scope; references are never model-generated IDs."""

    target_key: str
    cycle_key: str | None = None
    track_key: str | None = None
    institution_key: str | None = None
    programme_key: str | None = None

    def __post_init__(self) -> None:
        if not self.target_key.strip():
            raise ValueError("target_key cannot be blank")
        if self.track_key is not None and self.cycle_key is None:
            raise ValueError("track scope requires cycle scope")
        if self.programme_key is not None and self.institution_key is None:
            raise ValueError("programme scope requires institution scope")

    def key(self) -> tuple[str, str, str, str, str]:
        return tuple(
            value or ""
            for value in (
                self.target_key,
                self.cycle_key,
                self.track_key,
                self.institution_key,
                self.programme_key,
            )
        )


@dataclass(frozen=True, slots=True)
class ClaimAssessmentInput:
    """One immutable source assertion after deterministic boundary checks."""

    assessment_key: str
    source_key: str
    claim: SourceClaim
    scope: ResolvedScope
    evidence_status: EvidenceMatchStatus
    scope_status: ScopeResolutionStatus
    authority_status: AuthorityStatus
    applicability_status: ApplicabilityStatus
    authority_priority: int | None = None
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.assessment_key.strip() or not self.source_key.strip():
            raise ValueError("assessment_key and source_key cannot be blank")
        if self.authority_status is AuthorityStatus.AUTHORIZED:
            if self.authority_priority is None or self.authority_priority < 0:
                raise ValueError("authorized claims require a non-negative authority_priority")


@dataclass(frozen=True, slots=True)
class ResolutionMember:
    assessment_key: str
    source_key: str
    role: ResolutionMemberRole
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ClaimResolution:
    resolution_key: str
    claim_type: ClaimType
    field_path: str
    collection_key: str
    scope: ResolvedScope
    outcome: ResolutionOutcome
    effective_state: ClaimValueState | None
    effective_value: dict[str, Any] | None
    effective_value_hash: str | None
    members: tuple[ResolutionMember, ...]
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    policy_version: str = RESOLUTION_CORE_VERSION


@dataclass(frozen=True, slots=True)
class _AcceptedClaim:
    assessment: ClaimAssessmentInput
    state: ClaimValueState
    normalized_value: dict[str, Any] | None
    normalized_hash: str


@dataclass(frozen=True, slots=True)
class _ValueResolution:
    conflict: bool
    state: ClaimValueState | None = None
    value: dict[str, Any] | None = None
    value_hash: str | None = None
    partial: bool = False
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


def resolve_claim_assessments(
    assessments: list[ClaimAssessmentInput] | tuple[ClaimAssessmentInput, ...],
) -> tuple[ClaimResolution, ...]:
    """Resolve assessments by exact semantic claim key, deterministically.

    Different graph scopes, cycles, and collection members are partitioned before
    values are compared. Source count never selects between conflicting values.
    """

    grouped: dict[
        tuple[str, str, tuple[str, str, str, str, str]],
        list[ClaimAssessmentInput],
    ] = {}
    for assessment in assessments:
        field_path = _FIELD_PATHS[assessment.claim.claim_type]
        collection_key = collection_key_for_claim(assessment.claim)
        group_key = (field_path, collection_key, assessment.scope.key())
        grouped.setdefault(group_key, []).append(assessment)

    resolutions = [
        _resolve_exact_group(group)
        for _, group in sorted(grouped.items(), key=lambda item: item[0])
    ]
    return tuple(sorted(resolutions, key=lambda item: item.resolution_key))


def collection_key_for_claim(claim: SourceClaim) -> str:
    """Return the system semantic collection key for the implemented claim families."""

    if claim.collection_key_hint:
        return _normalize_key_text(claim.collection_key_hint)
    if isinstance(claim.value, DegreeClaimValue):
        return f"degree:{claim.value.level.value}"
    if isinstance(claim.value, FundingClaimValue):
        return f"funding:{claim.value.component_type.value}"
    if isinstance(claim.value, EligibilityClaimValue):
        return f"eligibility:{claim.value.rule_type.value}"
    if claim.claim_type is ClaimType.APPLICATION_OPENING:
        return "application:opening"
    if claim.claim_type is ClaimType.APPLICATION_DEADLINE:
        return "application:deadline"
    return claim.claim_type.value


def _resolve_exact_group(group: list[ClaimAssessmentInput]) -> ClaimResolution:
    ordered = sorted(group, key=lambda item: (item.source_key, item.assessment_key))
    exemplar = ordered[0]
    claim_type = exemplar.claim.claim_type
    field_path = _FIELD_PATHS[claim_type]
    collection_key = collection_key_for_claim(exemplar.claim)
    scope = exemplar.scope
    resolution_key = _resolution_key(field_path, collection_key, scope)

    members: list[ResolutionMember] = []
    accepted: list[_AcceptedClaim] = []
    saw_stale = False
    saw_unsupported = False
    saw_unresolved = False

    for assessment in ordered:
        if assessment.scope_status is ScopeResolutionStatus.OUT_OF_TARGET_SCOPE:
            members.append(_member(assessment, ResolutionMemberRole.OUT_OF_SCOPE))
            continue
        if assessment.scope_status is not ScopeResolutionStatus.RESOLVED_EXISTING:
            saw_unresolved = True
            members.append(_member(assessment, ResolutionMemberRole.UNRESOLVED))
            continue
        if assessment.evidence_status is not EvidenceMatchStatus.MATCHED:
            saw_unresolved = True
            members.append(_member(assessment, ResolutionMemberRole.UNRESOLVED))
            continue
        if assessment.authority_status is AuthorityStatus.UNSUPPORTED_AUTHORITY:
            saw_unsupported = True
            members.append(_member(assessment, ResolutionMemberRole.REJECTED_AUTHORITY))
            continue
        if assessment.authority_status is not AuthorityStatus.AUTHORIZED:
            saw_unresolved = True
            members.append(_member(assessment, ResolutionMemberRole.UNRESOLVED))
            continue
        if assessment.applicability_status is ApplicabilityStatus.STALE:
            saw_stale = True
            members.append(_member(assessment, ResolutionMemberRole.STALE))
            continue
        if assessment.applicability_status not in _APPLICABLE:
            saw_unresolved = True
            members.append(_member(assessment, ResolutionMemberRole.UNRESOLVED))
            continue

        normalized = normalize_claim_value(assessment.claim)
        accepted.append(
            _AcceptedClaim(
                assessment=assessment,
                state=assessment.claim.value_state,
                normalized_value=normalized,
                normalized_hash=_hash_value_state(assessment.claim.value_state, normalized),
            )
        )

    if not accepted:
        if saw_unsupported and not saw_stale and not saw_unresolved:
            outcome = ResolutionOutcome.UNSUPPORTED_AUTHORITY
            reasons = ("NO_AUTHORIZED_CLAIMS",)
        elif saw_stale and not saw_unresolved:
            outcome = ResolutionOutcome.STALE_ONLY
            reasons = ("NO_CURRENT_OR_APPLICABLE_CLAIMS",)
        else:
            outcome = ResolutionOutcome.UNRESOLVED
            reasons = ("NO_RESOLVABLE_CLAIMS",)
        return ClaimResolution(
            resolution_key=resolution_key,
            claim_type=claim_type,
            field_path=field_path,
            collection_key=collection_key,
            scope=scope,
            outcome=outcome,
            effective_state=None,
            effective_value=None,
            effective_value_hash=None,
            members=tuple(members),
            reason_codes=reasons,
        )

    top_priority = min(item.assessment.authority_priority or 0 for item in accepted)
    strongest = [item for item in accepted if item.assessment.authority_priority == top_priority]
    weaker = [item for item in accepted if item.assessment.authority_priority != top_priority]

    value_resolution = _resolve_values(claim_type, strongest)
    if value_resolution.conflict:
        members.extend(
            _member(item.assessment, ResolutionMemberRole.COMPETING) for item in strongest
        )
        members.extend(_weaker_member(item, strongest) for item in weaker)
        return ClaimResolution(
            resolution_key=resolution_key,
            claim_type=claim_type,
            field_path=field_path,
            collection_key=collection_key,
            scope=scope,
            outcome=ResolutionOutcome.CONFLICT_REVIEW_REQUIRED,
            effective_state=None,
            effective_value=None,
            effective_value_hash=None,
            members=_sorted_members(members),
            reason_codes=("SAME_SCOPE_TOP_AUTHORITY_CONFLICT",),
        )

    weaker_disagrees = any(
        not _accepted_matches_resolution(item, value_resolution) for item in weaker
    )
    independent_support = {
        item.assessment.source_key
        for item in accepted
        if _accepted_matches_resolution(item, value_resolution)
    }

    for item in strongest:
        role = (
            ResolutionMemberRole.EFFECTIVE
            if _accepted_matches_resolution(item, value_resolution)
            else ResolutionMemberRole.PARTIAL
        )
        members.append(_member(item.assessment, role))
    for item in weaker:
        members.append(_weaker_member(item, strongest, value_resolution=value_resolution))

    if weaker_disagrees:
        outcome = ResolutionOutcome.RESOLVED_BY_AUTHORITY
        reasons = ("FIELD_AUTHORITY_PRECEDENCE",)
    elif value_resolution.partial:
        outcome = ResolutionOutcome.PARTIAL_SUPPORT
        reasons = value_resolution.reason_codes or ("PARTIAL_TYPED_SUPPORT",)
    elif value_resolution.state is ClaimValueState.ASSERTED_UNKNOWN:
        outcome = ResolutionOutcome.PARTIAL_SUPPORT
        reasons = ("AUTHORITATIVE_SOURCE_ASSERTS_UNKNOWN",)
    elif len(independent_support) >= 2:
        outcome = ResolutionOutcome.CORROBORATED
        reasons = ("INDEPENDENT_SOURCE_CORROBORATION",)
    else:
        outcome = ResolutionOutcome.RESOLVED_SINGLE_SOURCE
        reasons = ("SINGLE_EFFECTIVE_SOURCE",)

    return ClaimResolution(
        resolution_key=resolution_key,
        claim_type=claim_type,
        field_path=field_path,
        collection_key=collection_key,
        scope=scope,
        outcome=outcome,
        effective_state=value_resolution.state,
        effective_value=value_resolution.value,
        effective_value_hash=value_resolution.value_hash,
        members=_sorted_members(members),
        reason_codes=reasons,
    )


def normalize_claim_value(claim: SourceClaim) -> dict[str, Any] | None:
    """Normalize typed source values without adding unsupported semantics."""

    if claim.value is None:
        return None
    value = claim.value
    if isinstance(value, DegreeClaimValue):
        return {"kind": "degree", "level": value.level.value}
    if isinstance(value, TemporalClaimValue):
        if value.precision is TemporalPrecision.DATE:
            return {
                "kind": "temporal",
                "precision": "date",
                "calendar_date": value.calendar_date.isoformat(),
            }
        normalized_instant = value.datetime_value.astimezone(UTC)
        return {
            "kind": "temporal",
            "precision": "datetime",
            "datetime_value": normalized_instant.isoformat().replace("+00:00", "Z"),
        }
    if isinstance(value, FundingClaimValue):
        return _normalize_funding(value)
    if isinstance(value, EligibilityClaimValue):
        return _normalize_eligibility(value)
    raise TypeError(f"unsupported PR6 claim value: {type(value)!r}")


def _resolve_values(claim_type: ClaimType, claims: list[_AcceptedClaim]) -> _ValueResolution:
    states = {item.state for item in claims}
    if len(states) != 1:
        return _ValueResolution(conflict=True)

    state = next(iter(states))
    if state is not ClaimValueState.ASSERTED_VALUE:
        value_hash = _hash_value_state(state, None)
        return _ValueResolution(
            conflict=False,
            state=state,
            value=None,
            value_hash=value_hash,
        )

    if claim_type in {ClaimType.APPLICATION_OPENING, ClaimType.APPLICATION_DEADLINE}:
        return _resolve_temporal_values(claims)

    distinct = {item.normalized_hash: item.normalized_value for item in claims}
    if len(distinct) != 1:
        return _ValueResolution(conflict=True)
    value = next(iter(distinct.values()))
    return _ValueResolution(
        conflict=False,
        state=state,
        value=value,
        value_hash=_hash_value_state(state, value),
    )


def _resolve_temporal_values(claims: list[_AcceptedClaim]) -> _ValueResolution:
    date_values: set[str] = set()
    datetimes: list[datetime] = []
    local_dates: set[str] = set()

    for item in claims:
        value = item.assessment.claim.value
        if not isinstance(value, TemporalClaimValue):
            return _ValueResolution(conflict=True)
        if value.precision is TemporalPrecision.DATE:
            date_values.add(value.calendar_date.isoformat())
        else:
            datetimes.append(value.datetime_value)
            local_dates.add(value.datetime_value.date().isoformat())

    if len(date_values) > 1:
        return _ValueResolution(conflict=True)

    if datetimes:
        instants = {item.astimezone(UTC) for item in datetimes}
        if len(instants) > 1:
            return _ValueResolution(conflict=True)
        if date_values:
            asserted_date = next(iter(date_values))
            if local_dates != {asserted_date}:
                return _ValueResolution(conflict=True)
        instant = next(iter(instants))
        value = {
            "kind": "temporal",
            "precision": "datetime",
            "datetime_value": instant.isoformat().replace("+00:00", "Z"),
        }
        return _ValueResolution(
            conflict=False,
            state=ClaimValueState.ASSERTED_VALUE,
            value=value,
            value_hash=_hash_value_state(ClaimValueState.ASSERTED_VALUE, value),
            partial=bool(date_values),
            reason_codes=("TEMPORAL_PRECISION_REFINEMENT",) if date_values else (),
        )

    if not date_values:
        return _ValueResolution(conflict=True)
    value = {
        "kind": "temporal",
        "precision": "date",
        "calendar_date": next(iter(date_values)),
    }
    return _ValueResolution(
        conflict=False,
        state=ClaimValueState.ASSERTED_VALUE,
        value=value,
        value_hash=_hash_value_state(ClaimValueState.ASSERTED_VALUE, value),
    )


def _normalize_funding(value: FundingClaimValue) -> dict[str, Any]:
    return {
        "kind": "funding",
        "component_type": value.component_type.value,
        "coverage_status": value.coverage_status.value,
        "amount_kind": value.amount_kind.value,
        "amount": _decimal(value.amount),
        "amount_min": _decimal(value.amount_min),
        "amount_max": _decimal(value.amount_max),
        "currency": value.currency,
        "frequency": value.frequency.value,
    }


def _normalize_eligibility(value: EligibilityClaimValue) -> dict[str, Any]:
    normalized_value: Any
    if isinstance(value.value, list):
        normalized_items = [_normalize_scalar(item) for item in value.value]
        normalized_value = sorted(
            {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in normalized_items}
        )
        normalized_value = [json.loads(item) for item in normalized_value]
    else:
        normalized_value = _normalize_scalar(value.value)
    return {
        "kind": "eligibility",
        "rule_type": value.rule_type.value,
        "operator": value.operator.value,
        "value": normalized_value,
        "unit": clean_text(value.unit) if value.unit else None,
        "grading_scale": _decimal(value.grading_scale),
        "required": value.required,
    }


def _normalize_scalar(value: str | int | Decimal | bool) -> str | int | bool:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, Decimal):
        return _decimal(value)
    return value


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _accepted_matches_resolution(item: _AcceptedClaim, resolution: _ValueResolution) -> bool:
    if item.state != resolution.state:
        return False
    if item.state is not ClaimValueState.ASSERTED_VALUE:
        return True
    if item.assessment.claim.claim_type in {
        ClaimType.APPLICATION_OPENING,
        ClaimType.APPLICATION_DEADLINE,
    }:
        return _temporal_claim_compatible(item.assessment.claim, resolution.value)
    return item.normalized_hash == resolution.value_hash


def _temporal_claim_compatible(claim: SourceClaim, resolved: dict[str, Any] | None) -> bool:
    if resolved is None or not isinstance(claim.value, TemporalClaimValue):
        return False
    value = claim.value
    if resolved["precision"] == "date":
        return (
            value.precision is TemporalPrecision.DATE
            and value.calendar_date.isoformat() == resolved["calendar_date"]
        )
    resolved_instant = datetime.fromisoformat(resolved["datetime_value"].replace("Z", "+00:00"))
    if value.precision is TemporalPrecision.DATETIME:
        return value.datetime_value.astimezone(UTC) == resolved_instant.astimezone(UTC)
    return value.calendar_date.isoformat() == resolved_instant.date().isoformat()


def _weaker_member(
    item: _AcceptedClaim,
    strongest: list[_AcceptedClaim],
    *,
    value_resolution: _ValueResolution | None = None,
) -> ResolutionMember:
    if value_resolution is not None and _accepted_matches_resolution(item, value_resolution):
        return _member(
            item.assessment,
            ResolutionMemberRole.CORROBORATING,
            extra=("LOWER_AUTHORITY_CORROBORATION",),
        )
    return _member(
        item.assessment,
        ResolutionMemberRole.COMPETING,
        extra=("LOWER_AUTHORITY_NON_EFFECTIVE",),
    )


def _member(
    assessment: ClaimAssessmentInput,
    role: ResolutionMemberRole,
    *,
    extra: tuple[str, ...] = (),
) -> ResolutionMember:
    return ResolutionMember(
        assessment_key=assessment.assessment_key,
        source_key=assessment.source_key,
        role=role,
        reason_codes=tuple(sorted(set(assessment.reason_codes + extra))),
    )


def _sorted_members(members: list[ResolutionMember]) -> tuple[ResolutionMember, ...]:
    return tuple(sorted(members, key=lambda item: (item.source_key, item.assessment_key, item.role)))


def _resolution_key(field_path: str, collection_key: str, scope: ResolvedScope) -> str:
    payload = {
        "field_path": field_path,
        "collection_key": collection_key,
        "scope": scope.key(),
        "policy_version": RESOLUTION_CORE_VERSION,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _hash_value_state(state: ClaimValueState, value: dict[str, Any] | None) -> str:
    return hashlib.sha256(
        _canonical_json({"state": state.value, "value": value}).encode("utf-8")
    ).hexdigest()


def _normalize_key_text(value: str) -> str:
    return clean_text(value).casefold()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "ApplicabilityStatus",
    "AuthorityStatus",
    "ClaimAssessmentInput",
    "ClaimResolution",
    "EvidenceMatchStatus",
    "RESOLUTION_CORE_VERSION",
    "ResolvedScope",
    "ResolutionMember",
    "ResolutionMemberRole",
    "ResolutionOutcome",
    "ScopeResolutionStatus",
    "collection_key_for_claim",
    "normalize_claim_value",
    "resolve_claim_assessments",
]
