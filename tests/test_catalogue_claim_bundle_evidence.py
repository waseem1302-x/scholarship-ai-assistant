import uuid

from app.modules.catalogue_ingestion.claim_bundle_provider import (
    CLAIM_BUNDLE_SYSTEM_INSTRUCTION,
    _bundle_azure_schema,
)
from app.modules.catalogue_ingestion.claim_bundle_schemas import (
    BundledAtomicClaim,
    BundleEvidenceDisposition,
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
    ClaimResolution,
    ClaimScope,
    ClaimValue,
    EvidenceDispositionState,
    EvidenceUnitDisposition,
    ExtractedClaim,
    ObjectiveCoverageState,
    ResolvedClaim,
)
from app.modules.catalogue_ingestion.evidence_block_models import CatalogueEvidenceBlock
from app.modules.catalogue_ingestion.production_service import _build_evidence_ledger
from app.modules.catalogue_ingestion.scoped_completeness import apply_evidence_accounting


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
    assert "unit_dispositions" in schema["required"]


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


def test_bundle_expansion_accounts_for_every_supplied_evidence_unit() -> None:
    mapped_text = "Tuition fees are fully covered."
    unresolved_text = "Appeals may be submitted within two days."
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
        unit_dispositions=[
            BundleEvidenceDisposition(
                block_key="funding",
                state=EvidenceDispositionState.MAPPED,
                reason="funding claim emitted",
            ),
            BundleEvidenceDisposition(
                block_key="appeals",
                state=EvidenceDispositionState.MAPPED,
                reason="incorrectly claimed as mapped",
            ),
        ],
    )

    expanded = expand_claim_bundle(
        output,
        requested_objectives=(ClaimObjective.FUNDING,),
        blocks_by_key={
            "funding": EvidenceBlockSpan(
                block_key="funding",
                start_offset=0,
                end_offset=len(mapped_text),
                block_text=mapped_text,
            ),
            "appeals": EvidenceBlockSpan(
                block_key="appeals",
                start_offset=100,
                end_offset=100 + len(unresolved_text),
                block_text=unresolved_text,
            ),
        },
        allowed_entity_types=OBJECTIVE_ENTITY_TYPES,
        allowed_field_paths=OBJECTIVE_FIELD_PATHS,
    )

    assert [item.state for item in expanded.dispositions] == [
        EvidenceDispositionState.MAPPED,
        EvidenceDispositionState.UNRESOLVED,
    ]
    assert expanded.outputs[ClaimObjective.FUNDING].coverage_state is ObjectiveCoverageState.PARTIAL
    assert "unit_disposition_without_accepted_claim:appeals" in expanded.warnings


def test_student_relevant_fact_without_a_typed_field_is_preserved_as_guidance() -> None:
    text = "Foreign students may work in Russia without obtaining a work permit."
    output = ClaimBundleExtractionOutput(
        evidence_refs=[
            BundleEvidenceReference(ref_id="work-ref", block_key="work", excerpt=text)
        ],
        claims=[
            BundledAtomicClaim(
                objective=ClaimObjective.FUNDING,
                entity_type=ClaimEntityType.GUIDANCE,
                entity_key="student_work_rights",
                field_path="text",
                value=_string_value(text),
                scope=ClaimScope(),
                evidence_ref_id="work-ref",
                basis="explicit",
            )
        ],
        objective_coverage=[_coverage(ClaimObjective.FUNDING)],
        unit_dispositions=[
            BundleEvidenceDisposition(
                block_key="work",
                state=EvidenceDispositionState.MAPPED,
                reason="preserved as student guidance",
            )
        ],
    )

    expanded = expand_claim_bundle(
        output,
        requested_objectives=(ClaimObjective.FUNDING,),
        blocks_by_key={
            "work": EvidenceBlockSpan(
                block_key="work",
                start_offset=0,
                end_offset=len(text),
                block_text=text,
            )
        },
        allowed_entity_types=OBJECTIVE_ENTITY_TYPES,
        allowed_field_paths=OBJECTIVE_FIELD_PATHS,
    )

    claim = expanded.outputs[ClaimObjective.FUNDING].claims[0]
    assert claim.entity_type is ClaimEntityType.GUIDANCE
    assert claim.field_path == "text"
    assert claim.value.primitive() == text


