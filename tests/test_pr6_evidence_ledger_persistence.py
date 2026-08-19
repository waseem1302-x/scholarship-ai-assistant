import hashlib
import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import utc_now
from app.modules.catalogue_ingestion.claim_core import (
    ClaimType,
    EvidenceProposal,
    EvidenceRole,
    SourceClaim,
    TemporalClaimValue,
    TemporalPrecision,
)
from app.modules.catalogue_ingestion.evidence_ledger import (
    LedgerBindingError,
    attach_snapshot_to_bundle,
    bind_claim_to_bundle,
    persist_source_claim,
    validate_claim_evidence,
)
from app.modules.catalogue_ingestion.evidence_ledger_models import (
    CatalogueCandidateSourceSnapshot,
    CatalogueEvidenceBundle,
    CatalogueEvidenceBundleClaim,
    CatalogueFieldClaim,
    CatalogueSourceExtraction,
    CatalogueSourceExtractionAttempt,
    ClaimEvidenceValidationStatus,
    EvidenceBundleStatus,
    LedgerIntegrityError,
    SourceExtractionAttemptStatus,
    SourceExtractionStatus,
)
from app.modules.catalogue_ingestion.models import (
    CandidateSourceStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.opportunities.evidence_models import OfficialityStatus, SourceOwnerType


_PR6_LEDGER_METADATA = CatalogueCandidateSourceSnapshot.__table__.metadata
_PR6_LEDGER_TABLES = tuple(
    mapper.local_table
    for mapper in CatalogueCandidateSourceSnapshot.__mapper__.registry.mappers
    if mapper.class_.__module__ == CatalogueCandidateSourceSnapshot.__module__
)


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for PR6 persistence tests")

    engine = create_engine(database_url, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    _PR6_LEDGER_METADATA.create_all(engine, tables=_PR6_LEDGER_TABLES)
    yield engine
    _PR6_LEDGER_METADATA.drop_all(engine, tables=_PR6_LEDGER_TABLES)
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine):
    connection = postgres_engine.connect()
    transaction = connection.begin()
    try:
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
            yield session
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _create_candidate(db_session: Session, *, label: str) -> CatalogueCandidate:
    run_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    run = CatalogueIngestionRun(
        id=run_id,
        source_label=f"PR6 persistence test {label}",
        source_fingerprint=_hash(f"source:{label}"),
        mode=IngestionMode.CANDIDATE_ONLY,
        status=IngestionRunStatus.PENDING,
        max_candidates=10,
        max_pages_per_candidate=10,
        max_model_calls=10,
        max_input_characters=100_000,
        max_output_tokens=10_000,
        max_estimated_cost=Decimal("10"),
    )
    candidate = CatalogueCandidate(
        id=candidate_id,
        run_id=run_id,
        seed_index=0,
        idempotency_key=_hash(f"candidate:{label}"),
        seed_name=f"Scholarship {label}",
    )
    db_session.add_all([run, candidate])
    db_session.flush()
    return candidate


def _add_candidate_artifact(
    db_session: Session,
    *,
    candidate_id: uuid.UUID,
    url: str,
    text: str,
    contract_label: str,
) -> tuple[CatalogueCandidateSourceSnapshot, CatalogueSourceExtraction]:
    now = utc_now()
    content_hash = _hash(text)
    source_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    extraction_id = uuid.uuid4()
    source = CatalogueCandidateSource(
        id=source_id,
        candidate_id=candidate_id,
        url=url,
        canonical_url=url,
        final_url=url,
        status=CandidateSourceStatus.FETCHED,
        is_official=True,
        trust_tier=1,
        classification_reason="official test source",
        content_type="text/html",
        content_hash=content_hash,
        relevant_excerpt=text[:500],
        bytes_read=len(text.encode("utf-8")),
        fetched_at=now,
    )
    snapshot = CatalogueCandidateSourceSnapshot(
        id=snapshot_id,
        candidate_source_id=source_id,
        fetched_at=now,
        requested_url=url,
        final_url=url,
        http_status=200,
        content_hash=content_hash,
        normalized_text=text,
        extraction_method="html_text",
        byte_count=len(text.encode("utf-8")),
        character_count=len(text),
        fetch_metadata={"content_type": "text/html"},
    )
    extraction = CatalogueSourceExtraction(
        id=extraction_id,
        candidate_source_snapshot_id=snapshot_id,
        target_context_hash=_hash(f"target:{candidate_id}"),
        claim_plan_hash=_hash("deadline-only"),
        schema_version="catalogue-source-extraction.v2",
        instruction_version="test-instruction.v1",
        prompt_hash=_hash("test prompt"),
        provider="fake",
        model="deterministic-test",
        contract_fingerprint=_hash(f"contract:{contract_label}"),
        status=SourceExtractionStatus.SUCCEEDED,
        accepted_output_json={"claims": []},
        started_at=now,
        completed_at=now,
    )
    db_session.add_all([source, snapshot, extraction])
    db_session.flush()
    return snapshot, extraction


def _deadline_claim(excerpt: str) -> SourceClaim:
    return SourceClaim(
        claim_type=ClaimType.APPLICATION_DEADLINE,
        value=TemporalClaimValue(
            precision=TemporalPrecision.DATE,
            calendar_date=date(2027, 5, 20),
        ),
        evidence=[EvidenceProposal(role=EvidenceRole.VALUE, excerpt=excerpt)],
    )


def _create_bundle(
    db_session: Session,
    *,
    candidate_id: uuid.UUID,
    label: str,
) -> CatalogueEvidenceBundle:
    row = CatalogueEvidenceBundle(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        opportunity_id=None,
        objective_kind="test_resolution",
        objective_scope_snapshot={"label": label},
        target_identity_snapshot={"candidate_id": str(candidate_id)},
        resolver_policy_version="test-resolver.v1",
        status=EvidenceBundleStatus.PENDING,
        input_fingerprint=_hash(f"bundle:{candidate_id}:{label}"),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _attach_candidate_snapshot(
    db_session: Session,
    *,
    bundle: CatalogueEvidenceBundle,
    snapshot: CatalogueCandidateSourceSnapshot,
    label: str,
):
    return attach_snapshot_to_bundle(
        db_session,
        bundle_id=bundle.id,
        candidate_source_snapshot_id=snapshot.id,
        source_context_hash=_hash(f"source-context:{label}"),
        normalized_url=snapshot.final_url,
        domain="official.example",
        source_owner_type=SourceOwnerType.PROVIDER,
        source_owner_id=None,
        officiality_status=OfficialityStatus.OFFICIAL,
        authority_class="official_provider",
        authority_scope_snapshot={"deadline": True},
        authority_policy_version="test-authority.v1",
    )


def test_one_extraction_claim_can_be_reused_across_multiple_bundles(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="reuse")
    text = "Applications close on 20 May 2027."
    snapshot, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/reuse",
        text=text,
        contract_label="reuse",
    )
    first = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    db_session.flush()
    second = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=99,
        claim=_deadline_claim(text),
    )
    assert second.reused is True
    assert second.claim.id == first.claim.id

    bundle_a = _create_bundle(db_session, candidate_id=candidate.id, label="deadline")
    bundle_b = _create_bundle(db_session, candidate_id=candidate.id, label="completeness")
    source_a = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_a,
        snapshot=snapshot,
        label="reuse-a",
    )
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_b,
        snapshot=snapshot,
        label="reuse-b",
    )
    db_session.flush()

    binding_a = bind_claim_to_bundle(
        db_session,
        bundle_id=bundle_a.id,
        bundle_source_id=source_a.id,
        claim_id=first.claim.id,
    )
    binding_b = bind_claim_to_bundle(
        db_session,
        bundle_id=bundle_b.id,
        bundle_source_id=source_b.id,
        claim_id=first.claim.id,
    )
    db_session.flush()

    assert binding_a.id != binding_b.id
    assert binding_a.claim_id == binding_b.claim_id == first.claim.id
    assert db_session.scalar(select(func.count()).select_from(CatalogueSourceExtraction)) == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogueFieldClaim)) == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogueEvidenceBundleClaim)) == 2


