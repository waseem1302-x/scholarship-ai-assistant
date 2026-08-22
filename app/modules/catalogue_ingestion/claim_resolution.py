"""Deterministic claim validation, conflict handling, and MEXT completeness gates."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable

from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimResolution,
    ExtractedClaim,
    ResolvedClaim,
)
from app.modules.catalogue_ingestion.models import CatalogueSourceArtifact


def resolve_claims(
    extracted: Iterable[tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]],
) -> ClaimResolution:
    candidates: dict[tuple[str, str, str, str], list[ResolvedClaim]] = defaultdict(list)
    rejected: list[str] = []
    for artifact, trust_tier, claims in extracted:
        for claim in claims:
            if not _valid_evidence_span(artifact.normalized_text, claim):
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:evidence_span_invalid"
                )
                continue
            scope_key = json.dumps(claim.scope.model_dump(), sort_keys=True)
            key = (claim.entity_type.value, claim.entity_key, claim.field_path, scope_key)
            candidates[key].append(
                ResolvedClaim(
                    claim=claim,
                    artifact_id=str(artifact.id),
                    source_id=str(artifact.source_id),
                    source_url=artifact.final_url,
                    content_hash=artifact.content_hash,
                    trust_tier=trust_tier,
                )
            )

    resolved: list[ResolvedClaim] = []
    conflicts: list[str] = []
    for key in sorted(candidates):
        values = candidates[key]
        best_tier = min(item.trust_tier for item in values)
        best = [item for item in values if item.trust_tier == best_tier]
        by_value: dict[str, list[ResolvedClaim]] = defaultdict(list)
        for item in best:
            normalized = json.dumps(
                item.claim.value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )
            by_value[normalized].append(item)
        if len(by_value) > 1:
            conflicts.append(":".join(key[:3]) + ":same_tier_conflict")
            continue
        seen_evidence: set[tuple[str, int, int]] = set()
        for item in next(iter(by_value.values())):
            evidence_key = (
                item.artifact_id,
                item.claim.excerpt_start,
                item.claim.excerpt_end,
            )
            if evidence_key not in seen_evidence:
                resolved.append(item)
                seen_evidence.add(evidence_key)

    scoped_types = {
        ClaimEntityType.DEADLINE,
        ClaimEntityType.FUNDING,
        ClaimEntityType.DOCUMENT,
        ClaimEntityType.STEP,
    }
    scopes_by_key: dict[tuple[ClaimEntityType, str, str], set[str]] = defaultdict(set)
    for item in resolved:
        claim = item.claim
        if claim.entity_type in scoped_types:
            scopes_by_key[(claim.entity_type, claim.entity_key, claim.field_path)].add(
                json.dumps(claim.scope.model_dump(), sort_keys=True)
            )
    for key, scopes in sorted(
        scopes_by_key.items(), key=lambda item: tuple(str(value) for value in item[0])
    ):
        if len(scopes) > 1:
            conflicts.append(f"{key[0].value}:{key[1]}:{key[2]}:ambiguous_scope_key")

    completeness = mext_completeness_errors(resolved)
    return ClaimResolution(
        resolved=resolved,
        conflicts=conflicts,
        rejected=rejected,
        completeness_errors=completeness,
    )


def mext_completeness_errors(claims: list[ResolvedClaim]) -> list[str]:
    present = {(item.claim.entity_type, item.claim.field_path) for item in claims}
    errors: list[str] = []
    required = {
        (ClaimEntityType.SCHOLARSHIP, "name"),
        (ClaimEntityType.SCHOLARSHIP, "provider_name"),
        (ClaimEntityType.SCHOLARSHIP, "country_code"),
        (ClaimEntityType.SCHOLARSHIP, "degree_levels"),
        (ClaimEntityType.CYCLE, "intake_year"),
    }
    for entity_type, field_path in sorted(required, key=lambda item: (item[0].value, item[1])):
        if (entity_type, field_path) not in present:
            errors.append(f"missing:{entity_type.value}.{field_path}")

    track_keys = {
        item.claim.entity_key
        for item in claims
        if item.claim.entity_type is ClaimEntityType.TRACK and item.claim.field_path == "name"
    }
    for route in ("embassy_recommendation", "university_recommendation"):
        if route not in track_keys:
            errors.append(f"missing:track.{route}")

    for entity_type in (
        ClaimEntityType.FUNDING,
        ClaimEntityType.DOCUMENT,
        ClaimEntityType.STEP,
    ):
        if not any(item.claim.entity_type is entity_type for item in claims):
            errors.append(f"missing:{entity_type.value}")
    return errors


def _valid_evidence_span(text: str, claim: ExtractedClaim) -> bool:
    return (
        claim.excerpt_end <= len(text)
        and text[claim.excerpt_start : claim.excerpt_end] == claim.excerpt
    )
