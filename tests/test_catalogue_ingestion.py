import hashlib
import json
import urllib.error
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.claim_bundle_provider import FakeBundleClaimProvider
from app.modules.catalogue_ingestion.claim_bundle_schemas import (
    BundleEvidenceReference,
    BundleObjectiveCoverage,
    ClaimBundleExtractionOutput,
)
from app.modules.catalogue_ingestion.claim_provider import (
    AzureOpenAIClaimProvider,
    ClaimExtractionResult,
    FakeClaimProvider,
    _azure_schema,
    _normalize_claim_output,
    _objective_azure_schema,
    _objective_source_text,
)
from app.modules.catalogue_ingestion.claim_resolution import resolve_claims
from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimExtractionOutput,
    ClaimObjective,
    ClaimValue,
)
from app.modules.catalogue_ingestion.evaluation import GoldItem, evaluate
from app.modules.catalogue_ingestion.extraction_cache_models import CatalogueExtractionCacheEvent
from app.modules.catalogue_ingestion.models import (
    CandidateSourceRole,
    CandidateSourceStatus,
    CandidateStatus,
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueExtractionAttempt,
    CatalogueIngestionRun,
    CatalogueJobState,
    CatalogueResumableJob,
    CatalogueSourceArtifact,
    IngestionInputKind,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.production_service import ProductionCatalogueIngestionService
from app.modules.catalogue_ingestion.provider import (
    AzureOpenAIExtractionProvider,
    ExtractionProviderError,
    ExtractionProviderRateLimited,
    ExtractionSchemaError,
    FakeExtractionProvider,
    azure_structured_output_schema,
    estimate_cost,
    extraction_retry_delay,
)
from app.modules.catalogue_ingestion.repository import CatalogueIngestionRepository
from app.modules.catalogue_ingestion.schemas import (
    CatalogueExtractionOutput,
    ExtractionResult,
    ExtractionUsage,
)
from app.modules.catalogue_ingestion.seed_parser import (
    LoadedSeed,
    LocalSeedDocumentParser,
    SeedParseError,
    SeedSourceLoader,
)
from app.modules.catalogue_ingestion.service import (
    CatalogueIngestionService,
    _aggregate_coverage,
    _canonical_identity_name,
    _crawler_child_matches_root,
    _identity_name_matches,
)
from app.modules.catalogue_ingestion.sources import OfficialSourceClassifier
from app.modules.catalogue_ingestion.validation import validate_and_build_proposal
from app.modules.opportunities.evidence_models import (
    ApplicationStep,
    FundingComponent,
    RequiredDocument,
    ScopedDeadline,
    SourceSnapshot,
)
from app.modules.opportunities.evidence_models import (
    FieldEvidence as GraphFieldEvidence,
)
from app.modules.opportunities.graph_models import (
    ApplicationTrack,
    Institution,
    InstitutionParticipation,
)
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    University,
    VerificationStatus,
)
from app.modules.opportunities.schemas import ReviewAction, ReviewActionRequest
from app.modules.opportunities.service import OpportunityService
from app.modules.opportunities.source_monitor import (
    FetchedSource,
    SafeSourceFetcher,
    SourceFetchError,
)

OFFICIAL_URL = "https://scholarships.gov.uk/example"
SOURCE_TEXT = (
    "Example Scholarship offers awards. Official Provider administers the award. "
    "Applicants study in the United Kingdom. Masters programmes are eligible."
)
MEXT_TEXT = (
    "MEXT Scholarship. Ministry of Education provides the award. Study in Japan. "
    "Undergraduate, masters and doctoral categories. "
    "2027 intake. Embassy Recommendation. University Recommendation. Tuition is covered. "
    "Research Students follow Embassy Recommendation. Embassy of Japan accepts applications. "
    "Passport is required. Submit the application."
    " Deadline 2026-05-15. Research Students support masters and doctoral degrees."
    " Applicants must hold a bachelor's degree."
)


def claim_output() -> ClaimExtractionOutput:
    def claim(
        entity_type,
        entity_key,
        field_path,
        value,
        excerpt,
        *,
        track_key=None,
        institution_key=None,
        programme_key=None,
    ):
        start = MEXT_TEXT.index(excerpt)
        typed = {
            "string_value": None,
            "decimal_value": None,
            "integer_value": None,
            "boolean_value": None,
            "string_list_value": None,
        }
        if isinstance(value, bool):
            typed["boolean_value"] = value
        elif isinstance(value, int):
            typed["integer_value"] = value
        elif isinstance(value, list):
            typed["string_list_value"] = value
        else:
            typed["string_value"] = value
        return {
            "entity_type": entity_type,
            "entity_key": entity_key,
            "field_path": field_path,
            "value": typed,
            "scope": {
                "cycle_key": "2027",
                "track_key": track_key,
                "institution_key": institution_key,
                "programme_key": programme_key,
            },
            "excerpt": excerpt,
            "excerpt_start": start,
            "excerpt_end": start + len(excerpt),
            "basis": "explicit",
        }

    return ClaimExtractionOutput.model_validate(
        {
            "claims": [
                claim("scholarship", "mext", "name", "MEXT Scholarship", "MEXT Scholarship"),
                claim(
                    "scholarship",
                    "mext",
                    "provider_name",
                    "Ministry of Education",
                    "Ministry of Education",
                ),
                claim("scholarship", "mext", "country_code", "JP", "Study in Japan"),
                claim(
                    "scholarship",
                    "mext",
                    "degree_levels",
                    ["bachelors", "masters", "phd"],
                    "Undergraduate, masters and doctoral categories",
                ),
                claim("cycle", "2027", "intake_year", 2027, "2027 intake"),
                claim(
                    "track",
                    "embassy_recommendation",
                    "name",
                    "Embassy Recommendation",
                    "Embassy Recommendation",
                    track_key="embassy_recommendation",
                ),
                claim(
                    "track",
                    "university_recommendation",
                    "name",
                    "University Recommendation",
                    "University Recommendation",
                    track_key="university_recommendation",
                ),
                claim(
                    "track",
                    "research_students",
                    "name",
                    "Research Students",
                    "Research Students",
                    track_key="research_students",
                ),
                claim(
                    "track",
                    "research_students",
                    "parent_track_key",
                    "embassy_recommendation",
                    "Embassy Recommendation",
                    track_key="research_students",
                ),
                claim(
                    "institution",
                    "embassy_of_japan",
                    "canonical_name",
                    "Embassy of Japan",
                    "Embassy of Japan accepts applications",
                    track_key="embassy_recommendation",
                    institution_key="embassy_of_japan",
                ),
                claim(
                    "institution",
                    "embassy_of_japan",
                    "institution_type",
                    "embassy",
                    "Embassy of Japan accepts applications",
                    track_key="embassy_recommendation",
                    institution_key="embassy_of_japan",
                ),
                claim(
                    "funding",
                    "tuition",
                    "coverage_status",
                    "confirmed",
                    "Tuition is covered",
                ),
                claim("document", "passport", "name", "Passport", "Passport is required"),
                claim(
                    "step", "submit", "title", "Submit the application", "Submit the application"
                ),
                claim(
                    "deadline",
                    "embassy_deadline",
                    "deadline_at",
                    "2026-05-15",
                    "Deadline 2026-05-15",
                    track_key="embassy_recommendation",
                ),
                claim(
                    "deadline",
                    "embassy_deadline",
                    "deadline_type",
                    "application_submission",
                    "Deadline 2026-05-15",
                    track_key="embassy_recommendation",
                ),
                claim(
                    "programme",
                    "research_students",
                    "name",
                    "Research Students",
                    "Research Students",
                    programme_key="research_students",
                ),
                claim(
                    "programme",
                    "research_students",
                    "degree_levels",
                    ["masters", "phd"],
                    "Research Students support masters and doctoral degrees",
                    programme_key="research_students",
                ),
                claim(
                    "eligibility",
                    "prior_bachelors_degree",
                    "rule_type",
                    "academic_background",
                    "Applicants must hold a bachelor's degree",
                    programme_key="research_students",
                ),
                claim(
                    "eligibility",
                    "prior_bachelors_degree",
                    "operator",
                    "equals",
                    "Applicants must hold a bachelor's degree",
                    programme_key="research_students",
                ),
                claim(
                    "eligibility",
                    "prior_bachelors_degree",
                    "value",
                    "bachelors",
                    "Applicants must hold a bachelor's degree",
                    programme_key="research_students",
                ),
                claim(
                    "funding",
                    "tuition",
                    "component_type",
                    "tuition",
                    "Tuition is covered",
                ),
            ],
            "unknown_objectives": [],
            "conflicts": [],
            "warnings": [],
        }
    )


def test_claim_value_treats_an_unused_empty_list_as_unset() -> None:
    value = ClaimValue(
        string_value="Embassy Recommendation",
        decimal_value=None,
        integer_value=None,
        boolean_value=None,
        string_list_value=[],
    )

    assert value.primitive() == "Embassy Recommendation"
    assert value.string_list_value is None


def test_claim_output_normalizes_paths_offsets_and_core_priority() -> None:
    raw = claim_output().model_dump(mode="json")
    raw["claims"][5]["field_path"] = "track_name"
    raw["claims"][7]["field_path"] = "track_type"
    raw["claims"][11]["field_path"] = "funding.coverage_status"
    output = ClaimExtractionOutput.model_validate(raw)
    output.claims[0] = output.claims[0].model_copy(
        update={"excerpt_start": 1, "excerpt_end": 1 + len("MEXT Scholarship")}
    )

    identity = _normalize_claim_output(output, MEXT_TEXT, objective=ClaimObjective.IDENTITY)
    programmes = _normalize_claim_output(output, MEXT_TEXT, objective=ClaimObjective.PROGRAMMES)
    routes = _normalize_claim_output(output, MEXT_TEXT, objective=ClaimObjective.ROUTES)
    application = _normalize_claim_output(
        output, MEXT_TEXT, objective=ClaimObjective.APPLICATION_TIMELINE
    )

    assert identity.claims[0].excerpt_start == 0
    assert output.claims[11].field_path == "coverage_status"
    assert output.claims[5].field_path == "name"
    assert any(item.field_path == "track_type" for item in output.claims)
    assert any(item.field_path == "deadline_at" for item in application.claims)
    present = {
        (item.entity_type.value, item.entity_key, item.field_path)
        for item in programmes.claims + routes.claims
    }
    assert any(item.field_path == "name" for item in identity.claims)
    assert ("track", "embassy_recommendation", "name") in present
    assert ("track", "university_recommendation", "name") in present
    assert ("programme", "research_students", "degree_levels") in present
    assert not any(item.startswith("claim_limit_applied:") for item in programmes.warnings)


def test_requirements_objective_retains_more_than_twelve_documents() -> None:
    template = claim_output().claims[12]
    documents = []
    for index in range(15):
        item = template.model_copy(deep=True)
        item.entity_key = f"document_{index + 1}"
        item.value.string_value = f"Required document {index + 1}"
        documents.append(item)
    output = ClaimExtractionOutput(
        objective=ClaimObjective.DOCUMENTS_CORE,
        claims=documents,
        unknown_objectives=[],
        conflicts=[],
        warnings=[],
    )

    normalized = _normalize_claim_output(
        output,
        MEXT_TEXT,
        objective=ClaimObjective.DOCUMENTS_CORE,
    )

    assert len(normalized.claims) == 15
    assert {item.entity_key for item in normalized.claims} == {
        f"document_{index + 1}" for index in range(15)
    }