def test_identical_semantic_claims_from_two_sources_are_not_collapsed(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="corroboration")
    text = "Applications close on 20 May 2027."
    snapshot_a, extraction_a = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/provider/deadline",
        text=text,
        contract_label="provider",
    )
    snapshot_b, extraction_b = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/embassy/deadline",
        text=text,
        contract_label="embassy",
    )
    claim_a = persist_source_claim(
        db_session,
        extraction_id=extraction_a.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    claim_b = persist_source_claim(
        db_session,
        extraction_id=extraction_b.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    db_session.flush()

    bundle = _create_bundle(db_session, candidate_id=candidate.id, label="corroboration")
    source_a = _attach_candidate_snapshot(
        db_session,
        bundle=bundle,
        snapshot=snapshot_a,
        label="provider",
    )
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle,
        snapshot=snapshot_b,
        label="embassy",
    )
    db_session.flush()
    bind_claim_to_bundle(
        db_session,
        bundle_id=bundle.id,
        bundle_source_id=source_a.id,
        claim_id=claim_a.claim.id,
    )
    bind_claim_to_bundle(
        db_session,
        bundle_id=bundle.id,
        bundle_source_id=source_b.id,
        claim_id=claim_b.claim.id,
    )
    db_session.flush()

    assert claim_a.claim.id != claim_b.claim.id
    assert claim_a.claim.claim_fingerprint == claim_b.claim.claim_fingerprint
    assert db_session.scalar(select(func.count()).select_from(CatalogueFieldClaim)) == 2
    assert db_session.scalar(select(func.count()).select_from(CatalogueEvidenceBundleClaim)) == 2


def test_bundle_source_rejects_snapshot_owned_by_another_candidate(
    db_session: Session,
) -> None:
    target = _create_candidate(db_session, label="target")
    other = _create_candidate(db_session, label="other")
    snapshot, _ = _add_candidate_artifact(
        db_session,
        candidate_id=other.id,
        url="https://official.example/other",
        text="Applications close on 20 May 2027.",
        contract_label="other",
    )
    bundle = _create_bundle(db_session, candidate_id=target.id, label="ownership")

    with pytest.raises(LedgerBindingError, match="does not belong to bundle candidate"):
        _attach_candidate_snapshot(
            db_session,
            bundle=bundle,
            snapshot=snapshot,
            label="wrong-owner",
        )


def test_claim_binding_rejects_different_snapshot_even_with_same_candidate(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="cross-snapshot")
    text = "Applications close on 20 May 2027."
    _, extraction_a = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/source-a",
        text=text,
        contract_label="source-a",
    )
    snapshot_b, _ = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/source-b",
        text=text,
        contract_label="source-b",
    )
    persisted = persist_source_claim(
        db_session,
        extraction_id=extraction_a.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    db_session.flush()
    bundle = _create_bundle(db_session, candidate_id=candidate.id, label="wrong-snapshot")
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle,
        snapshot=snapshot_b,
        label="source-b",
    )
    db_session.flush()

    with pytest.raises(LedgerBindingError, match="do not reference the same snapshot"):
        bind_claim_to_bundle(
            db_session,
            bundle_id=bundle.id,
            bundle_source_id=source_b.id,
            claim_id=persisted.claim.id,
        )


