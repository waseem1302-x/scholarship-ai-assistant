"""Fail-closed relationship classification for Scholarship Intelligence Graph candidates.

The classifier is deliberately deterministic. It may propose a relationship for
human review, but it never publishes, creates a scholarship automatically, or
treats model confidence as proof of independence.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.modules.opportunities.evidence_models import EvidenceSupportType
from app.modules.opportunities.graph_models import RelationshipKind


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    UNRESOLVED = "unresolved"


class IndependenceAuthorityType(StrEnum):
    UNIVERSITY = "university"
    GOVERNMENT = "government"
    FOUNDATION = "foundation"
    OTHER = "other"
    UNKNOWN = "unknown"


LINK_OR_EXISTING_RELATIONSHIPS = frozenset(
    {
        RelationshipKind.SAME_SCHOLARSHIP,
        RelationshipKind.SAME_SCHEME_TRACK,
        RelationshipKind.PARTICIPATING_INSTITUTION,
        RelationshipKind.ELIGIBLE_PROGRAMME,
        RelationshipKind.INSTITUTION_SPECIFIC_REQUIREMENT,
        RelationshipKind.INSTITUTION_SPECIFIC_DEADLINE,
        RelationshipKind.DUPLICATE,
    }
)

INDEPENDENT_RELATIONSHIPS = frozenset(
    {
        RelationshipKind.INDEPENDENT_UNIVERSITY_SCHOLARSHIP,
        RelationshipKind.INDEPENDENT_GOVERNMENT_SCHOLARSHIP,
        RelationshipKind.INDEPENDENT_FOUNDATION_SCHOLARSHIP,
    }
)

_GENERIC_IDENTITY_SUFFIXES = {
    "award",
    "awards",
    "program",
    "programme",
    "programs",
    "programmes",
    "scheme",
    "schemes",
    "scholarship",
    "scholarships",
}
_TRACK_LANGUAGE = re.compile(
    r"\b(?:type|category)\s+[a-z0-9]+\b|"
    r"\b(?:embassy|university|government portal|direct|nomination)\s+"
    r"(?:route|track|recommendation)\b",
    re.IGNORECASE,
)
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


@dataclass(frozen=True, slots=True)
class CandidateRelationshipContext:
    candidate_name: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    candidate_provider_id: str | None = None
    canonical_provider_id: str | None = None
    candidate_application_url: str | None = None
    canonical_application_urls: tuple[str, ...] = ()
    candidate_source_url: str | None = None
    canonical_source_urls: tuple[str, ...] = ()
    source_is_official: bool = False
    parent_scheme_explicit: bool = False
    explicit_relationship: RelationshipKind | None = None


@dataclass(frozen=True, slots=True)
class IndependenceAssessment:
    proposed_relationship: RelationshipKind = RelationshipKind.UNRESOLVED
    official_name_evidence: EvidenceSupportType = EvidenceSupportType.UNKNOWN
    awarding_authority_evidence: EvidenceSupportType = EvidenceSupportType.UNKNOWN
    separate_application: bool | None = None
    independent_award_decision: bool | None = None
    current_official_source: bool = False
    authority_type: IndependenceAuthorityType = IndependenceAuthorityType.UNKNOWN
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RelationshipDecision:
    relationship: RelationshipKind
    confidence_band: ConfidenceBand
    reason_code: str
    deterministic_signals: tuple[str, ...] = field(default_factory=tuple)
    missing_mandatory_proofs: tuple[str, ...] = field(default_factory=tuple)
    requires_human_review: bool = True
    proposes_independent_scholarship: bool = False
    auto_publish_allowed: bool = False


def normalize_identity_name(value: str) -> str:
    """Normalize identity text without turning name similarity into proof."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    tokens = normalized.split()
    while tokens and tokens[-1] in _GENERIC_IDENTITY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_url(value: str | None) -> str | None:
    """Canonicalize comparable HTTPS/HTTP URLs while preserving meaningful query keys."""

    if not value:
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None

    scheme = parsed.scheme.casefold()
    host = parsed.hostname.casefold().strip(".")
    try:
        port = parsed.port
    except ValueError:
        return None
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query_pairs = []
    for key, query_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in _TRACKING_QUERY_KEYS:
            continue
        query_pairs.append((key, query_value))
    query_pairs.sort(key=lambda pair: (pair[0].casefold(), pair[1]))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return normalized or None


