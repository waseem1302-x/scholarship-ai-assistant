"""Deterministic service boundary for PR6 evidence-ledger persistence.

The service accepts already typed source claims, preserves immutable source
identity, validates exact evidence spans, and prevents cross-target/cross-snapshot
bundle bindings. It has no model-provider dependency and never writes canonical
graph facts or publication state.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import utc_now
from app.modules.catalogue_ingestion.claim_core import SourceClaim, claim_fingerprint
from app.modules.catalogue_ingestion.evidence_ledger_models import (
    CatalogueCandidateSourceSnapshot,
    CatalogueClaimEvidence,
    CatalogueEvidenceBundle,
    CatalogueEvidenceBundleClaim,
    CatalogueEvidenceBundleSource,
    CatalogueFieldClaim,
    CatalogueSnapshotPromotion,
    CatalogueSourceExtraction,
    ClaimEvidenceValidationStatus,
    LedgerIntegrityError,
    SourceExtractionStatus,
)
from app.modules.catalogue_ingestion.models import CatalogueCandidateSource
from app.modules.opportunities.evidence_models import (
    OfficialityStatus,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.models import Source


class LedgerBindingError(LedgerIntegrityError):
    """Raised when immutable ledger identities do not belong together."""


@dataclass(frozen=True, slots=True)
class PersistedSourceClaim:
    claim: CatalogueFieldClaim
    evidence: tuple[CatalogueClaimEvidence, ...]
    reused: bool


def attach_snapshot_to_bundle(
    session: Session,
    *,
    bundle_id: uuid.UUID,
    source_context_hash: str,
    normalized_url: str,
    domain: str,
    source_owner_type: SourceOwnerType,
    source_owner_id: uuid.UUID | None,
    officiality_status: OfficialityStatus,
    authority_class: str,
    authority_scope_snapshot: dict[str, Any],
    authority_policy_version: str,
    candidate_source_snapshot_id: uuid.UUID | None = None,
    source_snapshot_id: uuid.UUID | None = None,
) -> CatalogueEvidenceBundleSource:
    """Freeze one source context only when the snapshot belongs to the bundle target."""

    bundle = session.get(CatalogueEvidenceBundle, bundle_id)
    if bundle is None:
        raise LedgerBindingError("evidence bundle does not exist")

    snapshot_kind, snapshot_id = _snapshot_identity(
        candidate_source_snapshot_id,
        source_snapshot_id,
    )
    if snapshot_kind == "candidate":
        if bundle.candidate_id is None or bundle.opportunity_id is not None:
            raise LedgerBindingError("candidate snapshot requires a candidate evidence bundle")
        snapshot = session.get(CatalogueCandidateSourceSnapshot, snapshot_id)
        if snapshot is None:
            raise LedgerBindingError("candidate source snapshot does not exist")
        candidate_source = session.get(CatalogueCandidateSource, snapshot.candidate_source_id)
        if candidate_source is None or candidate_source.candidate_id != bundle.candidate_id:
            raise LedgerBindingError("candidate snapshot does not belong to bundle candidate")
        existing_query = select(CatalogueEvidenceBundleSource).where(
            CatalogueEvidenceBundleSource.bundle_id == bundle_id,
            CatalogueEvidenceBundleSource.candidate_source_snapshot_id == snapshot_id,
        )
    else:
        if bundle.opportunity_id is None or bundle.candidate_id is not None:
            raise LedgerBindingError("canonical snapshot requires an opportunity evidence bundle")
        snapshot = session.get(SourceSnapshot, snapshot_id)
        if snapshot is None:
            raise LedgerBindingError("canonical source snapshot does not exist")
        canonical_source = session.get(Source, snapshot.source_id)
        if canonical_source is None or canonical_source.opportunity_id != bundle.opportunity_id:
            raise LedgerBindingError("canonical snapshot does not belong to bundle opportunity")
        existing_query = select(CatalogueEvidenceBundleSource).where(
            CatalogueEvidenceBundleSource.bundle_id == bundle_id,
            CatalogueEvidenceBundleSource.source_snapshot_id == snapshot_id,
        )

    existing = session.scalar(existing_query)
    if existing is not None:
        _assert_same_source_context(
            existing,
            source_context_hash=source_context_hash,
            normalized_url=normalized_url,
            domain=domain,
            source_owner_type=source_owner_type,
            source_owner_id=source_owner_id,
            officiality_status=officiality_status,
            authority_class=authority_class,
            authority_scope_snapshot=authority_scope_snapshot,
            authority_policy_version=authority_policy_version,
        )
        return existing

    row = CatalogueEvidenceBundleSource(
        id=uuid.uuid4(),
        bundle_id=bundle_id,
        candidate_source_snapshot_id=(snapshot_id if snapshot_kind == "candidate" else None),
        source_snapshot_id=(snapshot_id if snapshot_kind == "canonical" else None),
        source_context_hash=source_context_hash,
        normalized_url=normalized_url,
        domain=domain,
        source_owner_type=source_owner_type,
        source_owner_id=source_owner_id,
        officiality_status=officiality_status,
        authority_class=authority_class,
        authority_scope_snapshot=authority_scope_snapshot,
        authority_policy_version=authority_policy_version,
    )
    session.add(row)
    return row


def persist_source_claim(
    session: Session,
    *,
    extraction_id: uuid.UUID,
    ordinal: int,
    claim: SourceClaim,
) -> PersistedSourceClaim:
    """Persist one strict source assertion without collapsing cross-source evidence."""

    extraction = session.get(CatalogueSourceExtraction, extraction_id)
    if extraction is None:
        raise LedgerBindingError("source extraction does not exist")
    if extraction.status is not SourceExtractionStatus.SUCCEEDED:
        raise LedgerBindingError("claims can only be persisted from a succeeded extraction")

    fingerprint = claim_fingerprint(claim)
    existing = session.scalar(
        select(CatalogueFieldClaim).where(
            CatalogueFieldClaim.source_extraction_id == extraction_id,
            CatalogueFieldClaim.claim_fingerprint == fingerprint,
        )
    )
    if existing is not None:
        evidence = tuple(
            session.scalars(
                select(CatalogueClaimEvidence)
                .where(CatalogueClaimEvidence.claim_id == existing.id)
                .order_by(CatalogueClaimEvidence.ordinal)
            )
        )
        return PersistedSourceClaim(existing, evidence, True)

    claim_id = uuid.uuid4()
    source_value_json = _model_json(claim.value)
    row = CatalogueFieldClaim(
        id=claim_id,
        source_extraction_id=extraction_id,
        ordinal=ordinal,
        claim_type=claim.claim_type,
        source_subject_json=_model_json(claim.subject),
        scope_hint_snapshot=claim.scope_hint.model_dump(mode="json", exclude_none=True),
        source_value_json=source_value_json,
        source_value_hash=(
            _sha256_json(source_value_json) if source_value_json is not None else None
        ),
        value_state=claim.value_state,
        claim_fingerprint=fingerprint,
    )
    evidence_rows = tuple(
        CatalogueClaimEvidence(
            id=uuid.uuid4(),
            claim_id=claim_id,
            ordinal=index,
            role=proposal.role,
            excerpt=proposal.excerpt,
            section_label=proposal.section_label,
            locator=proposal.locator,
            validation_status=ClaimEvidenceValidationStatus.PENDING,
        )
        for index, proposal in enumerate(claim.evidence)
    )
    session.add(row)
    session.add_all(evidence_rows)
    return PersistedSourceClaim(row, evidence_rows, False)


def bind_claim_to_bundle(
    session: Session,
    *,
    bundle_id: uuid.UUID,
    bundle_source_id: uuid.UUID,
    claim_id: uuid.UUID,
) -> CatalogueEvidenceBundleClaim:
    """Bind a reusable claim only to the exact snapshot context that produced it."""

    bundle_source = session.get(CatalogueEvidenceBundleSource, bundle_source_id)
    if bundle_source is None:
        raise LedgerBindingError("bundle source does not exist")
    if bundle_source.bundle_id != bundle_id:
        raise LedgerBindingError("bundle source belongs to a different evidence bundle")

    claim = session.get(CatalogueFieldClaim, claim_id)
    if claim is None:
        raise LedgerBindingError("claim does not exist")
    extraction = session.get(CatalogueSourceExtraction, claim.source_extraction_id)
    if extraction is None:
        raise LedgerBindingError("claim source extraction does not exist")

    extraction_identity = _snapshot_identity(
        extraction.candidate_source_snapshot_id,
        extraction.source_snapshot_id,
    )
    bundle_source_identity = _snapshot_identity(
        bundle_source.candidate_source_snapshot_id,
        bundle_source.source_snapshot_id,
    )
    if extraction_identity != bundle_source_identity:
        raise LedgerBindingError("claim and bundle source do not reference the same snapshot")

    existing = session.scalar(
        select(CatalogueEvidenceBundleClaim).where(
            CatalogueEvidenceBundleClaim.bundle_id == bundle_id,
            CatalogueEvidenceBundleClaim.claim_id == claim_id,
        )
    )
    if existing is not None:
        if existing.bundle_source_id != bundle_source_id:
            raise LedgerBindingError("claim is already bound to another source context in bundle")
        return existing

    row = CatalogueEvidenceBundleClaim(
        id=uuid.uuid4(),
        bundle_id=bundle_id,
        bundle_source_id=bundle_source_id,
        claim_id=claim_id,
    )
    session.add(row)
    return row


def validate_claim_evidence(
    session: Session,
    *,
    evidence_id: uuid.UUID,
) -> CatalogueClaimEvidence:
    """Locate one evidence excerpt exactly in the immutable extraction snapshot."""

    evidence = session.get(CatalogueClaimEvidence, evidence_id)
    if evidence is None:
        raise LedgerBindingError("claim evidence does not exist")
    if evidence.validation_status is not ClaimEvidenceValidationStatus.PENDING:
        raise LedgerBindingError("claim evidence has already reached a terminal state")

    claim = session.get(CatalogueFieldClaim, evidence.claim_id)
    if claim is None:
        raise LedgerBindingError("claim does not exist")
    extraction = session.get(CatalogueSourceExtraction, claim.source_extraction_id)
    if extraction is None:
        raise LedgerBindingError("claim source extraction does not exist")

    normalized_text = _load_extraction_text(session, extraction)
    offsets = _exact_occurrences(normalized_text, evidence.excerpt)
    evidence.validated_at = utc_now()

    if len(offsets) == 1:
        start = offsets[0]
        evidence.validation_status = ClaimEvidenceValidationStatus.MATCHED
        evidence.excerpt_start = start
        evidence.excerpt_end = start + len(evidence.excerpt)
        evidence.failure_code = None
    elif not offsets:
        evidence.validation_status = ClaimEvidenceValidationStatus.NOT_FOUND
        evidence.excerpt_start = None
        evidence.excerpt_end = None
        evidence.failure_code = "evidence_excerpt_not_found"
    else:
        evidence.validation_status = ClaimEvidenceValidationStatus.AMBIGUOUS
        evidence.excerpt_start = None
        evidence.excerpt_end = None
        evidence.failure_code = "evidence_excerpt_ambiguous"
    return evidence


def prepare_snapshot_promotion(
    session: Session,
    *,
    candidate_source_snapshot_id: uuid.UUID,
    source_snapshot_id: uuid.UUID,
    candidate_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    promotion_reason: str,
) -> CatalogueSnapshotPromotion:
    """Prepare exact candidate-to-canonical snapshot lineage without refetching bytes."""

    candidate_snapshot = session.get(
        CatalogueCandidateSourceSnapshot,
        candidate_source_snapshot_id,
    )
    canonical_snapshot = session.get(SourceSnapshot, source_snapshot_id)
    if candidate_snapshot is None or canonical_snapshot is None:
        raise LedgerBindingError("snapshot promotion requires both existing snapshots")

    candidate_source = session.get(
        CatalogueCandidateSource,
        candidate_snapshot.candidate_source_id,
    )
    if candidate_source is None or candidate_source.candidate_id != candidate_id:
        raise LedgerBindingError("candidate snapshot does not belong to candidate")

    canonical_source = session.get(Source, canonical_snapshot.source_id)
    if canonical_source is None or canonical_source.opportunity_id != opportunity_id:
        raise LedgerBindingError("canonical snapshot does not belong to opportunity")

    if candidate_snapshot.content_hash != canonical_snapshot.content_hash:
        raise LedgerBindingError("snapshot promotion hash mismatch")
    if candidate_snapshot.normalized_text != canonical_snapshot.normalized_text:
        raise LedgerBindingError("snapshot promotion normalized text mismatch")

    existing = session.scalar(
        select(CatalogueSnapshotPromotion).where(
            CatalogueSnapshotPromotion.candidate_source_snapshot_id == candidate_source_snapshot_id,
            CatalogueSnapshotPromotion.source_snapshot_id == source_snapshot_id,
        )
    )
    if existing is not None:
        if existing.candidate_id != candidate_id or existing.opportunity_id != opportunity_id:
            raise LedgerBindingError("existing promotion has different target identity")
        return existing

    row = CatalogueSnapshotPromotion(
        id=uuid.uuid4(),
        candidate_source_snapshot_id=candidate_source_snapshot_id,
        source_snapshot_id=source_snapshot_id,
        candidate_id=candidate_id,
        opportunity_id=opportunity_id,
        promotion_reason=promotion_reason,
    )
    session.add(row)
    return row


def _assert_same_source_context(
    existing: CatalogueEvidenceBundleSource,
    *,
    source_context_hash: str,
    normalized_url: str,
    domain: str,
    source_owner_type: SourceOwnerType,
    source_owner_id: uuid.UUID | None,
    officiality_status: OfficialityStatus,
    authority_class: str,
    authority_scope_snapshot: dict[str, Any],
    authority_policy_version: str,
) -> None:
    expected = (
        source_context_hash,
        normalized_url,
        domain,
        source_owner_type,
        source_owner_id,
        officiality_status,
        authority_class,
        _canonical_json(authority_scope_snapshot),
        authority_policy_version,
    )
    actual = (
        existing.source_context_hash,
        existing.normalized_url,
        existing.domain,
        existing.source_owner_type,
        existing.source_owner_id,
        existing.officiality_status,
        existing.authority_class,
        _canonical_json(existing.authority_scope_snapshot),
        existing.authority_policy_version,
    )
    if actual != expected:
        raise LedgerBindingError("bundle source already exists with different frozen context")


def _load_extraction_text(session: Session, extraction: CatalogueSourceExtraction) -> str:
    if extraction.candidate_source_snapshot_id is not None:
        snapshot = session.get(
            CatalogueCandidateSourceSnapshot,
            extraction.candidate_source_snapshot_id,
        )
    else:
        snapshot = session.get(SourceSnapshot, extraction.source_snapshot_id)
    if snapshot is None:
        raise LedgerBindingError("source extraction snapshot does not exist")
    return snapshot.normalized_text


def _snapshot_identity(
    candidate_source_snapshot_id: uuid.UUID | None,
    source_snapshot_id: uuid.UUID | None,
) -> tuple[str, uuid.UUID]:
    if candidate_source_snapshot_id is not None and source_snapshot_id is None:
        return ("candidate", candidate_source_snapshot_id)
    if candidate_source_snapshot_id is None and source_snapshot_id is not None:
        return ("canonical", source_snapshot_id)
    raise LedgerBindingError("snapshot identity must contain exactly one snapshot kind")


def _exact_occurrences(text: str, excerpt: str) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        found = text.find(excerpt, start)
        if found < 0:
            return offsets
        offsets.append(found)
        start = found + 1


def _model_json(value: Any | None) -> dict[str, Any] | None:
    if value is None:
        return None
    serialized = value.model_dump(mode="json")
    if not isinstance(serialized, dict):
        raise TypeError("typed claim model must serialize to an object")
    return serialized


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "LedgerBindingError",
    "PersistedSourceClaim",
    "attach_snapshot_to_bundle",
    "bind_claim_to_bundle",
    "persist_source_claim",
    "prepare_snapshot_promotion",
    "validate_claim_evidence",
]