def test_database_composite_fk_rejects_bundle_source_from_another_bundle(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="composite-fk")
    text = "Applications close on 20 May 2027."
    snapshot, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/composite",
        text=text,
        contract_label="composite",
    )
    persisted = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=0,
        claim=_deadline_claim(text),
    )
    db_session.flush()
    bundle_a = _create_bundle(db_session, candidate_id=candidate.id, label="a")
    bundle_b = _create_bundle(db_session, candidate_id=candidate.id, label="b")
    source_b = _attach_candidate_snapshot(
        db_session,
        bundle=bundle_b,
        snapshot=snapshot,
        label="b",
    )
    db_session.flush()

    db_session.add(
        CatalogueEvidenceBundleClaim(
            id=uuid.uuid4(),
            bundle_id=bundle_a.id,
            bundle_source_id=source_b.id,
            claim_id=persisted.claim.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_exact_evidence_validation_records_offsets_and_terminal_rows_are_immutable(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="evidence")
    text = "Overview. Applications close on 20 May 2027. Apply online."
    excerpt = "Applications close on 20 May 2027."
    _, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/evidence",
        text=text,
        contract_label="evidence",
    )
    persisted = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=0,
        claim=_deadline_claim(excerpt),
    )
    db_session.flush()

    evidence = validate_claim_evidence(
        db_session,
        evidence_id=persisted.evidence[0].id,
    )
    db_session.flush()
    assert evidence.validation_status is ClaimEvidenceValidationStatus.MATCHED
    assert evidence.excerpt_start is not None
    assert evidence.excerpt_end is not None
    assert text[evidence.excerpt_start : evidence.excerpt_end] == excerpt

    evidence.excerpt = "mutated after validation"
    with pytest.raises(LedgerIntegrityError, match="terminal claim evidence is immutable"):
        db_session.flush()