def test_objective_source_mask_reduces_tokens_without_changing_evidence_offsets() -> None:
    prefix = "Overview " + ("irrelevant material " * 700)
    evidence = "Documents to be submitted include an Academic Transcript."
    source_text = prefix + evidence + (" unrelated appendix" * 700)

    masked = _objective_source_text(source_text, ClaimObjective.DOCUMENTS_CORE)

    evidence_start = source_text.index(evidence)
    assert len(masked) == len(source_text)
    assert masked[evidence_start : evidence_start + len(evidence)] == evidence
    assert masked.index(evidence) == evidence_start
    assert len(masked.replace(" ", "")) < len(source_text.replace(" ", ""))


def extraction_output(
    source_url: str = OFFICIAL_URL,
    *,
    conflicts: list[str] | None = None,
) -> CatalogueExtractionOutput:
    return CatalogueExtractionOutput.model_validate(
        {
            "identity": {
                "name": "Example Scholarship",
                "provider_name": "Official Provider",
                "provider_canonical_id": "official-provider",
                "provider_website_url": "https://scholarships.gov.uk",
                "university_name": None,
                "university_website_url": None,
                "country": "United Kingdom",
                "country_code": "GB",
                "programme_family_id": "example-scholarship",
            },
            "study": {
                "degree_level": "masters",
                "field_eligibility": None,
                "intake_year": None,
                "cycle_id": None,
            },
            "funding": {
                "funding_type": "unknown",
                "funding_policy": None,
                "tuition_coverage_status": "unknown",
                "stipend_coverage_status": "unknown",
                "accommodation_coverage_status": "unknown",
                "travel_coverage_status": "unknown",
                "insurance_coverage_status": "unknown",
                "fees_coverage_status": "unknown",
                "application_fee_status": "unknown",
                "tuition_coverage": None,
                "monthly_stipend_amount": None,
                "monthly_stipend_currency": None,
                "accommodation_coverage": None,
                "travel_allowance": None,
                "health_insurance": None,
                "application_fee_info": None,
            },
            "eligibility": {
                "nationality_eligibility": None,
                "minimum_academic_requirement": None,
                "english_language_requirement": None,
                "standardized_test_requirement": None,
                "rules": [],
            },
            "application": {
                "application_opening_date": None,
                "application_deadline": None,
                "timezone": None,
                "application_url": None,
                "application_method": None,
                "required_documents": [],
                "is_rolling": False,
            },
            "evidence": [
                {
                    "field_path": "identity.name",
                    "source_url": source_url,
                    "section_label": "Overview",
                    "locator": None,
                    "excerpt": "Example Scholarship offers awards.",
                    "basis": "explicit",
                },
                {
                    "field_path": "identity.provider_name",
                    "source_url": source_url,
                    "section_label": "Overview",
                    "locator": None,
                    "excerpt": "Official Provider administers the award.",
                    "basis": "explicit",
                },
                {
                    "field_path": "identity.country",
                    "source_url": source_url,
                    "section_label": "Eligibility",
                    "locator": None,
                    "excerpt": "Applicants study in the United Kingdom.",
                    "basis": "explicit",
                },
                {
                    "field_path": "study.degree_level",
                    "source_url": source_url,
                    "section_label": "Courses",
                    "locator": None,
                    "excerpt": "Masters programmes are eligible.",
                    "basis": "normalized",
                },
            ],
            "unknown_fields": ["application.application_deadline"],
            "conflicts": conflicts or [],
            "warnings": [],
        }
    )


def enabled_settings(**overrides) -> Settings:
    values = {
        "env": "test",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "test-secret-that-is-at-least-32-characters-long",
        "catalogue_ai_ingestion_enabled": True,
        "catalogue_ai_provider": "azure_openai",
        "catalogue_ai_endpoint": "https://example.openai.azure.com",
        "catalogue_ai_model": "structured-output-deployment",
        "catalogue_bounded_crawling_enabled": False,
        "catalogue_ai_max_retries": 2,
        "catalogue_ai_input_cost_per_million": Decimal("1"),
        "catalogue_ai_output_cost_per_million": Decimal("2"),
    }
    values.update(overrides)
    return Settings(**values)


class FakeFetcher:
    def __init__(self, text: str = SOURCE_TEXT) -> None:
        self.text = text
        self.calls = 0

    def fetch(self, url: str) -> FetchedSource:
        self.calls += 1
        return FetchedSource(
            url=url,
            final_url=url,
            content_hash=hashlib.sha256(self.text.encode()).hexdigest(),
            excerpt_text=self.text,
            section_label="Official page",
            bytes_read=len(self.text.encode()),
            normalized_text=self.text,
            content_type="text/html",
        )

    def fetch_with_limit(self, url: str, *, max_bytes: int) -> FetchedSource:
        fetched = self.fetch(url)
        if fetched.bytes_read > max_bytes:
            raise SourceFetchError("crawl_byte_budget_exceeded")
        return fetched


class MappingFetcher:
    def __init__(self, sources: dict[str, str]) -> None:
        self.sources = sources
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchedSource:
        self.calls.append(url)
        text = self.sources[url]
        return FetchedSource(
            url=url,
            final_url=url,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            excerpt_text=text,
            section_label="Official page",
            bytes_read=len(text.encode()),
            normalized_text=text,
            content_type="text/html",
        )


def write_seed(tmp_path, rows: list[dict[str, object]]):
    path = tmp_path / "seeds.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_seed_parsers_accept_bounded_json_csv_and_text(tmp_path) -> None:
    loader = SeedSourceLoader()
    parser = LocalSeedDocumentParser()
    json_path = write_seed(
        tmp_path,
        [{"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL}],
    )
    loaded = loader.load(str(json_path))
    assert parser.parse(loaded)[0].name == "Example Scholarship"
    assert loaded.fingerprint == hashlib.sha256(json_path.read_bytes()).hexdigest()

    csv_seed = LoadedSeed(
        "seeds.csv",
        "x" * 64,
        f"name,provider,official_url\nExample Scholarship,Provider,{OFFICIAL_URL}\n".encode(),
        "text/csv",
    )
    assert parser.parse(csv_seed)[0].provider == "Provider"
    text_seed = LoadedSeed(
        "seeds.txt",
        "y" * 64,
        f"- Example Scholarship | Provider | UK | {OFFICIAL_URL}\n".encode(),
        "text/plain",
    )
    assert str(parser.parse(text_seed)[0].possible_official_url) == OFFICIAL_URL


def test_catalogue_ingestion_admin_api_is_not_public(client) -> None:
    for path in (
        "/api/v1/admin/catalogue-ingestion/runs",
        "/api/v1/admin/catalogue-ingestion/candidates",
        "/api/v1/admin/catalogue-ingestion/discovery/runs",
        "/api/v1/admin/catalogue-ingestion/discovery/leads",
        f"/api/v1/admin/catalogue-ingestion/runs/{uuid.uuid4()}/observability",
        f"/api/v1/admin/catalogue-ingestion/candidates/{uuid.uuid4()}/observability",
    ):
        assert client.get(path).status_code == 401
    assert (
        client.post(
            "/api/v1/admin/catalogue-ingestion/runs/url",
            json={"url": OFFICIAL_URL},
        ).status_code
        == 401
    )


def test_candidate_claiming_prefers_the_least_served_candidate(db_session) -> None:
    run = CatalogueIngestionRun(
        source_label="fairness.json",
        source_fingerprint="f" * 64,
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=2,
        max_pages_per_candidate=1,
        max_model_calls=0,
        max_input_characters=1_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("0"),
    )
    db_session.add(run)
    db_session.flush()
    earlier = CatalogueCandidate(
        run_id=run.id,
        seed_index=0,
        idempotency_key="a" * 64,
        seed_name="Large Scholarship",
        attempt_count=2,
    )
    waiting = CatalogueCandidate(
        run_id=run.id,
        seed_index=1,
        idempotency_key="b" * 64,
        seed_name="Waiting Scholarship",
        attempt_count=0,
    )
    db_session.add_all((earlier, waiting))
    db_session.commit()
    repository = CatalogueIngestionRepository(db_session)
    run_lease = repository.acquire_run_lease(run.id, lease_seconds=60)

    claimed = repository.claim_candidates(
        run_id=run.id,
        run_lease_token=run_lease,
        worker_id="fair-worker",
        limit=1,
        lease_seconds=60,
    )

    assert [item.id for item in claimed] == [waiting.id]


def test_resumable_job_failure_is_terminal_and_retains_diagnostics(db_session) -> None:
    run = CatalogueIngestionRun(
        source_label="failed-job.json",
        source_fingerprint="f" * 64,
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=1,
        max_pages_per_candidate=1,
        max_model_calls=0,
        max_input_characters=1_000,
        max_output_tokens=256,
        max_estimated_cost=Decimal("0"),
    )
    candidate = CatalogueCandidate(
        run=run,
        seed_index=0,
        idempotency_key="j" * 64,
        seed_name="Failed Job Scholarship",
    )
    db_session.add_all((run, candidate))
    db_session.commit()
    repository = CatalogueIngestionRepository(db_session)
    run_lease = repository.acquire_run_lease(run.id, lease_seconds=60)
    claimed = repository.claim_candidates(
        run_id=run.id,
        run_lease_token=run_lease,
        worker_id="job-worker",
        limit=1,
        lease_seconds=60,
    )[0]
    assert claimed.lease_token is not None
    job = repository.start_or_resume_job(
        run_id=run.id,
        candidate_id=claimed.id,
        stage="claim_bundle_extraction",
        job_key="terminal-job",
        worker_id="job-worker",
        run_lease_token=run_lease,
        candidate_lease_token=claimed.lease_token,
    )

    repository.fail_job(
        job.id,
        worker_id="job-worker",
        run_lease_token=run_lease,
        candidate_lease_token=claimed.lease_token,
        error_code="bundle_validation_failed",
        error_detail="invalid_evidence_span:deadline",
        checkpoint={"outcome": "validation_failed"},
    )

    db_session.refresh(job)
    assert job.state is CatalogueJobState.FAILED
    assert job.error_code == "bundle_validation_failed"
    assert job.error_detail == "invalid_evidence_span:deadline"
    assert job.checkpoint["outcome"] == "validation_failed"
    assert job.completed_at is not None

    resumed = repository.start_or_resume_job(
        run_id=run.id,
        candidate_id=claimed.id,
        stage="claim_bundle_extraction",
        job_key="terminal-job",
        worker_id="job-worker",
        run_lease_token=run_lease,
        candidate_lease_token=claimed.lease_token,
        checkpoint={"outcome": "pending"},
    )

    assert resumed.state is CatalogueJobState.FAILED
    assert resumed.attempt_count == 1


def test_bundle_validation_failure_splits_then_fails_terminally_with_raw_output(
    db_session,
) -> None:
    invalid_output = ClaimBundleExtractionOutput(
        evidence_refs=[
            BundleEvidenceReference(
                ref_id="outside",
                block_key="z" * 64,
                excerpt="not present in the supplied evidence",
                excerpt_start=0,
                excerpt_end=36,
            )
        ],
        claims=[],
        objective_coverage=[
            BundleObjectiveCoverage(
                objective=objective,
                coverage_state="partial",
                unknown_objectives=["Invalid evidence reference used for recovery test"],
            )
            for objective in ClaimObjective
        ],
    )
    provider = FakeBundleClaimProvider(invalid_output)
    long_evidence = (MEXT_TEXT + "\n") * 70
    service = ProductionCatalogueIngestionService(
        db_session,
        enabled_settings(
            catalogue_bounded_crawling_enabled=False,
            catalogue_ai_max_calls_per_run=100,
            catalogue_completeness_mode_enabled=True,
        ),
        fetcher=FakeFetcher(long_evidence),
        claim_extractor=FakeClaimProvider(claim_output()),
        bundle_claim_extractor=provider,
    )
    run = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )

    service.process_run(run.id, worker_id="validation-recovery")

    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    jobs = list(
        db_session.scalars(
            select(CatalogueResumableJob).where(
                CatalogueResumableJob.stage == "claim_bundle_extraction"
            )
        )
    )
    events = list(
        db_session.scalars(
            select(CatalogueExtractionCacheEvent).where(
                CatalogueExtractionCacheEvent.reason == "bundle_validation_boundary_rejected"
            )
        )
    )
    assert any(job.checkpoint.get("outcome") == "split" for job in jobs)
    failed = [job for job in jobs if job.state is CatalogueJobState.FAILED]
    assert failed
    assert all(job.error_code == "bundle_validation_failed" for job in failed)
    assert events
    assert events[-1].detail_json["output_json"] == invalid_output.model_dump(mode="json")
    assert "unknown_evidence_block:outside" in events[-1].detail_json["validation_warnings"]
    assert candidate is not None
    assert candidate.status is not CandidateStatus.READY_FOR_REVIEW
    assert "acquisition_snapshot_missing" in candidate.validation_errors


def test_direct_url_run_is_first_class_and_does_not_assert_invented_identity(db_session) -> None:
    extractor = FakeClaimProvider(claim_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=extractor,
    )

    run = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    result = service.process_run(run.id, worker_id="direct-url-test")

    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    artifact = db_session.scalar(select(CatalogueSourceArtifact))
    assert result.input_kind is IngestionInputKind.DIRECT_URL
    assert result.operator_url == OFFICIAL_URL
    assert candidate is not None
    assert candidate.identity_hint_is_asserted is False
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW, (
        candidate.validation_errors,
        candidate.failure_code,
        [
            (source.status, source.is_official, len(source.artifacts))
            for source in candidate.sources
        ],
    )
    assert artifact is not None
    assert artifact.normalized_text == MEXT_TEXT
    assert artifact.content_hash == hashlib.sha256(MEXT_TEXT.encode()).hexdigest()


def test_direct_url_paid_work_yields_after_each_configured_candidate_slice(db_session) -> None:
    extractor = FakeClaimProvider(claim_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(catalogue_scheduler_max_provider_calls_per_candidate_slice=1),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=extractor,
    )
    run = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )

    result = service.process_run(run.id, worker_id="direct-slice", batch_size=1)
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )

    assert result.status is IngestionRunStatus.COMPLETED_WITH_REVIEW
    assert result.checkpoint_cursor == 1
    assert extractor.calls == len(ClaimObjective)
    assert candidate is not None
    assert candidate.attempt_count >= len(ClaimObjective)


