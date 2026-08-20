"""Contextual, append-only officiality assessment for discovery leads."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.discovery import (
    DOMAIN_PATTERN,
    DiscoveryObjectiveKind,
    DiscoveryScopeSnapshot,
    DiscoveryTargetIdentitySnapshot,
)
from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAssessment,
    CatalogueDiscoveryLead,
    CatalogueDiscoveryRun,
    DiscoveryOfficialityStatus,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryAssessmentInput,
    DiscoveryStateError,
)
from app.modules.catalogue_ingestion.sources import (
    OfficialSourceClassifier,
    SourceClassificationReason,
)
from app.modules.catalogue_ingestion.url_policy import normalize_discovery_lead_url
from app.modules.opportunities.evidence_models import SourceOwnerType

CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION = "catalogue-contextual-officiality.v1"


class SourceAuthorityClass(StrEnum):
    CANONICAL_OWNER = "canonical_owner"
    CO_OWNER = "co_owner"
    DELEGATED_OFFICIAL = "delegated_official"
    APPLICATION_PORTAL = "application_portal"
    COUNTRY_MISSION = "country_mission"
    SUPPORTING_INSTITUTION = "supporting_institution"


@dataclass(frozen=True)
class ReviewedOwnerDomain:
    """One active, human-reviewed owner/domain relationship."""

    domain: str
    owner_type: SourceOwnerType
    owner_name_snapshot: str
    authority_class: SourceAuthorityClass
    review_reason: str
    provider_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        normalized_domain = _normalize_reviewed_domain(self.domain)
        normalized_name = " ".join(self.owner_name_snapshot.split())
        normalized_reason = " ".join(self.review_reason.split())
        if not normalized_name or len(normalized_name) > 255:
            raise ValueError("reviewed owner name must be non-empty and bounded")
        if not normalized_reason or len(normalized_reason) > 500:
            raise ValueError("review reason must be non-empty and bounded")
        if self.owner_type is SourceOwnerType.PROVIDER and (
            self.provider_id is None or self.institution_id is not None
        ):
            raise ValueError("provider owner domains require only provider_id")
        if self.owner_type is SourceOwnerType.INSTITUTION and (
            self.institution_id is None or self.provider_id is not None
        ):
            raise ValueError("institution owner domains require only institution_id")
        if self.owner_type is SourceOwnerType.GOVERNMENT and self.institution_id is not None:
            raise ValueError("government owner domains cannot reference an institution")
        if self.owner_type not in {
            SourceOwnerType.PROVIDER,
            SourceOwnerType.GOVERNMENT,
            SourceOwnerType.INSTITUTION,
        }:
            raise ValueError("unsupported reviewed owner type")
        if (
            self.authority_class is SourceAuthorityClass.SUPPORTING_INSTITUTION
            and self.owner_type is not SourceOwnerType.INSTITUTION
        ):
            raise ValueError("supporting institution authority requires an institution owner")
        object.__setattr__(self, "domain", normalized_domain)
        object.__setattr__(self, "owner_name_snapshot", normalized_name)
        object.__setattr__(self, "review_reason", normalized_reason)

    @property
    def owner_id(self) -> uuid.UUID | None:
        return self.provider_id or self.institution_id

    def fingerprint_payload(self) -> dict[str, str | None]:
        return {
            "authority_class": self.authority_class.value,
            "domain": self.domain,
            "institution_id": _uuid_text(self.institution_id),
            "owner_name_snapshot": self.owner_name_snapshot,
            "owner_type": self.owner_type.value,
            "provider_id": _uuid_text(self.provider_id),
            "review_reason": self.review_reason,
        }


@dataclass(frozen=True)
class ContextualOfficialityAssessment:
    assessment_context_hash: str
    context_type: str
    officiality_status: DiscoveryOfficialityStatus
    owner_type: SourceOwnerType
    reason_code: str
    reason_detail: str
    classifier_version: str
    normalized_url: str | None = None
    owner_id: uuid.UUID | None = None
    canonical_domain: str | None = None
    authority_class: SourceAuthorityClass | None = None
    trust_tier: int | None = None
    context_provider_id: uuid.UUID | None = None
    context_institution_id: uuid.UUID | None = None

    def persistence_input(
        self,
        *,
        scope: DiscoveryScopeSnapshot,
        supersedes_assessment_id: uuid.UUID | None = None,
    ) -> DiscoveryAssessmentInput:
        return DiscoveryAssessmentInput(
            assessment_context_hash=self.assessment_context_hash,
            context_type=self.context_type,
            context_scholarship_id=scope.scholarship_id,
            context_provider_id=self.context_provider_id,
            context_institution_id=self.context_institution_id,
            context_cycle_id=scope.cycle_id,
            officiality_status=self.officiality_status,
            owner_type=self.owner_type.value,
            owner_id=self.owner_id,
            canonical_domain=self.canonical_domain,
            trust_tier=self.trust_tier,
            reason_code=self.reason_code,
            reason_detail=self.reason_detail,
            classifier_version=self.classifier_version,
            supersedes_assessment_id=supersedes_assessment_id,
        )


class ContextualOfficialityClassifier:
    """Classify URL ownership only from objective context and reviewed registrations."""

    def __init__(self, base_classifier: OfficialSourceClassifier | None = None) -> None:
        self.base_classifier = base_classifier or OfficialSourceClassifier()

    def assess(
        self,
        url: str,
        *,
        objective_kind: DiscoveryObjectiveKind,
        scope: DiscoveryScopeSnapshot,
        target: DiscoveryTargetIdentitySnapshot,
        reviewed_owner_domains: tuple[ReviewedOwnerDomain, ...],
        classifier_version: str = CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION,
    ) -> ContextualOfficialityAssessment:
        if not classifier_version or len(classifier_version) > 100:
            raise ValueError("classifier version must be non-empty and bounded")
        registrations = tuple(sorted(set(reviewed_owner_domains), key=_registration_sort_key))
        normalization = normalize_discovery_lead_url(url)
        normalized_url = (
            normalization.normalized.value if normalization.normalized is not None else None
        )
        context_hash = _assessment_context_hash(
            raw_url=url,
            normalized_url=normalized_url,
            objective_kind=objective_kind,
            scope=scope,
            target=target,
            registrations=registrations,
            classifier_version=classifier_version,
        )
        context_type = f"discovery:{objective_kind.value}"
        if normalization.normalized is None:
            assert normalization.rejection_code is not None
            return ContextualOfficialityAssessment(
                assessment_context_hash=context_hash,
                context_type=context_type,
                officiality_status=DiscoveryOfficialityStatus.REJECTED_URL_POLICY,
                owner_type=SourceOwnerType.UNKNOWN,
                reason_code=f"URL_POLICY_{normalization.rejection_code.value.upper()}",
                reason_detail="URL failed the bounded discovery lead policy.",
                classifier_version=classifier_version,
            )

        base = self.base_classifier.classify(
            normalized_url,
            reviewed_official_domains={registration.domain for registration in registrations},
        )
        if base.reason_code is SourceClassificationReason.THIRD_PARTY_DIRECTORY:
            return _assessment(
                context_hash=context_hash,
                context_type=context_type,
                status=DiscoveryOfficialityStatus.THIRD_PARTY,
                reason_code="KNOWN_THIRD_PARTY_DIRECTORY",
                reason_detail="Host is a known third-party scholarship directory.",
                classifier_version=classifier_version,
                normalized_url=normalized_url,
            )

        host = normalization.normalized.host
        matching_registrations = tuple(
            registration
            for registration in registrations
            if _same_or_subdomain(host, registration.domain)
        )
        if not matching_registrations:
            return _assessment(
                context_hash=context_hash,
                context_type=context_type,
                status=DiscoveryOfficialityStatus.UNRESOLVED,
                reason_code="NO_REVIEWED_OWNER_DOMAIN_MATCH",
                reason_detail="Host is not tied to any reviewed owner in this context.",
                classifier_version=classifier_version,
                normalized_url=normalized_url,
            )
        most_specific_length = max(
            len(registration.domain.split(".")) for registration in matching_registrations
        )
        matches = tuple(
            registration
            for registration in matching_registrations
            if len(registration.domain.split(".")) == most_specific_length
        )

        owner_keys = {
            (
                match.owner_type.value,
                _uuid_text(match.owner_id),
                _normalized_name(match.owner_name_snapshot),
            )
            for match in matches
        }
        if len(owner_keys) != 1:
            return _assessment(
                context_hash=context_hash,
                context_type=context_type,
                status=DiscoveryOfficialityStatus.UNRESOLVED,
                reason_code="CONFLICTING_REVIEWED_OWNERS",
                reason_detail="Host matches reviewed registrations for different owners.",
                classifier_version=classifier_version,
                normalized_url=normalized_url,
            )

        registration = min(matches, key=_authority_rank)
        context_provider_id, provider_conflict = _target_provider_id(target, registrations)
        if provider_conflict:
            return _assessment(
                context_hash=context_hash,
                context_type=context_type,
                status=DiscoveryOfficialityStatus.UNRESOLVED,
                reason_code="CONFLICTING_TARGET_PROVIDER_IDENTITIES",
                reason_detail="Reviewed registrations disagree on the target provider identity.",
                classifier_version=classifier_version,
                normalized_url=normalized_url,
            )

        if registration.owner_type in {SourceOwnerType.PROVIDER, SourceOwnerType.GOVERNMENT}:
            if context_provider_id is None or registration.provider_id != context_provider_id:
                return _owner_mismatch_assessment(
                    context_hash=context_hash,
                    context_type=context_type,
                    registration=registration,
                    classifier_version=classifier_version,
                    normalized_url=normalized_url,
                    reason_code="CROSS_PROVIDER_OWNER",
                    reason_detail="Reviewed domain owner does not match the target provider.",
                )
            return _provider_assessment(
                context_hash=context_hash,
                context_type=context_type,
                objective_kind=objective_kind,
                registration=registration,
                classifier_version=classifier_version,
                normalized_url=normalized_url,
                context_provider_id=context_provider_id,
            )

        if not _institution_matches_scope(registration, scope, target):
            return _owner_mismatch_assessment(
                context_hash=context_hash,
                context_type=context_type,
                registration=registration,
                classifier_version=classifier_version,
                normalized_url=normalized_url,
                reason_code="CROSS_INSTITUTION_OWNER",
                reason_detail="Reviewed institution owner does not match the objective scope.",
                context_provider_id=context_provider_id,
            )
        return _institution_assessment(
            context_hash=context_hash,
            context_type=context_type,
            target=target,
            registration=registration,
            classifier_version=classifier_version,
            normalized_url=normalized_url,
            context_provider_id=context_provider_id,
        )


class CatalogueDiscoveryOfficialityService:
    """Assess one observed lead and append immutable contextual provenance."""

    def __init__(
        self,
        session: Session,
        classifier: ContextualOfficialityClassifier | None = None,
    ) -> None:
        self.session = session
        self.repository = CatalogueDiscoveryRepository(session)
        self.classifier = classifier or ContextualOfficialityClassifier()

    def assess_lead(
        self,
        *,
        run_id: uuid.UUID,
        lead_id: uuid.UUID,
        reviewed_owner_domains: tuple[ReviewedOwnerDomain, ...],
        classifier_version: str = CONTEXTUAL_OFFICIALITY_CLASSIFIER_VERSION,
        supersedes_assessment_id: uuid.UUID | None = None,
    ) -> CatalogueDiscoveryAssessment:
        run = self.session.get(CatalogueDiscoveryRun, run_id)
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        lead = self.session.get(CatalogueDiscoveryLead, lead_id)
        if lead is None:
            raise DiscoveryStateError("catalogue_discovery_lead_not_found")
        scope = DiscoveryScopeSnapshot.model_validate(run.objective_scope)
        target = DiscoveryTargetIdentitySnapshot.model_validate(run.target_identity_snapshot)
        assessment = self.classifier.assess(
            lead.normalized_url,
            objective_kind=DiscoveryObjectiveKind(run.objective_kind),
            scope=scope,
            target=target,
            reviewed_owner_domains=reviewed_owner_domains,
            classifier_version=classifier_version,
        )
        return self.repository.append_assessment(
            run_id=run.id,
            lead_id=lead.id,
            assessment=assessment.persistence_input(
                scope=scope,
                supersedes_assessment_id=supersedes_assessment_id,
            ),
        )


def _provider_assessment(
    *,
    context_hash: str,
    context_type: str,
    objective_kind: DiscoveryObjectiveKind,
    registration: ReviewedOwnerDomain,
    classifier_version: str,
    normalized_url: str,
    context_provider_id: uuid.UUID,
) -> ContextualOfficialityAssessment:
    if registration.authority_class in {
        SourceAuthorityClass.CANONICAL_OWNER,
        SourceAuthorityClass.CO_OWNER,
    }:
        status = DiscoveryOfficialityStatus.OFFICIAL
        reason_code = "REVIEWED_PROVIDER_AUTHORITY"
        detail = "Reviewed provider owner and objective context match."
        trust_tier = 1
    elif _delegated_authority_supports(registration.authority_class, objective_kind):
        status = DiscoveryOfficialityStatus.SUPPORTING_OFFICIAL
        reason_code = "REVIEWED_SCOPED_PROVIDER_AUTHORITY"
        detail = "Reviewed delegated owner supports this objective without global authority."
        trust_tier = 2
    else:
        status = DiscoveryOfficialityStatus.UNRESOLVED
        reason_code = "AUTHORITY_OUTSIDE_OBJECTIVE_SCOPE"
        detail = "Reviewed owner authority does not cover this objective."
        trust_tier = None
    return _assessment(
        context_hash=context_hash,
        context_type=context_type,
        status=status,
        reason_code=reason_code,
        reason_detail=detail,
        classifier_version=classifier_version,
        normalized_url=normalized_url,
        registration=registration,
        trust_tier=trust_tier,
        context_provider_id=context_provider_id,
    )


def _institution_assessment(
    *,
    context_hash: str,
    context_type: str,
    target: DiscoveryTargetIdentitySnapshot,
    registration: ReviewedOwnerDomain,
    classifier_version: str,
    normalized_url: str,
    context_provider_id: uuid.UUID | None,
) -> ContextualOfficialityAssessment:
    institution_owns_award = (
        registration.authority_class is SourceAuthorityClass.CANONICAL_OWNER
        and target.provider_name is None
    )
    if institution_owns_award:
        status = DiscoveryOfficialityStatus.OFFICIAL
        reason_code = "REVIEWED_INSTITUTION_CANONICAL_OWNER"
        detail = "Reviewed institution is the canonical owner for this target."
        trust_tier = 1
    elif registration.authority_class in {
        SourceAuthorityClass.CANONICAL_OWNER,
        SourceAuthorityClass.CO_OWNER,
        SourceAuthorityClass.SUPPORTING_INSTITUTION,
    }:
        status = DiscoveryOfficialityStatus.SUPPORTING_OFFICIAL
        reason_code = "REVIEWED_SUPPORTING_INSTITUTION"
        detail = "Reviewed institution supports local facts without umbrella authority."
        trust_tier = 3
    else:
        status = DiscoveryOfficialityStatus.UNRESOLVED
        reason_code = "AUTHORITY_OUTSIDE_OBJECTIVE_SCOPE"
        detail = "Reviewed institution authority does not cover this objective."
        trust_tier = None
    return _assessment(
        context_hash=context_hash,
        context_type=context_type,
        status=status,
        reason_code=reason_code,
        reason_detail=detail,
        classifier_version=classifier_version,
        normalized_url=normalized_url,
        registration=registration,
        trust_tier=trust_tier,
        context_provider_id=context_provider_id,
        context_institution_id=registration.institution_id,
    )


def _owner_mismatch_assessment(
    *,
    context_hash: str,
    context_type: str,
    registration: ReviewedOwnerDomain,
    classifier_version: str,
    normalized_url: str,
    reason_code: str,
    reason_detail: str,
    context_provider_id: uuid.UUID | None = None,
) -> ContextualOfficialityAssessment:
    return _assessment(
        context_hash=context_hash,
        context_type=context_type,
        status=DiscoveryOfficialityStatus.UNRESOLVED,
        reason_code=reason_code,
        reason_detail=reason_detail,
        classifier_version=classifier_version,
        normalized_url=normalized_url,
        registration=registration,
        context_provider_id=context_provider_id,
    )


def _assessment(
    *,
    context_hash: str,
    context_type: str,
    status: DiscoveryOfficialityStatus,
    reason_code: str,
    reason_detail: str,
    classifier_version: str,
    normalized_url: str,
    registration: ReviewedOwnerDomain | None = None,
    trust_tier: int | None = None,
    context_provider_id: uuid.UUID | None = None,
    context_institution_id: uuid.UUID | None = None,
) -> ContextualOfficialityAssessment:
    return ContextualOfficialityAssessment(
        assessment_context_hash=context_hash,
        context_type=context_type,
        officiality_status=status,
        owner_type=(registration.owner_type if registration else SourceOwnerType.UNKNOWN),
        owner_id=(registration.owner_id if registration else None),
        canonical_domain=(registration.domain if registration else None),
        authority_class=(registration.authority_class if registration else None),
        trust_tier=trust_tier,
        reason_code=reason_code,
        reason_detail=reason_detail,
        classifier_version=classifier_version,
        normalized_url=normalized_url,
        context_provider_id=context_provider_id,
        context_institution_id=context_institution_id,
    )


def _target_provider_id(
    target: DiscoveryTargetIdentitySnapshot,
    registrations: tuple[ReviewedOwnerDomain, ...],
) -> tuple[uuid.UUID | None, bool]:
    if target.provider_name is None:
        return None, False
    provider_ids = {
        registration.provider_id
        for registration in registrations
        if registration.provider_id is not None
        and registration.owner_type in {SourceOwnerType.PROVIDER, SourceOwnerType.GOVERNMENT}
        and _normalized_name(registration.owner_name_snapshot)
        == _normalized_name(target.provider_name)
    }
    if len(provider_ids) != 1:
        return None, len(provider_ids) > 1
    return next(iter(provider_ids)), False


def _institution_matches_scope(
    registration: ReviewedOwnerDomain,
    scope: DiscoveryScopeSnapshot,
    target: DiscoveryTargetIdentitySnapshot,
) -> bool:
    return bool(
        scope.institution_id is not None
        and registration.institution_id == scope.institution_id
        and target.institution_name is not None
        and _normalized_name(registration.owner_name_snapshot)
        == _normalized_name(target.institution_name)
    )


def _delegated_authority_supports(
    authority: SourceAuthorityClass,
    objective_kind: DiscoveryObjectiveKind,
) -> bool:
    if authority is SourceAuthorityClass.DELEGATED_OFFICIAL:
        return True
    allowed = {
        SourceAuthorityClass.APPLICATION_PORTAL: {
            DiscoveryObjectiveKind.APPLICATION_ROUTE,
            DiscoveryObjectiveKind.APPLICATION_STEPS,
            DiscoveryObjectiveKind.CURRENT_APPLICATION_DEADLINE,
            DiscoveryObjectiveKind.CURRENT_APPLICATION_OPENING,
        },
        SourceAuthorityClass.COUNTRY_MISSION: {
            DiscoveryObjectiveKind.APPLICATION_ROUTE,
            DiscoveryObjectiveKind.APPLICATION_STEPS,
            DiscoveryObjectiveKind.CURRENT_APPLICATION_DEADLINE,
            DiscoveryObjectiveKind.CURRENT_APPLICATION_OPENING,
            DiscoveryObjectiveKind.REQUIRED_DOCUMENTS,
        },
    }
    return objective_kind in allowed.get(authority, set())


def _assessment_context_hash(
    *,
    raw_url: str,
    normalized_url: str | None,
    objective_kind: DiscoveryObjectiveKind,
    scope: DiscoveryScopeSnapshot,
    target: DiscoveryTargetIdentitySnapshot,
    registrations: tuple[ReviewedOwnerDomain, ...],
    classifier_version: str,
) -> str:
    payload = {
        "classifier_version": classifier_version,
        "objective_kind": objective_kind.value,
        "owner_domains": [item.fingerprint_payload() for item in registrations],
        "scope": scope.model_dump(mode="json"),
        "schema_version": "catalogue-contextual-officiality-context.v1",
        "target": target.model_dump(mode="json"),
        "url_fingerprint": hashlib.sha256((normalized_url or raw_url).encode()).hexdigest(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _normalize_reviewed_domain(value: str) -> str:
    candidate = value.strip().casefold().strip(".")
    if not DOMAIN_PATTERN.fullmatch(candidate):
        raise ValueError("reviewed owner domain must be a bare public DNS name")
    result = normalize_discovery_lead_url(f"https://{candidate}")
    if result.normalized is None or result.normalized.port is not None:
        raise ValueError("reviewed owner domain must be a bare public DNS name")
    return result.normalized.host


def _same_or_subdomain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _uuid_text(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


def _registration_sort_key(registration: ReviewedOwnerDomain) -> tuple[str, ...]:
    return (
        registration.domain,
        registration.owner_type.value,
        _uuid_text(registration.owner_id) or "",
        registration.authority_class.value,
        _normalized_name(registration.owner_name_snapshot),
    )


def _authority_rank(registration: ReviewedOwnerDomain) -> tuple[int, tuple[str, ...]]:
    ranks = {
        SourceAuthorityClass.CANONICAL_OWNER: 0,
        SourceAuthorityClass.CO_OWNER: 1,
        SourceAuthorityClass.DELEGATED_OFFICIAL: 2,
        SourceAuthorityClass.APPLICATION_PORTAL: 3,
        SourceAuthorityClass.COUNTRY_MISSION: 4,
        SourceAuthorityClass.SUPPORTING_INSTITUTION: 5,
    }
    return ranks[registration.authority_class], _registration_sort_key(registration)