def _normalized_urls(values: tuple[str, ...]) -> set[str]:
    return {url for value in values if (url := normalize_url(value)) is not None}


def _identity_names(context: CandidateRelationshipContext) -> set[str]:
    return {
        normalized
        for value in (context.canonical_name, *context.aliases)
        if (normalized := normalize_identity_name(value))
    }


def _route_language_matches_known_identity(context: CandidateRelationshipContext) -> bool:
    if not _TRACK_LANGUAGE.search(context.candidate_name):
        return False
    candidate = normalize_identity_name(context.candidate_name)
    return any(identity and identity in candidate for identity in _identity_names(context))


def _unresolved(reason_code: str, *signals: str) -> RelationshipDecision:
    return RelationshipDecision(
        relationship=RelationshipKind.UNRESOLVED,
        confidence_band=ConfidenceBand.UNRESOLVED,
        reason_code=reason_code,
        deterministic_signals=tuple(signals),
    )


class DeterministicRelationshipClassifier:
    """Classify only relationships that deterministic official evidence can establish."""

    def classify(self, context: CandidateRelationshipContext) -> RelationshipDecision:
        candidate_name = normalize_identity_name(context.candidate_name)
        canonical_name = normalize_identity_name(context.canonical_name)
        candidate_source = normalize_url(context.candidate_source_url)
        canonical_sources = _normalized_urls(context.canonical_source_urls)

        exact_name = bool(candidate_name and candidate_name == canonical_name)
        exact_source = bool(candidate_source and candidate_source in canonical_sources)
        if exact_name and exact_source:
            if not context.source_is_official:
                return _unresolved("official_evidence_required", "exact_name", "exact_source")
            return RelationshipDecision(
                relationship=RelationshipKind.DUPLICATE,
                confidence_band=ConfidenceBand.HIGH,
                reason_code="exact_existing_source_and_name",
                deterministic_signals=("exact_name", "exact_canonical_source"),
            )

        explicit = context.explicit_relationship
        if explicit in LINK_OR_EXISTING_RELATIONSHIPS:
            if not context.source_is_official:
                return _unresolved("official_evidence_required", f"explicit:{explicit.value}")
            if explicit != RelationshipKind.DUPLICATE and not context.parent_scheme_explicit:
                return _unresolved("parent_scheme_not_proven", f"explicit:{explicit.value}")
            return RelationshipDecision(
                relationship=explicit,
                confidence_band=ConfidenceBand.HIGH,
                reason_code="explicit_official_relationship",
                deterministic_signals=(f"explicit:{explicit.value}", "official_source"),
            )

        if explicit in INDEPENDENT_RELATIONSHIPS:
            return _unresolved("independence_requires_gate", f"proposed:{explicit.value}")
        if explicit is not None and explicit != RelationshipKind.UNRESOLVED:
            return _unresolved("relationship_requires_review", f"proposed:{explicit.value}")

        provider_match = (
            _normalize_identifier(context.candidate_provider_id) is not None
            and _normalize_identifier(context.candidate_provider_id)
            == _normalize_identifier(context.canonical_provider_id)
        )
        candidate_application = normalize_url(context.candidate_application_url)
        application_match = bool(
            candidate_application
            and candidate_application in _normalized_urls(context.canonical_application_urls)
        )
        alias_match = candidate_name in _identity_names(context)

        if context.source_is_official and provider_match and alias_match and application_match:
            return RelationshipDecision(
                relationship=RelationshipKind.SAME_SCHOLARSHIP,
                confidence_band=ConfidenceBand.HIGH,
                reason_code="alias_provider_application_match",
                deterministic_signals=(
                    "official_source",
                    "provider_match",
                    "alias_match",
                    "application_url_match",
                ),
            )

        if (
            context.source_is_official
            and context.parent_scheme_explicit
            and provider_match
            and _route_language_matches_known_identity(context)
        ):
            return RelationshipDecision(
                relationship=RelationshipKind.SAME_SCHEME_TRACK,
                confidence_band=ConfidenceBand.HIGH,
                reason_code="explicit_route_language_under_same_scheme",
                deterministic_signals=(
                    "official_source",
                    "parent_scheme_explicit",
                    "provider_match",
                    "route_language",
                ),
            )

        return _unresolved("deterministic_relationship_not_proven")