def test_catalogue_source_byte_limit_is_independent_from_model_text_limit(db_session) -> None:
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(
            catalogue_ai_max_input_characters=1_000,
            catalogue_source_max_bytes_per_page=750_000,
        ),
    )

    assert isinstance(service.fetcher, SafeSourceFetcher)
    assert service.fetcher.max_bytes == 750_000


def test_direct_url_run_rejects_non_https_and_reuses_unchanged_extraction(db_session) -> None:
    extractor = FakeClaimProvider(claim_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=extractor,
    )

    with pytest.raises(AppError, match="not permitted"):
        service.create_run_from_url(
            "http://scholarships.gov.uk/example",
            mode=IngestionMode.EXTRACTION,
            dry_run=True,
        )

    for _ in range(2):
        run = service.create_run_from_url(
            OFFICIAL_URL,
            mode=IngestionMode.EXTRACTION,
            dry_run=True,
        )
        service.process_run(run.id, worker_id="direct-url-rerun")

    assert extractor.calls == 12
    assert db_session.scalar(select(func.count()).select_from(CatalogueCandidate)) == 2
    assert db_session.scalar(select(func.count()).select_from(CatalogueSourceArtifact)) == 2


def test_direct_url_run_does_not_reuse_an_attempt_from_a_different_prompt(db_session) -> None:
    extractor = FakeClaimProvider(claim_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=extractor,
    )
    first = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    service.process_run(first.id, worker_id="direct-url-first-prompt")
    attempt = db_session.scalar(select(CatalogueExtractionAttempt))
    assert attempt is not None
    attempt.prompt_hash = "0" * 64
    db_session.commit()

    second = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    service.process_run(second.id, worker_id="direct-url-new-prompt")

    assert extractor.calls == 13


def test_direct_source_bundle_stages_expanded_claims_from_three_explicit_sources(
    db_session,
) -> None:
    embassy_url = "https://scholarships.gov.uk/aaa-mext-embassy"
    university_url = "https://scholarships.gov.uk/mext-university"
    outputs = {
        OFFICIAL_URL: claim_output().model_copy(update={"claims": claim_output().claims[:7]}),
        embassy_url: claim_output().model_copy(
            update={"claims": claim_output().claims[7:12] + claim_output().claims[14:]}
        ),
        university_url: claim_output().model_copy(update={"claims": claim_output().claims[12:14]}),
    }
    extraction_order: list[str] = []

    def extract(source_url: str, _source_text: str) -> ClaimExtractionOutput:
        extraction_order.append(source_url)
        return outputs[source_url]

    extractor = FakeClaimProvider(extract)
    fetcher = MappingFetcher({item: MEXT_TEXT for item in outputs})
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(catalogue_ai_max_pages_per_candidate=3),
        fetcher=fetcher,
        claim_extractor=extractor,
    )

    run = service.create_run_from_url(
        OFFICIAL_URL,
        supporting_urls=[embassy_url, university_url],
        mode=IngestionMode.REVIEW_QUEUE,
        dry_run=False,
    )
    result = service.process_run(run.id, worker_id="direct-bundle")

    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    sources = db_session.scalars(
        select(CatalogueCandidateSource)
        .where(CatalogueCandidateSource.candidate_id == candidate.id)
        .order_by(CatalogueCandidateSource.url)
    ).all()
    assert candidate is not None
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW
    assert result.model_calls == 36
    assert fetcher.calls == [OFFICIAL_URL, embassy_url, university_url]
    assert extraction_order == [OFFICIAL_URL] * 12 + [embassy_url] * 12 + [university_url] * 12
    assert {item.source_role for item in sources} == {
        CandidateSourceRole.PRIMARY,
        CandidateSourceRole.SUPPORTING,
    }
    assert all(item.status is CandidateSourceStatus.FETCHED for item in sources)
    assert all(
        item.artifacts[0].fetch_metadata["source_role"] == item.source_role for item in sources
    )
    assert db_session.scalar(select(func.count()).select_from(CatalogueSourceArtifact)) == 3
    assert db_session.scalar(select(func.count()).select_from(SourceSnapshot)) == 0
    assert db_session.scalar(select(func.count()).select_from(GraphFieldEvidence)) == 0
    objective_coverage = candidate.proposed_payload["objective_coverage"]
    assert objective_coverage["identity"] == "complete"
    assert set(objective_coverage.values()) <= {"complete", "partial", "unknown"}
    assert {"partial", "unknown"}.issubset(set(objective_coverage.values()))
    assert any(error.startswith("coverage:") for error in candidate.validation_errors)


def test_direct_source_bundle_rejects_duplicates_and_page_budget_overflow(db_session) -> None:
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(catalogue_ai_max_pages_per_candidate=2),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=FakeClaimProvider(claim_output()),
    )

    with pytest.raises(AppError, match="duplicate URL"):
        service.create_run_from_url(
            OFFICIAL_URL,
            supporting_urls=[f"{OFFICIAL_URL}#same-source"],
            mode=IngestionMode.EXTRACTION,
            dry_run=True,
        )
    with pytest.raises(AppError, match="page budget"):
        service.create_run_from_url(
            OFFICIAL_URL,
            supporting_urls=[
                "https://scholarships.gov.uk/mext-embassy",
                "https://scholarships.gov.uk/mext-university",
            ],
            mode=IngestionMode.EXTRACTION,
            dry_run=True,
        )


def test_direct_source_bundle_blocks_off_topic_support_before_extraction(db_session) -> None:
    supporting_url = "https://scholarships.gov.uk/general-funding"
    fetcher = MappingFetcher(
        {
            OFFICIAL_URL: MEXT_TEXT,
            supporting_url: "General government funding information for local students.",
        }
    )
    extractor = FakeClaimProvider(claim_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(catalogue_ai_max_pages_per_candidate=2),
        fetcher=fetcher,
        claim_extractor=extractor,
    )

    run = service.create_run_from_url(
        OFFICIAL_URL,
        supporting_urls=[supporting_url],
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    result = service.process_run(run.id, worker_id="off-topic-bundle")

    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    support = db_session.scalar(
        select(CatalogueCandidateSource).where(
            CatalogueCandidateSource.candidate_id == candidate.id,
            CatalogueCandidateSource.source_role == CandidateSourceRole.SUPPORTING,
        )
    )
    assert candidate is not None
    assert candidate.status is CandidateStatus.NEEDS_REVIEW
    assert candidate.failure_code == "direct_source_bundle_incomplete"
    assert support is not None
    assert support.failure_code == "operator_source_topic_mismatch"
    assert support.artifacts == []
    assert result.model_calls == 0
    assert extractor.calls == 0


def test_direct_source_bundle_resolves_an_expected_university_domain(db_session) -> None:
    university_url = "https://www.example.ac.jp/mext-recommendation"
    db_session.add(
        University(
            name="Example University",
            country="Japan",
            website_url="https://www.example.ac.jp/",
        )
    )
    db_session.commit()
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(catalogue_ai_max_pages_per_candidate=2),
        fetcher=MappingFetcher({OFFICIAL_URL: MEXT_TEXT, university_url: MEXT_TEXT}),
        claim_extractor=FakeClaimProvider(claim_output()),
    )

    run = service.create_run_from_url(
        OFFICIAL_URL,
        supporting_urls=[university_url],
        university="Example University",
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
    )
    service.process_run(run.id, worker_id="university-source")

    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    support = db_session.scalar(
        select(CatalogueCandidateSource).where(
            CatalogueCandidateSource.candidate_id == candidate.id,
            CatalogueCandidateSource.source_role == CandidateSourceRole.SUPPORTING,
        )
    )
    assert candidate is not None
    assert candidate.seed_university == "Example University"
    assert candidate.status is CandidateStatus.NEEDS_REVIEW
    assert support is not None
    assert support.is_official is True
    assert support.trust_tier == 3
    assert support.classification_reason == "domain matches the university's canonical website"


def test_retry_clears_stale_direct_url_review_state(db_session) -> None:
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=FakeClaimProvider(claim_output()),
    )
    run = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    service.process_run(run.id, worker_id="direct-url-retry")
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    assert candidate is not None
    candidate.status = CandidateStatus.CONFLICT_DETECTED
    candidate.conflicts = ["stale conflict"]
    candidate.validation_errors = ["stale validation error"]
    candidate.duplicate_opportunity_ids = [str(uuid.uuid4())]
    db_session.commit()
    reviewer = User(
        email="direct-url-reviewer@example.test",
        password_hash="not-used-by-service-test",
        role=UserRole.ADMIN,
    )
    db_session.add(reviewer)
    db_session.commit()

    retried = service.retry_candidate(
        candidate.id, reason="official source changed", actor=reviewer
    )

    assert retried.status is CandidateStatus.DISCOVERED
    assert retried.conflicts == []
    assert retried.validation_errors == []
    assert retried.duplicate_opportunity_ids == []
    assert retried.proposed_payload is None