@pytest.mark.parametrize(
    ("text", "excerpt", "expected_status", "expected_failure"),
    [
        (
            "No fixed closing date is published.",
            "Applications close on 20 May 2027.",
            ClaimEvidenceValidationStatus.NOT_FOUND,
            "evidence_excerpt_not_found",
        ),
        (
            "Deadline pending. Deadline pending.",
            "Deadline pending.",
            ClaimEvidenceValidationStatus.AMBIGUOUS,
            "evidence_excerpt_ambiguous",
        ),
    ],
)
def test_evidence_locator_fails_closed_for_missing_or_ambiguous_excerpt(
    db_session: Session,
    text: str,
    excerpt: str,
    expected_status: ClaimEvidenceValidationStatus,
    expected_failure: str,
) -> None:
    candidate = _create_candidate(db_session, label=expected_status.value)
    _, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url=f"https://official.example/{expected_status.value}",
        text=text,
        contract_label=expected_status.value,
    )
    persisted = persist_source_claim(
        db_session,
        extraction_id=extraction.id,
        ordinal=0,
        claim=_deadline_claim(excerpt),
    )
    db_session.flush()

    evidence = validate_claim_evidence(
        db_session,
        evidence_id=persisted.evidence[0].id,
    )
    db_session.flush()
    assert evidence.validation_status is expected_status
    assert evidence.excerpt_start is None
    assert evidence.excerpt_end is None
    assert evidence.failure_code == expected_failure
    assert evidence.validated_at is not None


def test_database_rejects_succeeded_extraction_without_accepted_output(
    db_session: Session,
) -> None:
    candidate = _create_candidate(db_session, label="invalid-success")
    snapshot, _ = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/valid-extraction",
        text="Applications close on 20 May 2027.",
        contract_label="valid",
    )
    now = utc_now()
    db_session.add(
        CatalogueSourceExtraction(
            id=uuid.uuid4(),
            candidate_source_snapshot_id=snapshot.id,
            target_context_hash=_hash("invalid-target"),
            claim_plan_hash=_hash("invalid-plan"),
            schema_version="catalogue-source-extraction.v2",
            instruction_version="test-instruction.v1",
            prompt_hash=_hash("invalid-prompt"),
            provider="fake",
            model="deterministic-test",
            contract_fingerprint=_hash("invalid-contract"),
            status=SourceExtractionStatus.SUCCEEDED,
            accepted_output_json=None,
            started_at=now,
            completed_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_candidate_source_snapshot_is_immutable(db_session: Session) -> None:
    candidate = _create_candidate(db_session, label="immutable-snapshot")
    snapshot, _ = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/immutable",
        text="Applications close on 20 May 2027.",
        contract_label="immutable",
    )
    snapshot.normalized_text = "mutated source bytes"
    with pytest.raises(LedgerIntegrityError, match="PR6 ledger history is immutable"):
        db_session.flush()


def test_retry_history_preserves_failed_attempt_before_success(db_session: Session) -> None:
    candidate = _create_candidate(db_session, label="retry-history")
    _, extraction = _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/retry",
        text="Applications close on 20 May 2027.",
        contract_label="retry",
    )
    now = utc_now()
    failed = CatalogueSourceExtractionAttempt(
        id=uuid.uuid4(),
        extraction_id=extraction.id,
        attempt_number=1,
        status=SourceExtractionAttemptStatus.RATE_LIMITED,
        request_fingerprint=_hash("attempt-1"),
        error_code="rate_limited",
        completed_at=now,
    )
    succeeded = CatalogueSourceExtractionAttempt(
        id=uuid.uuid4(),
        extraction_id=extraction.id,
        attempt_number=2,
        status=SourceExtractionAttemptStatus.SUCCEEDED,
        request_fingerprint=_hash("attempt-2"),
        completed_at=now,
    )
    db_session.add_all([failed, succeeded])
    db_session.flush()

    attempts = list(
        db_session.scalars(
            select(CatalogueSourceExtractionAttempt)
            .where(CatalogueSourceExtractionAttempt.extraction_id == extraction.id)
            .order_by(CatalogueSourceExtractionAttempt.attempt_number)
        )
    )
    assert [item.status for item in attempts] == [
        SourceExtractionAttemptStatus.RATE_LIMITED,
        SourceExtractionAttemptStatus.SUCCEEDED,
    ]

    failed.error_code = "rewritten_history"
    with pytest.raises(LedgerIntegrityError, match="terminal source extraction attempts"):
        db_session.flush()


def test_old_parent_cascade_cannot_erase_pr6_snapshot_history(db_session: Session) -> None:
    candidate = _create_candidate(db_session, label="retention")
    _add_candidate_artifact(
        db_session,
        candidate_id=candidate.id,
        url="https://official.example/retention",
        text="Applications close on 20 May 2027.",
        contract_label="retention",
    )
    db_session.commit()

    run = db_session.get(CatalogueIngestionRun, candidate.run_id)
    assert run is not None
    db_session.delete(run)
    with pytest.raises(IntegrityError):
        db_session.flush()
