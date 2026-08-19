"""Deterministic PR6 claim-resolution primitives.

This module has no database, network, or model dependency. It resolves already
validated source assertions by exact graph scope, field-specific authority,
applicability, and typed value semantics. It never publishes or materializes
canonical graph facts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.modules.catalogue_ingestion.claim_core import (
    ClaimType,
    ClaimValueState,
    DegreeClaimSubject,
    DegreeClaimValue,
    EligibilityClaimSubject,
    EligibilityClaimValue,
    EligibilityOperator,
    FundingClaimSubject,
    FundingClaimValue,
    SourceClaim,
    TemporalClaimValue,
    TemporalPrecision,
    clean_text,
)

RESOLUTION_CORE_VERSION = "pr6-resolution-core.v2"


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
    """System-resolved target scope; keys are never model-generated graph IDs."""

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
        elif self.authority_priority is not None:
            raise ValueError("non-authorized claims cannot carry authority_priority")


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
    temporal_local_dates: tuple[str, ...] = field(default_factory=tuple)


def resolve_claim_assessments(
    assessments: list[ClaimAssessmentInput] | tuple[ClaimAssessmentInput, ...],
) -> tuple[ClaimResolution, ...]:
    """Resolve source assertions without majority voting or model arbitration.

    Exact graph scope is partitioned before values are compared. Eligibility is
    additionally partitioned by semantic constraint slot so, for example, an age
    lower bound does not erase an age upper bound. Family-level eligibility
    negation is reconciled against each observed constraint slot by authority.
    """

    standard_groups: dict[
        tuple[str, str, tuple[str, str, str, str, str]],
        list[ClaimAssessmentInput],
    ] = {}
    eligibility_families: dict[
        tuple[str, tuple[str, str, str, str, str]],
        list[ClaimAssessmentInput],
    ] = {}

    for assessment in assessments:
        if assessment.claim.claim_type is ClaimType.ELIGIBILITY_RULE:
            rule_type = _eligibility_rule_type(assessment.claim)
            family_key = (rule_type, assessment.scope.key())
            eligibility_families.setdefault(family_key, []).append(assessment)
            continue

        field_path = _FIELD_PATHS[assessment.claim.claim_type]
        collection_key = collection_key_for_claim(assessment.claim)
        group_key = (field_path, collection_key, assessment.scope.key())
        standard_groups.setdefault(group_key, []).append(assessment)

    resolutions: list[ClaimResolution] = []
    for _, group in sorted(standard_groups.items(), key=lambda item: item[0]):
        resolutions.append(_resolve_exact_group(group))
    for _, family in sorted(eligibility_families.items(), key=lambda item: item[0]):
        resolutions.extend(_resolve_eligibility_family(family))

    return tuple(sorted(resolutions, key=lambda item: item.resolution_key))


def collection_key_for_claim(claim: SourceClaim) -> str:
    """Return a closed system-derived semantic collection key."""

    if isinstance(claim.value, DegreeClaimValue):
        return f"degree:{claim.value.level.value}"
    if isinstance(claim.subject, DegreeClaimSubject):
        return f"degree:{claim.subject.level.value}"

    if isinstance(claim.value, FundingClaimValue):
        return f"funding:{claim.value.component_type.value}"
    if isinstance(claim.subject, FundingClaimSubject):
        return f"funding:{claim.subject.component_type.value}"

    if isinstance(claim.value, EligibilityClaimValue):
        slot = _eligibility_slot(claim.value.operator)
        return f"eligibility:{claim.value.rule_type.value}:{slot}"
    if isinstance(claim.subject, EligibilityClaimSubject):
        return f"eligibility:{claim.subject.rule_type.value}:family"

    if claim.claim_type is ClaimType.APPLICATION_OPENING:
        return "application:opening"
    if claim.claim_type is ClaimType.APPLICATION_DEADLINE:
        return "application:deadline"
    raise ValueError(f"claim lacks a typed collection identity: {claim.claim_type.value}")


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


def _resolve_eligibility_family(
    family: list[ClaimAssessmentInput],
) -> tuple[ClaimResolution, ...]:
    rule_type = _eligibility_rule_type(family[0].claim)
    scope = family[0].scope
    for item in family[1:]:
        if _eligibility_rule_type(item.claim) != rule_type or item.scope != scope:
            raise ValueError("eligibility family contains mixed rule type or scope")

    family_claims = [item for item in family if item.claim.value is None]
    slot_groups: dict[str, list[ClaimAssessmentInput]] = {}
    for item in family:
        if item.claim.value is None:
            continue
        key = collection_key_for_claim(item.claim)
        slot_groups.setdefault(key, []).append(item)

    if not slot_groups:
        return (_resolve_exact_group(family_claims),)

    family_accepted = _accepted_claims(family_claims)
    family_top = _top_authority_claims(family_accepted)
    family_value_resolution = (
        _resolve_values(ClaimType.ELIGIBILITY_RULE, family_top) if family_top else None
    )

    if family_value_resolution is not None and family_value_resolution.conflict:
        return (
            _eligibility_family_conflict(
                family=family,
                rule_type=rule_type,
                scope=scope,
                reason="SAME_AUTHORITY_ELIGIBILITY_APPLICABILITY_CONFLICT",
            ),
        )

    output: list[ClaimResolution] = []
    for slot_key, slot_claims in sorted(slot_groups.items()):
        slot_accepted = _accepted_claims(slot_claims)
        if not family_top or not slot_accepted:
            output.append(_resolve_exact_group(slot_claims))
            continue

        slot_top = _top_authority_claims(slot_accepted)
        family_priority = _authority_priority(family_top[0])
        slot_priority = _authority_priority(slot_top[0])

        if family_priority < slot_priority:
            output.append(
                _eligibility_family_overrides_slot(
                    family=family,
                    family_top=family_top,
                    slot_claims=slot_claims,
                    slot_key=slot_key,
                )
            )
            continue

        if family_priority == slot_priority:
            output.append(
                _eligibility_family_conflict(
                    family=family + slot_claims,
                    rule_type=rule_type,
                    scope=scope,
                    collection_key=slot_key,
                    reason="SAME_AUTHORITY_APPLICABILITY_VALUE_CONFLICT",
                )
            )
            continue

        resolved = _resolve_exact_group(slot_claims)
        output.append(
            _append_resolution_members(
                resolved,
                [
                    _member(
                        item,
                        ResolutionMemberRole.COMPETING,
                        extra=("LOWER_AUTHORITY_FAMILY_ASSERTION",),
                    )
                    for item in family_top
                ],
            )
        )

    return tuple(output)


def _eligibility_family_overrides_slot(
    *,
    family: list[ClaimAssessmentInput],
    family_top: list[_AcceptedClaim],
    slot_claims: list[ClaimAssessmentInput],
    slot_key: str,
) -> ClaimResolution:
    exemplar = slot_claims[0]
    state_resolution = _resolve_values(ClaimType.ELIGIBILITY_RULE, family_top)
    members: list[ResolutionMember] = []

    top_keys = {item.assessment.assessment_key for item in family_top}
    for item in family:
        role = (
            ResolutionMemberRole.EFFECTIVE
            if item.assessment_key in top_keys
            else ResolutionMemberRole.COMPETING
        )
        members.append(_member(item, role))
    for item in slot_claims:
        members.append(
            _member(
                item,
                ResolutionMemberRole.COMPETING,
                extra=("LOWER_AUTHORITY_CONSTRAINT",),
            )
        )

    return ClaimResolution(
        resolution_key=_resolution_key(
            _FIELD_PATHS[ClaimType.ELIGIBILITY_RULE],
            slot_key,
            exemplar.scope,
        ),
        claim_type=ClaimType.ELIGIBILITY_RULE,
        field_path=_FIELD_PATHS[ClaimType.ELIGIBILITY_RULE],
        collection_key=slot_key,
        scope=exemplar.scope,
        outcome=ResolutionOutcome.RESOLVED_BY_AUTHORITY,
        effective_state=state_resolution.state,
        effective_value=None,
        effective_value_hash=state_resolution.value_hash,
        members=_sorted_members(members),
        reason_codes=("STRONGER_FAMILY_ASSERTION_OVERRIDES_CONSTRAINT",),
    )


def _eligibility_family_conflict(
    *,
    family: list[ClaimAssessmentInput],
    rule_type: str,
    scope: ResolvedScope,
    reason: str,
    collection_key: str | None = None,
) -> ClaimResolution:
    key = collection_key or f"eligibility:{rule_type}:family"
    members = [
        _member(item, ResolutionMemberRole.COMPETING)
        for item in sorted(family, key=lambda value: (value.source_key, value.assessment_key))
    ]
    return ClaimResolution(
        resolution_key=_resolution_key(_FIELD_PATHS[ClaimType.ELIGIBILITY_RULE], key, scope),
        claim_type=ClaimType.ELIGIBILITY_RULE,
        field_path=_FIELD_PATHS[ClaimType.ELIGIBILITY_RULE],
        collection_key=key,
        scope=scope,
        outcome=ResolutionOutcome.CONFLICT_REVIEW_REQUIRED,
        effective_state=None,
        effective_value=None,
        effective_value_hash=None,
        members=_sorted_members(members),
        reason_codes=(reason,),
    )


def _resolve_exact_group(group: list[ClaimAssessmentInput]) -> ClaimResolution:
    if not group:
        raise ValueError("cannot resolve an empty claim group")

    ordered = sorted(group, key=lambda item: (item.source_key, item.assessment_key))
    exemplar = ordered[0]
    claim_type = exemplar.claim.claim_type
    field_path = _FIELD_PATHS[claim_type]
    collection_key = collection_key_for_claim(exemplar.claim)
    scope = exemplar.scope

    for item in ordered[1:]:
        if item.scope != scope:
            raise ValueError("exact claim group contains mixed scope")
        if item.claim.claim_type is not claim_type:
            raise ValueError("exact claim group contains mixed claim type")
        if collection_key_for_claim(item.claim) != collection_key:
            raise ValueError("exact claim group contains mixed collection key")

    resolution_key = _resolution_key(field_path, collection_key, scope)
    members: list[ResolutionMember] = []
    accepted: list[_AcceptedClaim] = []
    saw_stale = False
    saw_unsupported = False
    saw_unresolved = False

    for assessment in ordered:
        accepted_item, role = _classify_assessment(assessment)
        if accepted_item is not None:
            accepted.append(accepted_item)
            continue
        if role is ResolutionMemberRole.STALE:
            saw_stale = True
        elif role is ResolutionMemberRole.REJECTED_AUTHORITY:
            saw_unsupported = True
        elif role is ResolutionMemberRole.UNRESOLVED:
            saw_unresolved = True
        members.append(_member(assessment, role))

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
            members=_sorted_members(members),
            reason_codes=reasons,
        )

    strongest = _top_authority_claims(accepted)
    top_priority = _authority_priority(strongest[0])
    weaker = [item for item in accepted if _authority_priority(item) != top_priority]

    value_resolution = _resolve_values(claim_type, strongest)
    if value_resolution.conflict:
        members.extend(
            _member(item.assessment, ResolutionMemberRole.COMPETING) for item in strongest
        )
        members.extend(
            _member(
                item.assessment,
                ResolutionMemberRole.COMPETING,
                extra=("LOWER_AUTHORITY_NON_EFFECTIVE",),
            )
            for item in weaker
        )
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
        if _accepted_matches_resolution(item, value_resolution):
            members.append(
                _member(
                    item.assessment,
                    ResolutionMemberRole.CORROBORATING,
                    extra=("LOWER_AUTHORITY_CORROBORATION",),
                )
            )
        else:
            members.append(
                _member(
                    item.assessment,
                    ResolutionMemberRole.COMPETING,
                    extra=("LOWER_AUTHORITY_NON_EFFECTIVE",),
                )
            )

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


def _accepted_claims(group: list[ClaimAssessmentInput]) -> list[_AcceptedClaim]:
    accepted: list[_AcceptedClaim] = []
    for assessment in group:
        item, _ = _classify_assessment(assessment)
        if item is not None:
            accepted.append(item)
    return accepted


def _classify_assessment(
    assessment: ClaimAssessmentInput,
) -> tuple[_AcceptedClaim | None, ResolutionMemberRole]:
    if assessment.scope_status is ScopeResolutionStatus.OUT_OF_TARGET_SCOPE:
        return None, ResolutionMemberRole.OUT_OF_SCOPE
    if assessment.scope_status is not ScopeResolutionStatus.RESOLVED_EXISTING:
        return None, ResolutionMemberRole.UNRESOLVED
    if assessment.evidence_status is not EvidenceMatchStatus.MATCHED:
        return None, ResolutionMemberRole.UNRESOLVED
    if assessment.authority_status is AuthorityStatus.UNSUPPORTED_AUTHORITY:
        return None, ResolutionMemberRole.REJECTED_AUTHORITY
    if assessment.authority_status is not AuthorityStatus.AUTHORIZED:
        return None, ResolutionMemberRole.UNRESOLVED
    if assessment.applicability_status is ApplicabilityStatus.STALE:
        return None, ResolutionMemberRole.STALE
    if assessment.applicability_status not in _APPLICABLE:
        return None, ResolutionMemberRole.UNRESOLVED

    normalized = normalize_claim_value(assessment.claim)
    item = _AcceptedClaim(
        assessment=assessment,
        state=assessment.claim.value_state,
        normalized_value=normalized,
        normalized_hash=_hash_value_state(assessment.claim.value_state, normalized),
    )
    return item, ResolutionMemberRole.EFFECTIVE


def _top_authority_claims(claims: list[_AcceptedClaim]) -> list[_AcceptedClaim]:
    if not claims:
        return []
    top_priority = min(_authority_priority(item) for item in claims)
    return [item for item in claims if _authority_priority(item) == top_priority]


def _authority_priority(item: _AcceptedClaim) -> int:
    priority = item.assessment.authority_priority
    if priority is None:
        raise ValueError("accepted claim is missing authority priority")
    return priority


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
            if asserted_date not in local_dates:
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
            temporal_local_dates=tuple(sorted(local_dates)),
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
        serialized = {
            json.dumps(item, sort_keys=True, ensure_ascii=False) for item in normalized_items
        }
        normalized_value = [json.loads(item) for item in sorted(serialized)]
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
        return _temporal_claim_compatible(item.assessment.claim, resolution)
    return item.normalized_hash == resolution.value_hash


def _temporal_claim_compatible(claim: SourceClaim, resolution: _ValueResolution) -> bool:
    if resolution.value is None or not isinstance(claim.value, TemporalClaimValue):
        return False
    value = claim.value
    if resolution.value["precision"] == "date":
        return (
            value.precision is TemporalPrecision.DATE
            and value.calendar_date.isoformat() == resolution.value["calendar_date"]
        )

    resolved_instant = datetime.fromisoformat(
        resolution.value["datetime_value"].replace("Z", "+00:00")
    )
    if value.precision is TemporalPrecision.DATETIME:
        return value.datetime_value.astimezone(UTC) == resolved_instant.astimezone(UTC)
    return value.calendar_date.isoformat() in set(resolution.temporal_local_dates)


def _eligibility_rule_type(claim: SourceClaim) -> str:
    if isinstance(claim.value, EligibilityClaimValue):
        return claim.value.rule_type.value
    if isinstance(claim.subject, EligibilityClaimSubject):
        return claim.subject.rule_type.value
    raise ValueError("eligibility claim requires typed value or subject")


def _eligibility_slot(operator: EligibilityOperator) -> str:
    return {
        EligibilityOperator.GTE: "lower_bound",
        EligibilityOperator.LTE: "upper_bound",
        EligibilityOperator.EQUALS: "equals",
        EligibilityOperator.IN: "include_set",
        EligibilityOperator.NOT_IN: "exclude_set",
    }[operator]


def _append_resolution_members(
    resolution: ClaimResolution,
    members: list[ResolutionMember],
) -> ClaimResolution:
    return ClaimResolution(
        resolution_key=resolution.resolution_key,
        claim_type=resolution.claim_type,
        field_path=resolution.field_path,
        collection_key=resolution.collection_key,
        scope=resolution.scope,
        outcome=resolution.outcome,
        effective_state=resolution.effective_state,
        effective_value=resolution.effective_value,
        effective_value_hash=resolution.effective_value_hash,
        members=_sorted_members(list(resolution.members) + members),
        reason_codes=resolution.reason_codes,
        policy_version=resolution.policy_version,
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
    unique: dict[tuple[str, str, ResolutionMemberRole], ResolutionMember] = {}
    for item in members:
        unique[(item.assessment_key, item.source_key, item.role)] = item
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.source_key, item.assessment_key, item.role.value),
        )
    )


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


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "RESOLUTION_CORE_VERSION",
    "ApplicabilityStatus",
    "AuthorityStatus",
    "ClaimAssessmentInput",
    "ClaimResolution",
    "EvidenceMatchStatus",
    "ResolutionMember",
    "ResolutionMemberRole",
    "ResolutionOutcome",
    "ResolvedScope",
    "ScopeResolutionStatus",
    "collection_key_for_claim",
    "normalize_claim_value",
    "resolve_claim_assessments",
]