def test_expanded_direct_url_stays_in_cited_staging_until_graph_support_exists(
    db_session,
) -> None:
    db_session.add(
        Institution(
            canonical_name="Embassy of Japan",
            slug="embassy-of-japan",
            institution_type="embassy",
            country_code="JP",
            identity_status="verified",
        )
    )
    db_session.commit()
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=FakeClaimProvider(claim_output()),
    )
    run = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.REVIEW_QUEUE,
        dry_run=False,
    )

    service.process_run(run.id, worker_id="mext-graph")

    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    assert candidate is not None
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW
    assert candidate.opportunity_id is None
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 0
    assert db_session.scalar(select(func.count()).select_from(ApplicationTrack)) == 0
    assert db_session.scalar(select(func.count()).select_from(Institution)) == 1
    assert db_session.scalar(select(func.count()).select_from(InstitutionParticipation)) == 0
    assert db_session.scalar(select(func.count()).select_from(FundingComponent)) == 0
    assert db_session.scalar(select(func.count()).select_from(RequiredDocument)) == 0
    assert db_session.scalar(select(func.count()).select_from(ApplicationStep)) == 0
    assert db_session.scalar(select(func.count()).select_from(ScopedDeadline)) == 0
    assert db_session.scalar(select(func.count()).select_from(SourceSnapshot)) == 0
    assert db_session.scalar(select(func.count()).select_from(GraphFieldEvidence)) == 0
    resolved = candidate.proposed_payload["resolved"]
    assert any(item["claim"]["entity_type"] == "programme" for item in resolved)
    assert any(item["claim"]["entity_type"] == "eligibility" for item in resolved)
    reviewer = User(
        email="expanded-staging-reviewer@example.test",
        password_hash="not-used-by-service-test",
        role=UserRole.ADMIN,
    )
    db_session.add(reviewer)
    db_session.commit()

    with pytest.raises(AppError) as exc_info:
        service.submit_candidate(candidate.id, notes="reviewed", actor=reviewer)

    assert exc_info.value.code == "catalogue_detail_extraction_review_only"
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_claim_resolution_rejects_bad_offsets_and_same_tier_conflicts() -> None:
    artifact_one = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="a" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    artifact_two = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url="https://scholarships.gov.uk/second",
        content_type="text/html",
        content_hash="b" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    claims_one = claim_output().claims
    conflicting = claim_output().model_copy(deep=True).claims
    conflicting[0].value.string_value = "Different Scholarship"
    conflicting[-1].excerpt_start += 1

    resolution = resolve_claims([(artifact_one, 1, claims_one), (artifact_two, 1, conflicting)])

    assert "scholarship:scholarship:name:same_tier_conflict" in resolution.conflicts
    assert any(item.endswith("evidence_span_invalid") for item in resolution.rejected)
    assert resolution.is_materializable is False


def test_claim_resolution_fails_closed_when_one_entity_key_spans_routes() -> None:
    artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="c" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    embassy_funding = claim_output().claims[11].model_copy(deep=True)
    university_funding = claim_output().claims[11].model_copy(deep=True)
    embassy_funding.scope.track_key = "embassy_recommendation"
    university_funding.scope.track_key = "university_recommendation"

    resolution = resolve_claims([(artifact, 1, [embassy_funding, university_funding])])

    assert "funding:tuition:coverage_status:ambiguous_scope_key" in resolution.conflicts
    assert resolution.is_materializable is False

    detail_resolution = resolve_claims(
        [(artifact, 1, [embassy_funding, university_funding])],
        require_detail=True,
    )
    assert not any(item.endswith("ambiguous_scope_key") for item in detail_resolution.conflicts)

    unsupported = claim_output().claims[5].model_copy(deep=True)
    unsupported.field_path = "eligibility.age"
    unsupported_resolution = resolve_claims([(artifact, 1, [unsupported])])
    assert any(
        item.endswith("eligibility.age:unsupported_field_path")
        for item in unsupported_resolution.rejected
    )

    contextless_year = claim_output().claims[4].model_copy(deep=True)
    contextless_year.excerpt = "2027"
    contextless_year.excerpt_end = contextless_year.excerpt_start + 4
    wrong_route = claim_output().claims[5].model_copy(deep=True)
    wrong_route.excerpt = "University Recommendation"
    wrong_route.excerpt_start = MEXT_TEXT.index(wrong_route.excerpt)
    wrong_route.excerpt_end = wrong_route.excerpt_start + len(wrong_route.excerpt)
    semantic_resolution = resolve_claims([(artifact, 1, [contextless_year, wrong_route])])
    assert any(
        item.endswith("intake_year:intake_year_context_missing")
        for item in semantic_resolution.rejected
    )
    assert any(
        item.endswith("name:embassy_route_evidence_mismatch")
        for item in semantic_resolution.rejected
    )


def test_claim_resolution_blocks_a_bundle_that_mixes_intake_cycles() -> None:
    first_artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="d" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    prior_text = MEXT_TEXT.replace("2027 intake", "2026 intake")
    prior_artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url="https://scholarships.gov.uk/mext-2026",
        content_type="text/html",
        content_hash="e" * 64,
        normalized_text=prior_text,
        extraction_method="normalized_text",
        byte_count=len(prior_text),
        character_count=len(prior_text),
    )
    current_cycle = claim_output().claims[4]
    prior_cycle = current_cycle.model_copy(deep=True)
    prior_cycle.entity_key = "2026"
    prior_cycle.scope.cycle_key = "2026"
    prior_cycle.value.integer_value = 2026
    prior_cycle.excerpt = "2026 intake"
    prior_cycle.excerpt_end = prior_cycle.excerpt_start + len(prior_cycle.excerpt)

    resolution = resolve_claims(
        [(first_artifact, 1, [current_cycle]), (prior_artifact, 1, [prior_cycle])]
    )

    assert "cycle:intake_year:multiple_cycles" in resolution.conflicts
    assert "cycle:scope:multiple_cycles" in resolution.conflicts
    assert resolution.is_materializable is False


def test_claim_resolution_canonicalizes_same_year_cycle_aliases() -> None:
    first_artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="d" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    second_artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url="https://scholarships.gov.uk/mext-2027",
        content_type="text/html",
        content_hash="e" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    first_cycle = claim_output().claims[4]
    second_cycle = first_cycle.model_copy(deep=True)
    second_cycle.entity_key = "arrival_2027_cycle"
    second_cycle.scope.cycle_key = "arrival_2027_cycle"

    resolution = resolve_claims(
        [(first_artifact, 1, [first_cycle]), (second_artifact, 1, [second_cycle])]
    )

    assert "cycle:intake_year:multiple_cycles" not in resolution.conflicts
    assert "cycle:scope:multiple_cycles" not in resolution.conflicts
    assert {item.claim.entity_key for item in resolution.resolved} == {"intake_2027"}
    assert {item.claim.scope.cycle_key for item in resolution.resolved} == {"intake_2027"}


def test_claim_resolution_rejects_a_route_inferred_from_generic_university_text() -> None:
    text = f"{MEXT_TEXT} Study at Japanese universities."
    artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="f" * 64,
        normalized_text=text,
        extraction_method="normalized_text",
        byte_count=len(text),
        character_count=len(text),
    )
    claim = claim_output().claims[6].model_copy(deep=True)
    claim.field_path = "track_type"
    claim.value.string_value = "university_recommendation"
    claim.excerpt = "Study at Japanese universities."
    claim.excerpt_start = text.index(claim.excerpt)
    claim.excerpt_end = claim.excerpt_start + len(claim.excerpt)

    resolution = resolve_claims([(artifact, 1, [claim])])

    assert any(item.endswith("university_route_evidence_mismatch") for item in resolution.rejected)
    assert resolution.resolved == []


def test_claim_resolution_separates_events_and_validates_resource_links() -> None:
    text = (
        "Arrival in Japan: April 2027. Application deadline: May 15, 2026. "
        "Download the Application form."
    )
    form_url = "https://scholarships.gov.uk/forms/application.pdf"
    artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="1" * 64,
        normalized_text=text,
        extraction_method="normalized_text",
        byte_count=len(text),
        character_count=len(text),
        fetch_metadata={"links": [{"url": form_url, "text": "Application form"}]},
    )
    deadline_template = claim_output().claims[14]
    arrival_deadline = deadline_template.model_copy(deep=True)
    arrival_deadline.entity_key = "arrival"
    arrival_deadline.value.string_value = "2027-04"
    arrival_deadline.excerpt = "Arrival in Japan: April 2027"
    arrival_deadline.excerpt_start = text.index(arrival_deadline.excerpt)
    arrival_deadline.excerpt_end = arrival_deadline.excerpt_start + len(arrival_deadline.excerpt)
    arrival_event = arrival_deadline.model_copy(deep=True)
    arrival_event.entity_type = ClaimEntityType.EVENT
    arrival_event.field_path = "date_text"
    valid_resource = arrival_deadline.model_copy(deep=True)
    valid_resource.entity_type = ClaimEntityType.RESOURCE
    valid_resource.entity_key = "application_form"
    valid_resource.field_path = "url"
    valid_resource.value.string_value = form_url
    valid_resource.excerpt = "Application form"
    valid_resource.excerpt_start = text.index(valid_resource.excerpt)
    valid_resource.excerpt_end = valid_resource.excerpt_start + len(valid_resource.excerpt)
    invented_resource = valid_resource.model_copy(deep=True)
    invented_resource.entity_key = "invented_form"
    invented_resource.value.string_value = "https://scholarships.gov.uk/forms/invented.pdf"

    resolution = resolve_claims(
        [(artifact, 1, [arrival_deadline, arrival_event, valid_resource, invented_resource])]
    )

    assert any(item.endswith("non_deadline_event_misclassified") for item in resolution.rejected)
    assert any(item.endswith("resource_url_not_in_fetched_links") for item in resolution.rejected)
    accepted = {
        (item.claim.entity_type, item.claim.entity_key, item.claim.field_path)
        for item in resolution.resolved
    }
    assert (ClaimEntityType.EVENT, "arrival", "date_text") in accepted
    assert (ClaimEntityType.RESOURCE, "application_form", "url") in accepted


def test_compatibility_resolution_defers_programme_completeness_to_persisted_topology() -> None:
    artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="2" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    claims = [item for index, item in enumerate(claim_output().claims) if index != 17]

    resolution = resolve_claims(
        [(artifact, 1, claims)],
        require_detail=True,
        objective_coverage={
            "identity": "complete",
            "programmes": "complete",
            "programme_details": "complete",
            "routes": "complete",
            "eligibility": "complete",
            "eligibility_context": "complete",
            "documents_core": "complete",
            "documents_requirements": "complete",
            "documents_counts": "complete",
            "documents_format": "complete",
            "funding": "complete",
            "application_timeline": "complete",
        },
    )

    assert any(
        cell.state.value in {"partial", "unknown"}
        and "persist_and_evaluate_topology" in cell.missing_frontier_reasons
        for cell in resolution.scope_coverage
    )
    assert resolution.is_materializable is False


def test_multi_programme_compatibility_resolution_requires_topology_evaluation() -> None:
    artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="4" * 64,
        normalized_text=MEXT_TEXT,
        extraction_method="normalized_text",
        byte_count=len(MEXT_TEXT),
        character_count=len(MEXT_TEXT),
    )
    claims = claim_output().model_copy(deep=True).claims
    undergraduate_name = claims[16].model_copy(deep=True)
    undergraduate_name.entity_key = "undergraduate_students"
    undergraduate_name.scope.programme_key = "undergraduate_students"
    undergraduate_name.value.string_value = "Undergraduate Students"
    undergraduate_name.excerpt = "Undergraduate"
    undergraduate_name.excerpt_start = MEXT_TEXT.index("Undergraduate")
    undergraduate_name.excerpt_end = undergraduate_name.excerpt_start + len("Undergraduate")
    undergraduate_degrees = claims[17].model_copy(deep=True)
    undergraduate_degrees.entity_key = "undergraduate_students"
    undergraduate_degrees.scope.programme_key = "undergraduate_students"
    undergraduate_degrees.value.string_list_value = ["bachelors"]
    undergraduate_degrees.excerpt = "Undergraduate"
    undergraduate_degrees.excerpt_start = MEXT_TEXT.index("Undergraduate")
    undergraduate_degrees.excerpt_end = undergraduate_degrees.excerpt_start + len("Undergraduate")
    claims.extend([undergraduate_name, undergraduate_degrees])

    resolution = resolve_claims(
        [(artifact, 1, claims)],
        require_detail=True,
        objective_coverage={
            "identity": "complete",
            "programmes": "complete",
            "programme_details": "complete",
            "routes": "complete",
            "eligibility": "complete",
            "eligibility_context": "complete",
            "documents_core": "complete",
            "documents_requirements": "complete",
            "documents_counts": "complete",
            "documents_format": "complete",
            "funding": "complete",
            "application_timeline": "complete",
        },
    )

    assert any(error.startswith("coverage:") for error in resolution.completeness_errors)
    assert all(
        "persist_and_evaluate_topology" in cell.missing_frontier_reasons
        for cell in resolution.scope_coverage
        if cell.state.value != "complete"
    )