def test_unresolved_evidence_unit_prevents_model_reported_completeness() -> None:
    resolution = ClaimResolution(
        resolved=[],
        conflicts=[],
        rejected=[],
        completeness_errors=[],
        provider_objective_coverage={ClaimObjective.FUNDING.value: "complete"},
    )

    accounted = apply_evidence_accounting(
        resolution,
        [
            EvidenceUnitDisposition(
                block_key="funding-gap",
                state=EvidenceDispositionState.UNRESOLVED,
                reason="routed unit produced no accepted claim",
                objectives=[ClaimObjective.FUNDING],
            )
        ],
    )

    assert accounted.completeness_errors == ["evidence_unit:funding-gap:unresolved"]
    assert accounted.is_materializable is False


def test_terminal_evidence_dispositions_do_not_create_false_completeness_errors() -> None:
    resolution = ClaimResolution(
        resolved=[],
        conflicts=[],
        rejected=[],
        completeness_errors=[],
    )

    accounted = apply_evidence_accounting(
        resolution,
        [
            EvidenceUnitDisposition(
                block_key="navigation",
                state=EvidenceDispositionState.IRRELEVANT,
                reason="no relevant objective",
            )
        ],
    )

    assert accounted.completeness_errors == []
    assert accounted.evidence_dispositions[0].state is EvidenceDispositionState.IRRELEVANT


def test_final_evidence_ledger_checks_dispositions_against_resolved_claims() -> None:
    artifact_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    source_id = uuid.uuid4()

    def block(index: int, text: str) -> CatalogueEvidenceBlock:
        start = index * 100
        return CatalogueEvidenceBlock(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            source_id=source_id,
            source_artifact_id=artifact_id,
            block_index=index,
            block_key=str(index + 1) * 64,
            block_hash=str(index + 4) * 64,
            source_content_hash="a" * 64,
            start_offset=start,
            end_offset=start + len(text),
            block_text=text,
            heading=None,
            section_key=f"unit-{index}",
            coordinate_json=[],
            topology_hints=[],
            language_hints=["en"],
            source_role="primary",
        )

    mapped = block(0, "Tuition is covered.")
    omitted = block(1, "Appeals are allowed.")
    navigation = block(2, "Back to top")
    accepted_claim = ExtractedClaim(
        entity_type=ClaimEntityType.FUNDING,
        entity_key="tuition",
        field_path="coverage_status",
        value=_string_value("covered"),
        scope=ClaimScope(),
        excerpt=mapped.block_text,
        excerpt_start=mapped.start_offset,
        excerpt_end=mapped.end_offset,
        basis="explicit",
    )
    resolution = ClaimResolution(
        resolved=[
            ResolvedClaim(
                claim=accepted_claim,
                artifact_id=str(artifact_id),
                source_id=str(source_id),
                source_url="https://example.edu/scholarship",
                content_hash="a" * 64,
                trust_tier=1,
            )
        ],
        conflicts=[],
        rejected=[],
        completeness_errors=[],
    )

    ledger = _build_evidence_ledger(
        blocks=[mapped, omitted, navigation],
        selected_block_ids={mapped.id, omitted.id},
        reported=[
            EvidenceUnitDisposition(
                block_key=omitted.block_key,
                state=EvidenceDispositionState.MAPPED,
                reason="provider claimed it was mapped",
                objectives=[ClaimObjective.APPLICATION_TIMELINE],
            )
        ],
        resolution=resolution,
    )

    assert [item.state for item in ledger] == [
        EvidenceDispositionState.MAPPED,
        EvidenceDispositionState.UNRESOLVED,
        EvidenceDispositionState.IRRELEVANT,
    ]