def decide_independence(assessment: IndependenceAssessment) -> RelationshipDecision:
    """Apply the mandatory five-part independence gate and always require review."""

    if assessment.proposed_relationship in LINK_OR_EXISTING_RELATIONSHIPS:
        return RelationshipDecision(
            relationship=assessment.proposed_relationship,
            confidence_band=ConfidenceBand.HIGH,
            reason_code="existing_or_child_relationship",
            deterministic_signals=("independence_gate_bypassed_for_link",),
        )

    if assessment.conflicts:
        return RelationshipDecision(
            relationship=RelationshipKind.UNRESOLVED,
            confidence_band=ConfidenceBand.UNRESOLVED,
            reason_code="independence_conflict_requires_review",
            deterministic_signals=("conflicting_evidence",),
        )

    missing: list[str] = []
    if assessment.official_name_evidence != EvidenceSupportType.EXPLICIT:
        missing.append("official_name")
    if assessment.awarding_authority_evidence != EvidenceSupportType.EXPLICIT:
        missing.append("awarding_authority")
    if assessment.separate_application is not True:
        missing.append("separate_application")
    if assessment.independent_award_decision is not True:
        missing.append("independent_award_decision")
    if assessment.current_official_source is not True:
        missing.append("current_official_source")

    relationship_by_authority = {
        IndependenceAuthorityType.UNIVERSITY: RelationshipKind.INDEPENDENT_UNIVERSITY_SCHOLARSHIP,
        IndependenceAuthorityType.GOVERNMENT: RelationshipKind.INDEPENDENT_GOVERNMENT_SCHOLARSHIP,
        IndependenceAuthorityType.FOUNDATION: RelationshipKind.INDEPENDENT_FOUNDATION_SCHOLARSHIP,
    }
    independent_relationship = relationship_by_authority.get(assessment.authority_type)
    if independent_relationship is None:
        missing.append("recognized_awarding_authority_type")

    if missing:
        return RelationshipDecision(
            relationship=RelationshipKind.UNRESOLVED,
            confidence_band=ConfidenceBand.UNRESOLVED,
            reason_code="independence_not_proven",
            missing_mandatory_proofs=tuple(missing),
        )

    return RelationshipDecision(
        relationship=independent_relationship,
        confidence_band=ConfidenceBand.HIGH,
        reason_code="independence_proven_pending_human_review",
        deterministic_signals=(
            "official_name_explicit",
            "awarding_authority_explicit",
            "separate_application",
            "independent_award_decision",
            "current_official_source",
        ),
        proposes_independent_scholarship=True,
    )


__all__ = [
    "LINK_OR_EXISTING_RELATIONSHIPS",
    "CandidateRelationshipContext",
    "ConfidenceBand",
    "DeterministicRelationshipClassifier",
    "IndependenceAssessment",
    "IndependenceAuthorityType",
    "RelationshipDecision",
    "decide_independence",
    "normalize_identity_name",
    "normalize_url",
]