def test_objective_coverage_is_partial_when_any_official_source_is_partial() -> None:
    from app.modules.catalogue_ingestion.claim_schemas import ObjectiveCoverageState

    assert (
        _aggregate_coverage([ObjectiveCoverageState.COMPLETE, ObjectiveCoverageState.PARTIAL])
        is ObjectiveCoverageState.PARTIAL
    )


def test_compatible_application_method_evidence_coexists_without_a_false_conflict() -> None:
    text = (
        f"{MEXT_TEXT} Apply through the Embassy of Japan. "
        "Applications are submitted to the diplomatic mission."
    )
    artifact = CatalogueSourceArtifact(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        final_url=OFFICIAL_URL,
        content_type="text/html",
        content_hash="3" * 64,
        normalized_text=text,
        extraction_method="normalized_text",
        byte_count=len(text),
        character_count=len(text),
    )
    first = claim_output().claims[5].model_copy(deep=True)
    first.field_path = "application_method"
    first.value.string_value = "Apply through the Embassy of Japan"
    first.excerpt = "Apply through the Embassy of Japan"
    first.excerpt_start = text.index(first.excerpt)
    first.excerpt_end = first.excerpt_start + len(first.excerpt)
    second = first.model_copy(deep=True)
    second.value.string_value = "Applications are submitted to the diplomatic mission"
    second.excerpt = "Applications are submitted to the diplomatic mission"
    second.excerpt_start = text.index(second.excerpt)
    second.excerpt_end = second.excerpt_start + len(second.excerpt)

    resolution = resolve_claims([(artifact, 1, [first, second])])

    assert resolution.conflicts == []
    assert len(resolution.resolved) == 2


def test_seed_parser_fails_closed_for_image_only_pdf() -> None:
    with pytest.raises(SeedParseError, match="malformed_seed_pdf"):
        LocalSeedDocumentParser().parse(
            LoadedSeed("seed.pdf", "x" * 64, b"not-a-pdf", "application/pdf")
        )


def test_remote_seed_redirect_cannot_leave_private_blob_boundary(monkeypatch) -> None:
    class RedirectedResponse:
        headers = type("Headers", (), {"get_content_type": lambda self: "text/plain"})()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self) -> str:
            return "https://unreviewed.example/seed.txt"

        def read(self, limit: int) -> bytes:
            del limit
            return b"Example Scholarship"

    class Opener:
        def open(self, request, timeout: int):
            assert request.get_header("Authorization") == "Bearer managed-identity"
            del timeout
            return RedirectedResponse()

    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.seed_parser.validate_monitor_url", lambda url: None
    )
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.seed_parser.validate_response_peer",
        lambda response: None,
    )
    monkeypatch.setattr(
        "app.modules.catalogue_ingestion.seed_parser.urllib.request.build_opener",
        lambda handler: Opener(),
    )
    credential = type(
        "Credential",
        (),
        {"get_token": lambda self, scope: type("Token", (), {"token": "managed-identity"})()},
    )()
    with pytest.raises(SeedParseError, match="redirected_outside_azure_blob"):
        SeedSourceLoader(credential=credential).load(
            "https://private.blob.core.windows.net/seeds/input.txt"
        )


def test_official_source_classification_is_deterministic() -> None:
    classifier = OfficialSourceClassifier()
    assert classifier.classify(OFFICIAL_URL).trust_tier == 2
    assert (
        classifier.classify(
            "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/"
        ).trust_tier
        == 2
    )
    assert not classifier.classify("https://scholarshipportal.com/example").is_official
    assert classifier.classify(
        "https://funding.example.edu/program",
        university_website_url="https://example.edu",
    ).is_official
    assert not classifier.classify("https://unknown.example/program").is_official


def test_mext_crawl_rejects_official_but_topic_unrelated_children() -> None:
    root = FakeFetcher("Japanese Government MEXT Scholarship").fetch(
        "https://www.studyinjapan.go.jp/en/mext"
    )
    relevant = FakeFetcher("MEXT Embassy Recommendation application").fetch(
        "https://www.studyinjapan.go.jp/en/mext-application"
    )
    unrelated = FakeFetcher("Yamagata privately financed student scholarship").fetch(
        "https://www.studyinjapan.go.jp/en/other-scholarship"
    )

    assert _crawler_child_matches_root(root, relevant) is True
    assert _crawler_child_matches_root(root, unrelated) is False


def test_extraction_contract_rejects_extra_fields_and_schema_is_strict() -> None:
    raw = extraction_output().model_dump(mode="json")
    raw["invented"] = "not allowed"
    with pytest.raises(ValidationError):
        CatalogueExtractionOutput.model_validate(raw)

    schema = azure_structured_output_schema()

    def assert_objects_are_strict(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" or "properties" in value:
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value.get("properties", {}))
            for item in value.values():
                assert_objects_are_strict(item)
        elif isinstance(value, list):
            for item in value:
                assert_objects_are_strict(item)

    assert_objects_are_strict(schema)

    unsupported_keywords = {
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "multipleOf",
        "patternProperties",
        "unevaluatedProperties",
        "propertyNames",
        "minProperties",
        "maxProperties",
        "unevaluatedItems",
        "contains",
        "minContains",
        "maxContains",
        "minItems",
        "maxItems",
        "uniqueItems",
    }

    def assert_azure_supported_schema(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"properties", "$defs"} and isinstance(item, dict):
                    for child_schema in item.values():
                        assert_azure_supported_schema(child_schema)
                    continue
                assert key not in unsupported_keywords
                assert_azure_supported_schema(item)
        elif isinstance(value, list):
            for item in value:
                assert_azure_supported_schema(item)

    assert_azure_supported_schema(schema)


def test_validation_requires_exact_official_evidence_and_surfaces_conflicts() -> None:
    valid = validate_and_build_proposal(
        extraction_output(),
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT,
        source_title="Official source",
        content_hash="a" * 64,
        trust_tier=2,
    )
    assert valid.errors == []
    assert valid.payload is not None
    assert valid.payload.status is OpportunityStatus.DRAFT
    assert valid.payload.source.verification_status is VerificationStatus.NEEDS_REVIEW

    unsupported = validate_and_build_proposal(
        extraction_output(),
        source_url=OFFICIAL_URL,
        source_text="Different official page content with no supporting excerpts.",
        source_title="Official source",
        content_hash="b" * 64,
        trust_tier=2,
    )
    assert unsupported.payload is None
    assert any("excerpt was not found" in error for error in unsupported.errors)

    conflict = validate_and_build_proposal(
        extraction_output(conflicts=["Two deadlines are stated"]),
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT,
        source_title="Official source",
        content_hash="c" * 64,
        trust_tier=2,
    )
    assert conflict.payload is None
    assert any("conflicts" in error for error in conflict.errors)


def test_pipeline_reaches_review_boundary_without_publication(db_session, tmp_path) -> None:
    extractor = FakeExtractionProvider(extraction_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(),
        extractor=extractor,
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [{"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL}],
            )
        ),
        mode=IngestionMode.VALIDATION,
        dry_run=False,
    )
    result = service.process_run(run.id, worker_id="test-worker", batch_size=1)
    candidate = db_session.scalar(select(CatalogueCandidate))

    assert result.status is IngestionRunStatus.COMPLETED_WITH_REVIEW
    assert result.model_calls == 1
    assert candidate is not None
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_review_queue_creates_only_existing_domain_draft(db_session, tmp_path) -> None:
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(),
        extractor=FakeExtractionProvider(extraction_output()),
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [{"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL}],
            )
        ),
        mode=IngestionMode.REVIEW_QUEUE,
        dry_run=False,
    )
    service.process_run(run.id, worker_id="test-worker", batch_size=10)
    candidate = db_session.scalar(select(CatalogueCandidate))
    opportunity = db_session.scalar(select(Opportunity))

    assert candidate is not None
    assert candidate.status is CandidateStatus.SUBMITTED_FOR_REVIEW
    assert opportunity is not None
    assert opportunity.status is OpportunityStatus.DRAFT
    assert opportunity.sources[0].verification_status is VerificationStatus.NEEDS_REVIEW

    reviewer = User(
        email="catalogue-reviewer@example.test",
        password_hash="not-used-by-service-test",
        role=UserRole.ADMIN,
    )
    db_session.add(reviewer)
    db_session.commit()
    OpportunityService(db_session).apply_review_action(
        opportunity.id,
        ReviewActionRequest(action=ReviewAction.PUBLISH),
        reviewed_by=reviewer,
    )
    db_session.refresh(candidate)
    db_session.refresh(opportunity)
    assert candidate.status is CandidateStatus.PUBLISHED
    assert opportunity.status is OpportunityStatus.ACTIVE


def test_seed_and_extracted_identity_mismatch_fails_validation(db_session, tmp_path) -> None:
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(),
        extractor=FakeExtractionProvider(extraction_output()),
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [{"name": "Unrelated Global Award", "possible_official_url": OFFICIAL_URL}],
            )
        ),
        mode=IngestionMode.VALIDATION,
        dry_run=False,
    )
    service.process_run(run.id, worker_id="test-worker", batch_size=1)
    candidate = db_session.scalar(select(CatalogueCandidate))

    assert candidate is not None
    assert candidate.status is CandidateStatus.VALIDATION_FAILED
    assert any("programme identity" in error for error in candidate.validation_errors)
    assert db_session.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_content_hash_reuse_avoids_a_second_model_call(db_session, tmp_path) -> None:
    extractor = FakeExtractionProvider(extraction_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(),
        extractor=extractor,
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [
                    {"name": "The Example Scholarship", "possible_official_url": OFFICIAL_URL},
                    {"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL},
                ],
            )
        ),
        mode=IngestionMode.VALIDATION,
        dry_run=False,
    )
    service.process_run(run.id, worker_id="test-worker", batch_size=2)

    assert extractor.calls == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogueExtractionAttempt)) == 2
    assert set(db_session.scalars(select(CatalogueCandidate.status))) == {
        CandidateStatus.READY_FOR_REVIEW
    }


def test_budget_exhaustion_is_explicit_and_resumeable(db_session, tmp_path) -> None:
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(catalogue_ai_max_calls_per_run=0),
        fetcher=FakeFetcher(),
        extractor=FakeExtractionProvider(extraction_output()),
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [{"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL}],
            )
        ),
        mode=IngestionMode.EXTRACTION,
        dry_run=False,
    )
    result = service.process_run(run.id, worker_id="test-worker", batch_size=1)
    candidate = db_session.scalar(select(CatalogueCandidate))

    assert result.status is IngestionRunStatus.BUDGET_EXHAUSTED
    assert result.failure_code == "run_budget_exhausted"
    assert candidate is not None
    assert candidate.status is CandidateStatus.SOURCE_FETCHED
    assert candidate.claimed_by is None


