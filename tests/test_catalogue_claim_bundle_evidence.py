from app.modules.catalogue_ingestion.claim_bundle_provider import (
    CLAIM_BUNDLE_SYSTEM_INSTRUCTION,
    _bundle_azure_schema,
)
from app.modules.catalogue_ingestion.claim_bundle_schemas import (
    BundledAtomicClaim,
    BundleEvidenceReference,
    BundleObjectiveCoverage,
    ClaimBundleExtractionOutput,
    EvidenceBlockSpan,
    expand_claim_bundle,
)
from app.modules.catalogue_ingestion.claim_provider import (
    OBJECTIVE_ENTITY_TYPES,
    OBJECTIVE_FIELD_PATHS,
)
from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimObjective,
    ClaimScope,
    ClaimValue,
    ObjectiveCoverageState,
)


def _string_value(value: str) -> ClaimValue:
    return ClaimValue(
        string_value=value,
        decimal_value=None,
        integer_value=None,
        boolean_value=None,
        string_list_value=None,
    )


def _claim(
    *,
    objective: ClaimObjective,
    field_path: str,
    value: str,
    evidence_ref_id: str,
) -> BundledAtomicClaim:
    entity_type = (
        ClaimEntityType.FUNDING
        if objective is ClaimObjective.FUNDING
        else ClaimEntityType.SCHOLARSHIP
    )
    return BundledAtomicClaim(
        objective=objective,
        entity_type=entity_type,
        entity_key="root",
        field_path=field_path,
        value=_string_value(value),
        scope=ClaimScope(),
        evidence_ref_id=evidence_ref_id,
        basis="explicit",
    )


def _coverage(objective: ClaimObjective) -> BundleObjectiveCoverage:
    return BundleObjectiveCoverage(
        objective=objective,
        coverage_state=ObjectiveCoverageState.COMPLETE,
        unknown_objectives=[],
    )


def test_bundle_provider_schema_requests_quotes_without_character_offsets() -> None:
    schema = _bundle_azure_schema((ClaimObjective.IDENTITY,))

    reference_schema = schema["$defs"]["BundleEvidenceReference"]
    assert set(reference_schema["properties"]) == {"ref_id", "block_key", "excerpt"}
    assert set(reference_schema["required"]) == {"ref_id", "block_key", "excerpt"}


def test_bundle_prompt_does_not_give_conflicting_offset_instructions() -> None:
    assert "exact character offsets" not in CLAIM_BUNDLE_SYSTEM_INSTRUCTION
    assert "Do not calculate or\nreturn character offsets" in CLAIM_BUNDLE_SYSTEM_INSTRUCTION


def test_bundle_expansion_binds_whitespace_normalized_quote_to_exact_source_span() -> None:
    block_text = "Funding details: Tuition   fees\nare fully covered for award recipients."
    block = EvidenceBlockSpan(
        block_key="funding",
        start_offset=200,
        end_offset=200 + len(block_text),
        block_text=block_text,
    )
    output = ClaimBundleExtractionOutput(
        evidence_refs=[
            BundleEvidenceReference(
                ref_id="funding-ref",
                block_key="funding",
                excerpt="Tuition fees are fully covered",
            )
        ],
        claims=[
            _claim(
                objective=ClaimObjective.FUNDING,
                field_path="coverage_status",
                value="covered",
                evidence_ref_id="funding-ref",
            )
        ],
        objective_coverage=[_coverage(ClaimObjective.FUNDING)],
    )

    expanded = expand_claim_bundle(
        output,
        requested_objectives=(ClaimObjective.FUNDING,),
        blocks_by_key={"funding": block},
        allowed_entity_types=OBJECTIVE_ENTITY_TYPES,
        allowed_field_paths=OBJECTIVE_FIELD_PATHS,
    )

    claim = expanded.outputs[ClaimObjective.FUNDING].claims[0]
    exact_excerpt = "Tuition   fees\nare fully covered"
    assert claim.excerpt == exact_excerpt
    assert claim.excerpt_start == 200 + block_text.index(exact_excerpt)
    assert claim.excerpt_end == claim.excerpt_start + len(exact_excerpt)


def test_bundle_expansion_keeps_valid_claims_when_another_reference_is_invalid() -> None:
    block_text = "Open Doors Scholarship. Tuition is covered."
    block = EvidenceBlockSpan(
        block_key="official",
        start_offset=0,
        end_offset=len(block_text),
        block_text=block_text,
    )
    output = ClaimBundleExtractionOutput(
        evidence_refs=[
            BundleEvidenceReference(
                ref_id="identity-ref",
                block_key="official",
                excerpt="Open Doors Scholarship",
            ),
            BundleEvidenceReference(
                ref_id="invalid-funding-ref",
                block_key="official",
                excerpt="A monthly stipend is provided",
            ),
        ],
        claims=[
            _claim(
                objective=ClaimObjective.IDENTITY,
                field_path="name",
                value="Open Doors Scholarship",
                evidence_ref_id="identity-ref",
            ),
            _claim(
                objective=ClaimObjective.FUNDING,
                field_path="coverage_status",
                value="covered",
                evidence_ref_id="invalid-funding-ref",
            ),
        ],
        objective_coverage=[
            _coverage(ClaimObjective.IDENTITY),
            _coverage(ClaimObjective.FUNDING),
        ],
    )

    expanded = expand_claim_bundle(
        output,
        requested_objectives=(ClaimObjective.IDENTITY, ClaimObjective.FUNDING),
        blocks_by_key={"official": block},
        allowed_entity_types=OBJECTIVE_ENTITY_TYPES,
        allowed_field_paths=OBJECTIVE_FIELD_PATHS,
    )

    identity = expanded.outputs[ClaimObjective.IDENTITY]
    funding = expanded.outputs[ClaimObjective.FUNDING]
    assert len(identity.claims) == 1
    assert identity.coverage_state is ObjectiveCoverageState.COMPLETE
    assert funding.claims == []
    assert funding.coverage_state is ObjectiveCoverageState.PARTIAL
    assert "provider_invalid_claims_dropped:1" in funding.warnings
