"""Strict multi-objective claim bundles with shared evidence references."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pydantic import Field, model_validator

from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimExtractionOutput,
    ClaimObjective,
    ClaimScope,
    ClaimValue,
    EvidenceDispositionState,
    EvidenceUnitDisposition,
    ExtractedClaim,
    ObjectiveCoverageState,
    StrictClaimModel,
)

CLAIM_BUNDLE_SCHEMA_VERSION = "catalogue-claim-bundle.v4"


class BundleEvidenceReference(StrictClaimModel):
    ref_id: str = Field(min_length=1, max_length=100)
    block_key: str = Field(min_length=1, max_length=64)
    excerpt: str = Field(min_length=1)
    excerpt_start: int | None = Field(default=None, ge=0)
    excerpt_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_span(self) -> BundleEvidenceReference:
        if (self.excerpt_start is None) != (self.excerpt_end is None):
            raise ValueError("Bundle evidence offsets must both be present or both be omitted")
        if (
            self.excerpt_start is not None
            and self.excerpt_end is not None
            and self.excerpt_end <= self.excerpt_start
        ):
            raise ValueError("Bundle evidence span must be non-empty")
        return self


class BundledAtomicClaim(StrictClaimModel):
    objective: ClaimObjective
    entity_type: ClaimEntityType
    entity_key: str = Field(min_length=1, max_length=120)
    field_path: str = Field(min_length=1, max_length=255)
    value: ClaimValue
    scope: ClaimScope
    evidence_ref_id: str = Field(min_length=1, max_length=100)
    basis: str

    @model_validator(mode="after")
    def valid_basis(self) -> BundledAtomicClaim:
        if self.basis not in {"explicit", "normalized"}:
            raise ValueError("Claim basis must be explicit or normalized")
        return self


class BundleObjectiveCoverage(StrictClaimModel):
    objective: ClaimObjective
    coverage_state: ObjectiveCoverageState
    unknown_objectives: list[str] = Field(default_factory=list)


class BundleEvidenceDisposition(StrictClaimModel):
    block_key: str = Field(min_length=1, max_length=64)
    state: EvidenceDispositionState
    reason: str = Field(min_length=1, max_length=500)
    duplicate_of_block_key: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def valid_duplicate_target(self) -> BundleEvidenceDisposition:
        if self.state is EvidenceDispositionState.DUPLICATE:
            if not self.duplicate_of_block_key or self.duplicate_of_block_key == self.block_key:
                raise ValueError("Duplicate evidence disposition requires another block key")
        elif self.duplicate_of_block_key is not None:
            raise ValueError("Only duplicate evidence dispositions may name a duplicate target")
        return self


class ClaimBundleExtractionOutput(StrictClaimModel):
    evidence_refs: list[BundleEvidenceReference]
    claims: list[BundledAtomicClaim]
    objective_coverage: list[BundleObjectiveCoverage]
    unit_dispositions: list[BundleEvidenceDisposition] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def internally_consistent(self) -> ClaimBundleExtractionOutput:
        ref_ids = [item.ref_id for item in self.evidence_refs]
        if len(ref_ids) != len(set(ref_ids)):
            raise ValueError("Bundle evidence reference IDs must be unique")
        coverage_objectives = [item.objective for item in self.objective_coverage]
        if len(coverage_objectives) != len(set(coverage_objectives)):
            raise ValueError("Bundle objective coverage entries must be unique")
        known = set(ref_ids)
        if any(claim.evidence_ref_id not in known for claim in self.claims):
            raise ValueError("Every bundled claim must reference a declared evidence reference")
        disposition_keys = [item.block_key for item in self.unit_dispositions]
        if len(disposition_keys) != len(set(disposition_keys)):
            raise ValueError("Bundle evidence dispositions must be unique per block")
        return self


@dataclass(frozen=True, slots=True)
class EvidenceBlockSpan:
    block_key: str
    start_offset: int
    end_offset: int
    block_text: str
    objectives: tuple[ClaimObjective, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpandedClaimBundle:
    outputs: Mapping[ClaimObjective, ClaimExtractionOutput]
    warnings: tuple[str, ...]
    dispositions: tuple[EvidenceUnitDisposition, ...]


def expand_claim_bundle(
    output: ClaimBundleExtractionOutput,
    *,
    requested_objectives: Iterable[ClaimObjective],
    blocks_by_key: Mapping[str, EvidenceBlockSpan],
    allowed_entity_types: Mapping[ClaimObjective, frozenset[ClaimEntityType]],
    allowed_field_paths: Mapping[ClaimObjective, frozenset[str]],
    max_claims_per_objective: int | None = None,
) -> ExpandedClaimBundle:
    """Expand shared references into independently-validatable atomic claim outputs."""

    requested = tuple(dict.fromkeys(requested_objectives))
    requested_set = set(requested)
    warnings = list(output.warnings)
    refs: dict[str, BundleEvidenceReference] = {}
    invalid_ref_ids: set[str] = set()
    for ref in output.evidence_refs:
        block = blocks_by_key.get(ref.block_key)
        if block is None:
            invalid_ref_ids.add(ref.ref_id)
            warnings.append(f"unknown_evidence_block:{ref.ref_id}")
            continue
        bound = _bind_reference(ref, block)
        if bound is None:
            invalid_ref_ids.add(ref.ref_id)
            warnings.append(f"invalid_evidence_span:{ref.ref_id}")
            continue
        refs[ref.ref_id] = bound

    claims_by_objective: dict[ClaimObjective, list[ExtractedClaim]] = {
        objective: [] for objective in requested
    }
    dropped_by_objective: dict[ClaimObjective, int] = {objective: 0 for objective in requested}
    accepted_blocks: set[str] = set()
    for bundled in output.claims:
        objective = bundled.objective
        if objective not in requested_set:
            warnings.append(f"unrequested_objective_claim:{objective.value}")
            continue
        ref = refs.get(bundled.evidence_ref_id)
        if ref is None:
            dropped_by_objective[objective] += 1
            continue
        if bundled.entity_type not in allowed_entity_types[objective]:
            dropped_by_objective[objective] += 1
            warnings.append(
                f"objective_entity_mismatch:{objective.value}:{bundled.entity_type.value}"
            )
            continue
        try:
            claim = ExtractedClaim(
                entity_type=bundled.entity_type,
                entity_key=bundled.entity_key,
                field_path=bundled.field_path,
                value=bundled.value,
                scope=bundled.scope,
                excerpt=ref.excerpt,
                excerpt_start=ref.excerpt_start,
                excerpt_end=ref.excerpt_end,
                basis=bundled.basis,
            )
        except ValueError:
            dropped_by_objective[objective] += 1
            warnings.append(f"invalid_atomic_claim:{objective.value}:{bundled.entity_key}")
            continue
        allowed_fields = allowed_field_paths.get(objective)
        if allowed_fields is not None and claim.field_path not in allowed_fields:
            dropped_by_objective[objective] += 1
            warnings.append(f"objective_field_mismatch:{objective.value}:{claim.field_path}")
            continue
        claims_by_objective[objective].append(claim)
        accepted_blocks.add(ref.block_key)

    supplied_dispositions = {item.block_key: item for item in output.unit_dispositions}
    dispositions: list[EvidenceUnitDisposition] = []
    unresolved_blocks: list[str] = []
    for block_key, block in blocks_by_key.items():
        supplied = supplied_dispositions.get(block_key)
        state = supplied.state if supplied is not None else (
            EvidenceDispositionState.MAPPED
            if block_key in accepted_blocks
            else EvidenceDispositionState.UNRESOLVED
        )
        reason = supplied.reason if supplied is not None else "legacy disposition inferred"
        duplicate_of = supplied.duplicate_of_block_key if supplied is not None else None
        if state is EvidenceDispositionState.MAPPED and block_key not in accepted_blocks:
            state = EvidenceDispositionState.UNRESOLVED
            duplicate_of = None
            reason = "mapped disposition had no accepted evidence-bound claim"
            warnings.append(f"unit_disposition_without_accepted_claim:{block_key}")
        if state is EvidenceDispositionState.DUPLICATE:
            target = blocks_by_key.get(duplicate_of or "")
            if target is None or _normalized_unit_text(target.block_text) != _normalized_unit_text(
                block.block_text
            ):
                state = EvidenceDispositionState.UNRESOLVED
                duplicate_of = None
                reason = "duplicate disposition did not match its canonical unit"
                warnings.append(f"invalid_duplicate_disposition:{block_key}")
        if state is EvidenceDispositionState.UNRESOLVED:
            unresolved_blocks.append(block_key)
        dispositions.append(
            EvidenceUnitDisposition(
                block_key=block_key,
                state=state,
                reason=reason,
                objectives=list(block.objectives or requested),
                duplicate_of_block_key=duplicate_of,
            )
        )
    for block_key in sorted(set(supplied_dispositions) - set(blocks_by_key)):
        warnings.append(f"unknown_unit_disposition:{block_key}")

    coverage = {item.objective: item for item in output.objective_coverage}
    expanded: dict[ClaimObjective, ClaimExtractionOutput] = {}
    for objective in requested:
        claims = claims_by_objective[objective]
        dropped = dropped_by_objective[objective]
        coverage_item = coverage.get(objective)
        state = (
            coverage_item.coverage_state
            if coverage_item is not None
            else ObjectiveCoverageState.PARTIAL
        )
        unknown = list(coverage_item.unknown_objectives) if coverage_item is not None else []
        objective_warnings: list[str] = []
        if max_claims_per_objective is not None and len(claims) > max_claims_per_objective:
            objective_warnings.append(
                f"claim_limit_applied:{len(claims)}:{max_claims_per_objective}"
            )
            claims = claims[:max_claims_per_objective]
            state = ObjectiveCoverageState.PARTIAL
            unknown.append("Provider output exceeded the per-objective atomic claim limit")
        if dropped:
            state = ObjectiveCoverageState.PARTIAL
            objective_warnings.append(f"provider_invalid_claims_dropped:{dropped}")
            unknown.append("One or more requested facts had invalid objective or evidence binding")
        if coverage_item is None:
            objective_warnings.append("provider_objective_coverage_missing")
            unknown.append("Provider omitted objective coverage state")
        if unresolved_blocks:
            state = ObjectiveCoverageState.PARTIAL
            objective_warnings.extend(
                f"unresolved_evidence_unit:{block_key}" for block_key in unresolved_blocks
            )
            unknown.append("One or more routed evidence units remain unresolved")
        expanded[objective] = ClaimExtractionOutput(
            objective=objective,
            coverage_state=state,
            claims=claims,
            unknown_objectives=list(dict.fromkeys(unknown)),
            conflicts=list(output.conflicts),
            warnings=list(dict.fromkeys([*warnings, *objective_warnings])),
        )
    return ExpandedClaimBundle(
        outputs=expanded,
        warnings=tuple(dict.fromkeys(warnings)),
        dispositions=tuple(dispositions),
    )


def _normalized_unit_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _bind_reference(
    ref: BundleEvidenceReference,
    block: EvidenceBlockSpan,
) -> BundleEvidenceReference | None:
    if (
        ref.excerpt_start is not None
        and ref.excerpt_end is not None
        and block.start_offset <= ref.excerpt_start < ref.excerpt_end <= block.end_offset
    ):
        local_start = ref.excerpt_start - block.start_offset
        local_end = ref.excerpt_end - block.start_offset
        if block.block_text[local_start:local_end] == ref.excerpt:
            return ref
    return _find_unique_reference(ref, block)


def _find_unique_reference(
    ref: BundleEvidenceReference,
    block: EvidenceBlockSpan,
) -> BundleEvidenceReference | None:
    exact_starts = _match_starts(block.block_text, ref.excerpt)
    if len(exact_starts) == 1:
        local_start = exact_starts[0]
        local_end = local_start + len(ref.excerpt)
    elif exact_starts:
        return None
    else:
        normalized_text, source_starts, source_ends = _normalize_whitespace(block.block_text)
        normalized_excerpt, _, _ = _normalize_whitespace(ref.excerpt)
        if not normalized_excerpt:
            return None
        normalized_starts = _match_starts(normalized_text, normalized_excerpt)
        if len(normalized_starts) != 1:
            return None
        normalized_start = normalized_starts[0]
        normalized_end = normalized_start + len(normalized_excerpt)
        local_start = source_starts[normalized_start]
        local_end = source_ends[normalized_end - 1]
    start = block.start_offset + local_start
    exact_excerpt = block.block_text[local_start:local_end]
    return ref.model_copy(
        update={
            "excerpt": exact_excerpt,
            "excerpt_start": start,
            "excerpt_end": block.start_offset + local_end,
        }
    )


def _match_starts(text: str, excerpt: str) -> list[int]:
    starts: list[int] = []
    position = text.find(excerpt)
    while position >= 0 and len(starts) < 2:
        starts.append(position)
        position = text.find(excerpt, position + 1)
    return starts


def _normalize_whitespace(text: str) -> tuple[str, list[int], list[int]]:
    normalized: list[str] = []
    source_starts: list[int] = []
    source_ends: list[int] = []
    for index, character in enumerate(text):
        if character.isspace():
            if not normalized or normalized[-1] == " ":
                if normalized:
                    source_ends[-1] = index + 1
                continue
            normalized.append(" ")
            source_starts.append(index)
            source_ends.append(index + 1)
            continue
        normalized.append(character)
        source_starts.append(index)
        source_ends.append(index + 1)
    if normalized and normalized[-1] == " ":
        normalized.pop()
        source_starts.pop()
        source_ends.pop()
    return "".join(normalized), source_starts, source_ends


__all__ = [
    "CLAIM_BUNDLE_SCHEMA_VERSION",
    "BundleEvidenceDisposition",
    "BundleEvidenceReference",
    "BundleObjectiveCoverage",
    "BundledAtomicClaim",
    "ClaimBundleExtractionOutput",
    "EvidenceBlockSpan",
    "ExpandedClaimBundle",
    "expand_claim_bundle",
]