def test_open_provider_circuit_defers_candidate_without_calling_provider(
    db_session, tmp_path
) -> None:
    from app.modules.catalogue_ingestion.provider_attempts import ProviderFailureClass
    from app.modules.catalogue_ingestion.scheduling import CatalogueProviderScheduler

    extractor = FakeExtractionProvider(extraction_output())
    settings = enabled_settings()
    service = CatalogueIngestionService(
        db_session,
        settings,
        fetcher=FakeFetcher(),
        extractor=extractor,
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [{"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL}],
            )
        ),
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )
    CatalogueProviderScheduler(db_session, settings).record_failure(
        provider=extractor.name,
        deployment=settings.catalogue_ai_model,
        failure_class=ProviderFailureClass.AUTHENTICATION_CONFIGURATION_ERROR,
    )

    result = service.process_run(run.id, worker_id="circuit-test", batch_size=1)
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )

    assert result.status is IngestionRunStatus.PENDING
    assert result.failure_code == "provider_circuit_open"
    assert extractor.calls == 0
    assert candidate is not None
    assert candidate.status is CandidateStatus.SOURCE_FETCHED
    assert candidate.claimed_by is None
    assert candidate.next_attempt_at is not None


def test_actual_cost_overflow_preserves_paid_output_for_resume(db_session, tmp_path) -> None:
    class CostlyExtractionProvider:
        name = "fake"
        model = "costly-test-v1"

        def __init__(self) -> None:
            self.calls = 0

        def extract(self, *, source_url: str, source_text: str) -> ExtractionResult:
            del source_url, source_text
            self.calls += 1
            return ExtractionResult(
                output=extraction_output(),
                usage=ExtractionUsage(
                    input_tokens=100,
                    output_tokens=50,
                    estimated_cost=Decimal("0.002"),
                    latency_ms=1,
                ),
            )

    extractor = CostlyExtractionProvider()
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(
            catalogue_ai_max_output_tokens=256,
            catalogue_ai_max_estimated_cost_per_run=Decimal("0.001"),
        ),
        fetcher=FakeFetcher(),
        extractor=extractor,
    )
    run = service.create_run_from_source(
        str(
            write_seed(
                tmp_path,
                [{"name": "Example Scholarship", "possible_official_url": OFFICIAL_URL}],
            )
        ),
        mode=IngestionMode.EXTRACTION,
        dry_run=False,
    )

    stopped = service.process_run(run.id, worker_id="test-worker", batch_size=1)
    attempt = db_session.scalar(select(CatalogueExtractionAttempt))
    candidate = db_session.scalar(select(CatalogueCandidate))

    assert stopped.status is IngestionRunStatus.BUDGET_EXHAUSTED
    assert stopped.model_calls == 1
    assert stopped.estimated_cost == Decimal("0.002")
    assert attempt is not None
    assert attempt.status.value == "succeeded"
    assert attempt.output_json is not None
    assert candidate is not None
    assert candidate.status is CandidateStatus.SOURCE_FETCHED
    assert candidate.claimed_by is None

    resumed = service.process_run(run.id, worker_id="resume-worker", batch_size=1)

    assert resumed.status is IngestionRunStatus.COMPLETED_WITH_REVIEW
    assert resumed.failure_code is None
    assert extractor.calls == 1
    assert db_session.scalar(select(func.count()).select_from(CatalogueExtractionAttempt)) == 1
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW


def test_direct_claim_cost_overflow_preserves_paid_output_for_resume(db_session) -> None:
    class CostlyClaimProvider:
        name = "fake_claims"
        model = "costly-claims-v2"

        def __init__(self) -> None:
            self.calls = 0

        def extract_claims(
            self,
            *,
            source_url: str,
            source_text: str,
            objective: ClaimObjective,
            source_links: list[dict[str, str | None]],
        ) -> ClaimExtractionResult:
            del source_url, source_text, source_links
            self.calls += 1
            return ClaimExtractionResult(
                output=_normalize_claim_output(claim_output(), MEXT_TEXT, objective=objective),
                usage=ExtractionUsage(
                    input_tokens=100,
                    output_tokens=50,
                    estimated_cost=Decimal("0.002"),
                    latency_ms=1,
                ),
            )

    extractor = CostlyClaimProvider()
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(
            catalogue_ai_max_output_tokens=256,
            catalogue_ai_max_estimated_cost_per_run=Decimal("0.001"),
        ),
        fetcher=FakeFetcher(MEXT_TEXT),
        claim_extractor=extractor,
    )
    run = service.create_run_from_url(
        OFFICIAL_URL,
        mode=IngestionMode.EXTRACTION,
        dry_run=True,
    )

    stopped = service.process_run(run.id, worker_id="direct-cost", batch_size=1)
    candidate = db_session.scalar(
        select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id)
    )
    attempt = db_session.scalar(select(CatalogueExtractionAttempt))

    assert stopped.status is IngestionRunStatus.BUDGET_EXHAUSTED
    assert stopped.model_calls == 1
    assert stopped.estimated_cost == Decimal("0.002")
    assert candidate is not None
    assert candidate.status is CandidateStatus.SOURCE_FETCHED
    assert attempt is not None
    assert attempt.output_json is not None

    run_row = db_session.get(CatalogueIngestionRun, run.id)
    assert run_row is not None
    run_row.max_estimated_cost = Decimal("0.030")
    db_session.commit()
    resumed = service.process_run(run.id, worker_id="direct-cost-resume", batch_size=1)

    assert resumed.status is IngestionRunStatus.COMPLETED_WITH_REVIEW
    assert extractor.calls == 12
    assert db_session.scalar(select(func.count()).select_from(CatalogueExtractionAttempt)) == 12
    assert candidate.status is CandidateStatus.READY_FOR_REVIEW


def test_500_candidate_run_is_bounded_and_never_calls_ai(db_session, tmp_path) -> None:
    rows = [{"name": f"Scholarship {index:03d}"} for index in range(500)]
    extractor = FakeExtractionProvider(extraction_output())
    service = CatalogueIngestionService(
        db_session,
        enabled_settings(),
        fetcher=FakeFetcher(),
        extractor=extractor,
    )
    run = service.create_run_from_source(
        str(write_seed(tmp_path, rows)),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
        max_candidates=500,
    )
    result = service.process_run(run.id, worker_id="scale-test", batch_size=37)

    assert result.checkpoint_cursor == 500
    assert result.model_calls == 0
    assert extractor.calls == 0
    assert result.aggregate_summary["needs_review"] == 500
    assert result.aggregate_summary["provider_attempts"] == 0
    assert result.aggregate_summary["provider_accounting_uncertain"] == 0
    assert result.aggregate_summary["provider_cost_lower_bound"] == "0"
    assert result.aggregate_summary["provider_cost_upper_bound"] == "0"


def test_idempotency_distinguishes_new_cycles_without_duplicating_same_cycle(
    db_session, tmp_path
) -> None:
    rows = [
        {"name": "Example Scholarship", "cycle": "2026-27", "intake_year": 2026},
        {"name": "Example Scholarship", "cycle": "2027-28", "intake_year": 2027},
        {"name": "Example Scholarship", "cycle": "2026-27", "intake_year": 2026},
    ]
    service = CatalogueIngestionService(db_session, enabled_settings())
    run = service.create_run_from_source(
        str(write_seed(tmp_path, rows)),
        mode=IngestionMode.CANDIDATE_ONLY,
        dry_run=True,
    )

    candidates = list(
        db_session.scalars(select(CatalogueCandidate).where(CatalogueCandidate.run_id == run.id))
    )
    assert {(item.seed_cycle, item.seed_intake_year) for item in candidates} == {
        ("2026-27", 2026),
        ("2027-28", 2027),
    }


def test_cost_and_evaluation_report_fail_closed() -> None:
    assert estimate_cost(
        1_000_000,
        500_000,
        input_per_million=Decimal("1"),
        output_per_million=Decimal("2"),
    ) == Decimal("2.000000")
    gold = [
        GoldItem(
            id="example",
            official_url=OFFICIAL_URL,
            source_text=SOURCE_TEXT,
            expected={"identity": {"name": "Example Scholarship"}},
            support={"identity.name": "Example Scholarship offers awards."},
            expected_unknown=["application.application_deadline"],
        )
    ]
    report = evaluate(FakeExtractionProvider(extraction_output()), gold, max_calls=1)
    assert report.schema_validation_rate == 1
    assert report.successful_extractions == 1
    assert report.provider_failure_count == 0
    assert report.official_source_correctness == 1
    assert report.expected_unknown_count == 1
    assert report.expected_unknown_accuracy == 1
    assert report.false_confident_values == 0
    assert report.field_accuracy["identity.name"] == 1

    class FailingProvider:
        name = "failing"
        model = "test"

        def extract(self, *, source_url: str, source_text: str):
            del source_url, source_text
            raise ExtractionProviderError("invalid response")

    failed = evaluate(FailingProvider(), gold)
    assert failed.schema_validation_rate == 0
    assert failed.successful_extractions == 0
    assert failed.provider_failure_count == 1
    assert failed.official_source_correctness == 0


