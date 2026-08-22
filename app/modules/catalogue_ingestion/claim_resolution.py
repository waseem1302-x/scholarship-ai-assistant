"""Deterministic claim validation, conflict handling, and MEXT completeness gates."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable

from app.modules.catalogue_ingestion.claim_schemas import (
    SUPPORTED_CLAIM_FIELDS,
    ClaimEntityType,
    ClaimResolution,
    ExtractedClaim,
    ResolvedClaim,
)
from app.modules.catalogue_ingestion.models import CatalogueSourceArtifact


def resolve_claims(
    extracted: Iterable[tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]],
) -> ClaimResolution:
    extracted_items = list(extracted)
    cycle_aliases = _cycle_aliases(extracted_items)
    candidates: dict[tuple[str, str, str, str], list[ResolvedClaim]] = defaultdict(list)
    rejected: list[str] = []
    for artifact, trust_tier, claims in extracted_items:
        for claim in claims:
            if claim.field_path not in SUPPORTED_CLAIM_FIELDS[claim.entity_type]:
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:unsupported_field_path"
                )
                continue
            if not _valid_evidence_span(artifact.normalized_text, claim):
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:evidence_span_invalid"
                )
                continue
            semantic_error = _semantic_claim_error(claim)
            if semantic_error is not None:
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:{semantic_error}"
                )
                continue
            claim = _canonicalize_cycle_aliases(claim, cycle_aliases)
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

    intake_years = {
        str(item.claim.value.primitive())
        for item in resolved
        if item.claim.entity_type is ClaimEntityType.CYCLE
        and item.claim.field_path == "intake_year"
    }
    scoped_cycles = {
        item.claim.scope.cycle_key for item in resolved if item.claim.scope.cycle_key is not None
    }
    if len(intake_years) > 1:
        conflicts.append("cycle:intake_year:multiple_cycles")
    if len(scoped_cycles) > 1:
        conflicts.append("cycle:scope:multiple_cycles")

    completeness = mext_completeness_errors(resolved)
    return ClaimResolution(
        resolved=resolved,
        conflicts=sorted(set(conflicts)),
        rejected=rejected,
        completeness_errors=completeness,
    )


def _cycle_aliases(
    extracted: list[tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]],
) -> dict[str, int]:
    years_by_alias: dict[str, set[int]] = defaultdict(set)
    for artifact, _trust_tier, claims in extracted:
        for claim in claims:
            if (
                claim.entity_type is ClaimEntityType.CYCLE
                and claim.field_path == "intake_year"
                and _valid_evidence_span(artifact.normalized_text, claim)
                and _semantic_claim_error(claim) is None
            ):
                value = claim.value.primitive()
                if isinstance(value, int):
                    years_by_alias[claim.entity_key].add(value)
    return {alias: next(iter(years)) for alias, years in years_by_alias.items() if len(years) == 1}


def _canonicalize_cycle_aliases(
    claim: ExtractedClaim, cycle_aliases: dict[str, int]
) -> ExtractedClaim:
    entity_key = claim.entity_key
    if claim.entity_type is ClaimEntityType.CYCLE and entity_key in cycle_aliases:
        entity_key = f"intake_{cycle_aliases[entity_key]}"
    scope = claim.scope
    if scope.cycle_key in cycle_aliases:
        scope = scope.model_copy(update={"cycle_key": f"intake_{cycle_aliases[scope.cycle_key]}"})
    if entity_key == claim.entity_key and scope is claim.scope:
        return claim
    return claim.model_copy(update={"entity_key": entity_key, "scope": scope})


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


def _semantic_claim_error(claim: ExtractedClaim) -> str | None:
    excerpt = claim.excerpt.casefold()
    if claim.entity_type is ClaimEntityType.CYCLE and claim.field_path == "intake_year":
        value = claim.value.primitive()
        if not isinstance(value, int) or str(value) not in excerpt:
            return "intake_year_evidence_mismatch"
        if not re.search(
            r"\b(?:academic|application|arrival|arrive|arriving|fiscal|fy|intake|recruit)",
            excerpt,
        ):
            return "intake_year_context_missing"
    if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "name":
        if claim.entity_key == "embassy_recommendation" and not (
            "embassy" in excerpt and "recommend" in excerpt
        ):
            return "embassy_route_evidence_mismatch"
        if claim.entity_key == "university_recommendation" and not (
            "university" in excerpt and "recommend" in excerpt
        ):
            return "university_route_evidence_mismatch"
    if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "track_type":
        if claim.entity_key == "embassy_recommendation" and not (
            ("embassy" in excerpt and "recommend" in excerpt) or "diplomatic mission" in excerpt
        ):
            return "embassy_route_evidence_mismatch"
        if claim.entity_key == "university_recommendation" and not (
            "university" in excerpt and "recommend" in excerpt
        ):
            return "university_route_evidence_mismatch"
    return None