def test_azure_provider_uses_entra_strict_output_as_single_attempt_transport() -> None:
    output = extraction_output()
    response_body = json.dumps(
        {
            "choices": [{"message": {"content": output.model_dump_json()}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    ).encode()

    class Credential:
        def get_token(self, scope: str):
            assert scope == "https://cognitiveservices.azure.com/.default"
            return type("Token", (), {"token": "entra-token"})()

    class Response:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit: int) -> bytes:
            assert limit > len(response_body)
            return response_body

    class Opener:
        def __init__(self) -> None:
            self.calls = 0
            self.request = None

        def open(self, request, timeout: int):
            self.calls += 1
            self.request = request
            assert timeout == 30
            return Response()

    opener = Opener()
    waits: list[float] = []
    provider = AzureOpenAIExtractionProvider(
        enabled_settings(), credential=Credential(), opener=opener, sleeper=waits.append
    )
    result = provider.extract(source_url=OFFICIAL_URL, source_text=SOURCE_TEXT)

    assert opener.calls == 1
    assert waits == []
    assert opener.request.get_header("Authorization") == "Bearer entra-token"
    sent = json.loads(opener.request.data)
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert result.output.identity.name == "Example Scholarship"
    assert result.usage.estimated_cost == Decimal("0.000200")


def test_azure_claim_provider_uses_strict_schema_and_preserves_billed_failure_usage() -> None:
    import time

    schema = _azure_schema(ClaimExtractionOutput)

    def assert_objects_are_strict(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" or "properties" in value:
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value.get("properties", {}))
            for item in value.values():
                assert_objects_are_strict(item)
        elif isinstance(value, list):
            for item in value:
                assert_objects_are_strict(item)

    assert_objects_are_strict(schema)
    programme_schema = _objective_azure_schema(ClaimObjective.PROGRAMMES)
    assert programme_schema["$defs"]["ClaimEntityType"]["enum"] == ["programme"]
    assert programme_schema["$defs"]["ClaimObjective"]["enum"] == ["programmes"]
    assert "name" in programme_schema["$defs"]["ExtractedClaim"]["properties"]["field_path"]["enum"]
    provider = AzureOpenAIClaimProvider(enabled_settings(), credential=object())
    response_body = json.dumps(
        {
            "choices": [{"message": {"content": claim_output().model_dump_json()}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    ).encode()
    result = provider._parse(response_body, time.perf_counter())

    assert len(result.output.claims) == len(claim_output().claims)
    assert len(result.output.claims) > 12
    assert result.usage.estimated_cost == Decimal("0.000200")

    salvageable = claim_output().model_dump(mode="json")
    salvageable["claims"].append(
        {
            "entity_type": "scholarship",
            "entity_key": "blank",
            "field_path": "alias",
            "value": {
                "string_value": None,
                "decimal_value": None,
                "integer_value": None,
                "boolean_value": None,
                "string_list_value": None,
            },
            "scope": {
                "cycle_key": None,
                "track_key": None,
                "institution_key": None,
                "programme_key": None,
            },
            "excerpt": "",
            "excerpt_start": 0,
            "excerpt_end": 0,
            "basis": "explicit",
        }
    )
    salvaged_response = json.dumps(
        {
            "choices": [{"message": {"content": json.dumps(salvageable)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    ).encode()
    salvaged = provider._parse(salvaged_response, time.perf_counter())
    assert len(salvaged.output.claims) == len(claim_output().claims)
    assert salvaged.output.coverage_state.value == "complete"
    assert "provider_null_placeholders_dropped:1" in salvaged.output.warnings

    invalid_response = json.dumps(
        {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    ).encode()
    with pytest.raises(ExtractionSchemaError) as exc_info:
        provider._parse(invalid_response, time.perf_counter())

    assert exc_info.value.usage is not None
    assert exc_info.value.usage.estimated_cost == Decimal("0.000200")
    assert "claims" in str(exc_info.value)

    truncated_response = json.dumps(
        {
            "choices": [{"finish_reason": "length", "message": {"content": "{"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 4000},
        }
    ).encode()
    with pytest.raises(ExtractionSchemaError) as truncated_info:
        provider._parse(truncated_response, time.perf_counter())

    assert truncated_info.value.code == "ai_output_truncated"
    assert truncated_info.value.usage is not None


def test_azure_provider_does_not_retry_non_retryable_http_errors() -> None:
    class Credential:
        def get_token(self, scope: str):
            del scope
            return type("Token", (), {"token": "entra-token"})()

    class Opener:
        def __init__(self) -> None:
            self.calls = 0

        def open(self, request, timeout: int):
            del timeout
            self.calls += 1
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    opener = Opener()
    waits: list[float] = []
    provider = AzureOpenAIExtractionProvider(
        enabled_settings(), credential=Credential(), opener=opener, sleeper=waits.append
    )

    with pytest.raises(ExtractionProviderError):
        provider.extract(source_url=OFFICIAL_URL, source_text=SOURCE_TEXT)

    assert opener.calls == 1
    assert waits == []


def test_catalogue_ai_retry_delay_honors_retry_after_and_cap() -> None:
    error = urllib.error.HTTPError(
        OFFICIAL_URL,
        429,
        "Too Many Requests",
        {"Retry-After": "30"},
        None,
    )

    assert extraction_retry_delay(error, attempt=0, maximum=60) == 30
    assert extraction_retry_delay(error, attempt=0, maximum=10) == 10
    error.headers["Retry-After"] = "invalid"
    assert extraction_retry_delay(error, attempt=1, maximum=60) == 2
    error.headers["Retry-After"] = "NaN"
    assert extraction_retry_delay(error, attempt=2, maximum=60) == 4


def test_azure_claim_provider_surfaces_exhausted_rate_limit() -> None:
    class Credential:
        def get_token(self, scope: str):
            del scope
            return type("Token", (), {"token": "entra-token"})()

    class Opener:
        def open(self, request, timeout: int):
            del timeout
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "30"},
                None,
            )

    provider = AzureOpenAIClaimProvider(
        enabled_settings(catalogue_ai_max_retries=0),
        credential=Credential(),
        opener=Opener(),
    )

    with pytest.raises(ExtractionProviderRateLimited) as exc_info:
        provider.extract_claims(source_url=OFFICIAL_URL, source_text=SOURCE_TEXT)

    assert exc_info.value.code == "ai_rate_limited"


def test_semantic_validation_rejects_country_inferred_from_university() -> None:
    raw = extraction_output().model_dump(mode="json")
    inferred_excerpt = "Applicants study at the University of Edinburgh."
    raw["evidence"][2]["excerpt"] = inferred_excerpt

    output = CatalogueExtractionOutput.model_validate(raw)
    source_text = SOURCE_TEXT.replace(
        "Applicants study in the United Kingdom.",
        inferred_excerpt,
    )

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=source_text,
        source_title="Official source",
        content_hash="f" * 64,
        trust_tier=2,
    )

    assert any(
        "identity.country: evidence does not explicitly name" in error for error in validated.errors
    )
    assert validated.payload is None


def test_semantic_validation_rejects_generic_costs_as_tuition_coverage() -> None:
    raw = extraction_output().model_dump(mode="json")
    excerpt = "Full scholarships cover participation costs and contribute to living expenses."
    raw["funding"]["tuition_coverage_status"] = "confirmed"
    raw["evidence"].append(
        {
            "field_path": "funding.tuition_coverage_status",
            "source_url": OFFICIAL_URL,
            "section_label": "Funding",
            "locator": None,
            "excerpt": excerpt,
            "basis": "explicit",
        }
    )

    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT + " " + excerpt,
        source_title="Official source",
        content_hash="1" * 64,
        trust_tier=2,
    )

    assert any(
        "funding.tuition_coverage_status: evidence does not support "
        "the claimed tuition coverage status" in error
        for error in validated.errors
    )
    assert validated.payload is None


def test_semantic_validation_rejects_graduates_as_minimum_academic_requirement() -> None:
    raw = extraction_output().model_dump(mode="json")
    excerpt = "The programme supports rigorously selected graduates from developing countries."
    raw["eligibility"]["minimum_academic_requirement"] = "graduates"
    raw["evidence"].append(
        {
            "field_path": "eligibility.minimum_academic_requirement",
            "source_url": OFFICIAL_URL,
            "section_label": "Eligibility",
            "locator": None,
            "excerpt": excerpt,
            "basis": "explicit",
        }
    )

    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT + " " + excerpt,
        source_title="Official source",
        content_hash="2" * 64,
        trust_tier=2,
    )

    assert any(
        "minimum_academic_requirement: evidence does not state an explicit" in error
        for error in validated.errors
    )
    assert validated.payload is None


def test_semantic_validation_accepts_explicit_tuition_and_degree_requirement() -> None:
    raw = extraction_output().model_dump(mode="json")
    tuition_excerpt = "Full tuition fees are covered by the scholarship."
    academic_excerpt = "Applicants must have a bachelor's degree."

    raw["funding"]["tuition_coverage_status"] = "confirmed"
    raw["eligibility"]["minimum_academic_requirement"] = "bachelor's degree"

    raw["evidence"].extend(
        [
            {
                "field_path": "funding.tuition_coverage_status",
                "source_url": OFFICIAL_URL,
                "section_label": "Funding",
                "locator": None,
                "excerpt": tuition_excerpt,
                "basis": "explicit",
            },
            {
                "field_path": "eligibility.minimum_academic_requirement",
                "source_url": OFFICIAL_URL,
                "section_label": "Eligibility",
                "locator": None,
                "excerpt": academic_excerpt,
                "basis": "explicit",
            },
        ]
    )

    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT + " " + tuition_excerpt + " " + academic_excerpt,
        source_title="Official source",
        content_hash="3" * 64,
        trust_tier=2,
    )

    assert validated.errors == []
    assert validated.payload is not None


def test_semantic_country_matching_uses_real_word_boundaries() -> None:
    raw = extraction_output().model_dump(mode="json")
    raw["identity"]["country"] = "Mali"

    excerpt = "Applicants study in Somalia."
    raw["evidence"][2]["excerpt"] = excerpt

    output = CatalogueExtractionOutput.model_validate(raw)
    source_text = SOURCE_TEXT.replace(
        "Applicants study in the United Kingdom.",
        excerpt,
    )

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=source_text,
        source_title="Official source",
        content_hash="4" * 64,
        trust_tier=2,
    )

    assert any(
        "identity.country: evidence does not explicitly name" in error for error in validated.errors
    )
    assert validated.payload is None


def test_semantic_validation_rejects_confirmed_tuition_with_negative_evidence() -> None:
    raw = extraction_output().model_dump(mode="json")
    excerpt = "Tuition fees are not covered by the scholarship."

    raw["funding"]["tuition_coverage_status"] = "confirmed"
    raw["evidence"].append(
        {
            "field_path": "funding.tuition_coverage_status",
            "source_url": OFFICIAL_URL,
            "section_label": "Funding",
            "locator": None,
            "excerpt": excerpt,
            "basis": "explicit",
        }
    )

    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT + " " + excerpt,
        source_title="Official source",
        content_hash="5" * 64,
        trust_tier=2,
    )

    assert any("claimed tuition coverage status" in error for error in validated.errors)
    assert validated.payload is None


def test_semantic_validation_accepts_explicit_tuition_noncoverage() -> None:
    raw = extraction_output().model_dump(mode="json")
    excerpt = "Tuition fees are not covered by the scholarship."

    raw["funding"]["tuition_coverage_status"] = "not_covered"
    raw["evidence"].append(
        {
            "field_path": "funding.tuition_coverage_status",
            "source_url": OFFICIAL_URL,
            "section_label": "Funding",
            "locator": None,
            "excerpt": excerpt,
            "basis": "explicit",
        }
    )

    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT + " " + excerpt,
        source_title="Official source",
        content_hash="6" * 64,
        trust_tier=2,
    )

    assert validated.errors == []
    assert validated.payload is not None


def test_semantic_validation_rejects_negated_academic_requirement() -> None:
    raw = extraction_output().model_dump(mode="json")
    excerpt = "A bachelor's degree is not required."

    raw["eligibility"]["minimum_academic_requirement"] = "bachelor's degree"
    raw["evidence"].append(
        {
            "field_path": "eligibility.minimum_academic_requirement",
            "source_url": OFFICIAL_URL,
            "section_label": "Eligibility",
            "locator": None,
            "excerpt": excerpt,
            "basis": "explicit",
        }
    )

    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT + " " + excerpt,
        source_title="Official source",
        content_hash="7" * 64,
        trust_tier=2,
    )

    assert any(
        "minimum_academic_requirement: evidence does not state an explicit" in error
        for error in validated.errors
    )
    assert validated.payload is None


def test_validation_accepts_equivalent_apostrophe_encoding_in_evidence() -> None:
    raw = extraction_output().model_dump(mode="json")
    raw["evidence"][0]["excerpt"] = "Example Scholar\x19s Award"
    output = CatalogueExtractionOutput.model_validate(raw)

    source_text = SOURCE_TEXT + " Example Scholar" + chr(0x2019) + "s Award"

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=source_text,
        source_title="Official source",
        content_hash="d" * 64,
        trust_tier=2,
    )

    assert validated.errors == []
    assert validated.payload is not None


def test_non_mandatory_ai_rule_is_not_added_to_structured_matching() -> None:
    raw = extraction_output().model_dump(mode="json")
    raw["eligibility"]["rules"] = [
        {
            "rule_type": "target_degree",
            "operator": "equals",
            "value": "Masters",
            "unit": None,
            "grading_scale": None,
            "required": False,
            "confidence": "high",
        }
    ]
    output = CatalogueExtractionOutput.model_validate(raw)

    validated = validate_and_build_proposal(
        output,
        source_url=OFFICIAL_URL,
        source_text=SOURCE_TEXT,
        source_title="Official source",
        content_hash="e" * 64,
        trust_tier=2,
    )

    assert validated.errors == []
    assert validated.payload is not None
    assert validated.payload.eligibility_rules == []
    assert any(
        "Non-mandatory AI-extracted eligibility rules were omitted" in warning
        for warning in validated.payload.eligibility_warnings
    )


def test_identity_name_match_tolerates_programme_label_variants() -> None:
    assert _identity_name_matches(
        "Chevening Scholarships",
        "Chevening Scholarship Programme",
    )
    assert not _identity_name_matches(
        "Chevening Scholarships",
        "Commonwealth Scholarship Programme",
    )


def test_identity_name_match_tolerates_official_page_title_wrapper() -> None:
    assert _identity_name_matches(
        "Chevening Scholarship Programme",
        "About us - Chevening Scholarship Programme - GOV.UK",
    )
    assert not _identity_name_matches(
        "Chevening Scholarship Programme",
        "About us - Commonwealth Scholarship Programme - GOV.UK",
    )


def test_evidence_normalizer_tolerates_observed_azure_apostrophe_corruption() -> None:
    from app.modules.catalogue_ingestion.validation import _normalize

    corrupted_masters = "Masters" + chr(0x0003) + "9 degrees"
    corrupted_government = "government" + chr(0x0003) + "9s"

    assert _normalize(corrupted_masters) == _normalize("Masters" + chr(0x2019) + " degrees")
    assert _normalize(corrupted_government) == _normalize("government" + chr(0x2019) + "s")


def test_canonical_identity_name_strips_official_page_title_wrapper() -> None:
    assert (
        _canonical_identity_name(
            "Chevening Scholarship Programme",
            "About us - Chevening Scholarship Programme - GOV.UK",
        )
        == "Chevening Scholarship Programme"
    )
    assert (
        _canonical_identity_name(
            "Chevening Scholarships",
            "About us - Chevening Scholarship Programme - GOV.UK",
        )
        == "Chevening Scholarship Programme"
    )
    assert (
        _canonical_identity_name(
            "Chevening Scholarship Programme",
            "Commonwealth Scholarship Programme",
        )
        == "Commonwealth Scholarship Programme"
    )


def test_gold_contract_rejects_derived_fields_and_missing_support() -> None:
    with pytest.raises(ValidationError, match="not AI-scored"):
        GoldItem(
            id="derived",
            official_url=OFFICIAL_URL,
            source_text=SOURCE_TEXT,
            expected={"identity": {"provider_canonical_id": "official-provider"}},
            support={"identity.provider_canonical_id": "Official Provider"},
            expected_unknown=["application.application_deadline"],
        )

    with pytest.raises(ValidationError, match="requires a support excerpt"):
        GoldItem(
            id="unsupported",
            official_url=OFFICIAL_URL,
            source_text=SOURCE_TEXT,
            expected={"identity": {"name": "Example Scholarship"}},
            expected_unknown=["application.application_deadline"],
        )

    with pytest.raises(ValidationError, match="not verbatim source text"):
        GoldItem(
            id="invented-support",
            official_url=OFFICIAL_URL,
            source_text=SOURCE_TEXT,
            expected={"identity": {"name": "Example Scholarship"}},
            support={"identity.name": "This sentence is not in the source."},
            expected_unknown=["application.application_deadline"],
        )


def test_gold_evaluation_counts_explicit_unknown_hallucinations() -> None:
    raw = extraction_output().model_dump(mode="json")
    raw["application"]["application_deadline"] = "2027-01-01T00:00:00+00:00"
    hallucinating = CatalogueExtractionOutput.model_validate(raw)
    gold = [
        GoldItem(
            id="hallucination",
            official_url=OFFICIAL_URL,
            source_text=SOURCE_TEXT,
            expected={"identity": {"name": "Example Scholarship"}},
            support={"identity.name": "Example Scholarship offers awards."},
            expected_unknown=["application.application_deadline"],
        )
    ]

    report = evaluate(FakeExtractionProvider(hallucinating), gold)

    assert report.expected_unknown_count == 1
    assert report.expected_unknown_accuracy == 0
    assert report.false_confident_values == 1
    assert report.item_results[0]["unknown_results"]["application.application_deadline"] is False


def test_gold_evaluation_normalizes_unordered_document_lists() -> None:
    raw = extraction_output().model_dump(mode="json")
    raw["application"]["required_documents"] = ["Academic Transcript", "Passport"]
    output = CatalogueExtractionOutput.model_validate(raw)
    source_text = SOURCE_TEXT + " Applicants submit a Passport and Academic Transcript."
    gold = [
        GoldItem(
            id="documents",
            official_url=OFFICIAL_URL,
            source_text=source_text,
            expected={"application": {"required_documents": ["passport", "academic transcript"]}},
            support={
                "application.required_documents": (
                    "Applicants submit a Passport and Academic Transcript."
                )
            },
            expected_unknown=["application.application_deadline"],
        )
    ]

    report = evaluate(FakeExtractionProvider(output), gold)

    assert report.field_accuracy["application.required_documents"] == 1


def test_gold_set_requires_explicit_unknown_coverage() -> None:
    gold = [
        GoldItem(
            id="no-unknowns",
            official_url=OFFICIAL_URL,
            source_text=SOURCE_TEXT,
            expected={"identity": {"name": "Example Scholarship"}},
            support={"identity.name": "Example Scholarship offers awards."},
        )
    ]

    with pytest.raises(ValueError, match="expected_unknown"):
        evaluate(FakeExtractionProvider(extraction_output()), gold)


def test_gold_evaluator_identity_name_allows_student_audience_suffix() -> None:
    from app.modules.catalogue_ingestion.evaluation import values_equal

    assert values_equal(
        "identity.name",
        "Erasmus Mundus Joint Masters (students)",
        "Erasmus Mundus Joint Masters",
    )


def test_gold_evaluator_identity_name_allows_uppercase_brand_suffix() -> None:
    from app.modules.catalogue_ingestion.evaluation import values_equal

    assert values_equal(
        "identity.name",
        "Development-Related Postgraduate Courses (EPOS) - DAAD",
        "Development-Related Postgraduate Courses (EPOS)",
    )


def test_gold_evaluator_identity_name_keeps_material_suffix_strict() -> None:
    from app.modules.catalogue_ingestion.evaluation import values_equal

    assert not values_equal(
        "identity.name",
        "Global Scholars Programme - International Track",
        "Global Scholars Programme",
    )


def test_gold_evaluator_non_identity_text_remains_strict() -> None:
    from app.modules.catalogue_ingestion.evaluation import values_equal

    assert not values_equal(
        "identity.provider_name",
        "Example Foundation (students)",
        "Example Foundation",
    )


def test_evaluation_scores_only_successful_extractions_and_reports_failure_cost() -> None:
    from app.modules.catalogue_ingestion.schemas import (
        ExtractionResult,
        ExtractionUsage,
    )

    first_url = "https://example.test/failed"
    second_url = "https://example.test/success"

    gold = [
        GoldItem(
            id="failed",
            official_url=first_url,
            source_text="Failed Scholarship official source text.",
            expected={"identity": {"name": "Failed Scholarship"}},
            support={
                "identity.name": "Failed Scholarship",
            },
            expected_unknown=["study.intake_year"],
        ),
        GoldItem(
            id="success",
            official_url=second_url,
            source_text="Expected Scholarship official source text.",
            expected={"identity": {"name": "Expected Scholarship"}},
            support={
                "identity.name": "Expected Scholarship",
            },
            expected_unknown=["study.intake_year"],
        ),
    ]

    class MixedProvider:
        name = "mixed"
        model = "test"

        def __init__(self) -> None:
            self.calls = 0

        def extract(self, *, source_url: str, source_text: str):
            del source_text
            self.calls += 1

            if self.calls == 1:
                raise ExtractionProviderError(
                    "schema failed after a billed response",
                    usage=ExtractionUsage(
                        input_tokens=100,
                        output_tokens=50,
                        estimated_cost=Decimal("0.001"),
                        latency_ms=5000,
                    ),
                )

            raw = extraction_output(source_url).model_dump(mode="json")
            raw["study"]["intake_year"] = 2026

            return ExtractionResult(
                output=CatalogueExtractionOutput.model_validate(raw),
                usage=ExtractionUsage(
                    input_tokens=200,
                    output_tokens=100,
                    estimated_cost=Decimal("0.002"),
                    latency_ms=1000,
                ),
            )

    report = evaluate(
        MixedProvider(),
        gold,
        max_calls=2,
        max_cost=Decimal("0.01"),
    )

    assert report.sample_count == 2
    assert report.successful_extractions == 1
    assert report.provider_failure_count == 1
    assert report.item_results[0]["error_detail"] == ("schema failed after a billed response")

    # Failed provider calls affect reliability, not extraction accuracy.
    assert report.field_totals == {"identity.name": 1}
    assert report.expected_unknown_count == 1
    assert report.benchmark_expected_unknown_count == 2

    # Both calls had measurable Azure-style usage.
    assert report.costed_call_count == 2
    assert report.uncosted_provider_failure_count == 0
    assert report.total_estimated_cost == Decimal("0.003")
    assert report.total_estimated_cost_is_lower_bound is False

    # Nearest-rank P95 for two observations is the slower call.
    assert report.p95_latency_ms == 5000

    success_result = report.item_results[1]
    assert success_result["field_mismatches"] == [
        {
            "path": "identity.name",
            "expected": "Expected Scholarship",
            "actual": "Example Scholarship",
        }
    ]
    assert success_result["unknown_mismatches"] == [
        {
            "path": "study.intake_year",
            "actual": 2026,
        }
    ]


def test_azure_schema_failure_preserves_usage_for_evaluation_costs() -> None:
    import time

    from app.modules.catalogue_ingestion.provider import ExtractionSchemaError

    provider = AzureOpenAIExtractionProvider(
        enabled_settings(),
        credential=object(),
    )

    response_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": "{}",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
            },
        }
    ).encode()

    with pytest.raises(ExtractionSchemaError) as exc_info:
        provider._parse_response(
            response_body,
            time.perf_counter(),
        )

    assert exc_info.value.usage is not None
    assert exc_info.value.usage.input_tokens == 100
    assert exc_info.value.usage.output_tokens == 50
    assert exc_info.value.usage.estimated_cost == Decimal("0.000200")
    assert "strict schema" in str(exc_info.value)
    assert "identity" in str(exc_info.value)


def test_azure_schema_failure_without_usage_remains_uncosted() -> None:
    import time

    from app.modules.catalogue_ingestion.provider import ExtractionSchemaError

    provider = AzureOpenAIExtractionProvider(
        enabled_settings(),
        credential=object(),
    )

    response_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": "{}",
                    }
                }
            ]
        }
    ).encode()

    with pytest.raises(
        ExtractionSchemaError,
        match="usage was missing or invalid",
    ) as exc_info:
        provider._parse_response(
            response_body,
            time.perf_counter(),
        )

    assert exc_info.value.usage is None


def test_catalogue_system_instruction_locks_conservative_semantics() -> None:
    from app.modules.catalogue_ingestion.provider import SYSTEM_INSTRUCTION

    assert "Absence of a benefit from the page must never be converted into not_covered" in (
        SYSTEM_INSTRUCTION
    )
    assert "Do not use partial merely because a grant is fixed" in SYSTEM_INSTRUCTION
    assert "website or publishing platform" in SYSTEM_INSTRUCTION
    assert "are not minimum academic requirements" in SYSTEM_INSTRUCTION
    assert "destination or host study country" in SYSTEM_INSTRUCTION
    assert "Never infer it from a university name" in SYSTEM_INSTRUCTION
    assert "Do not singularize or pluralize that heading" in SYSTEM_INSTRUCTION
    assert "overall scholarship value" in SYSTEM_INSTRUCTION
    assert "participation costs" in SYSTEM_INSTRUCTION
    assert "Do not append" in SYSTEM_INSTRUCTION


def test_claim_instruction_requires_exactly_one_typed_value() -> None:
    from app.modules.catalogue_ingestion.claim_provider import CLAIM_SYSTEM_INSTRUCTION

    assert "exactly one non-null field" in CLAIM_SYSTEM_INSTRUCTION
    assert "the other four value fields to null" in CLAIM_SYSTEM_INSTRUCTION
