import hashlib
import json
import urllib.error
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.modules.auth.models import User, UserRole
from app.modules.catalogue_ingestion.evaluation import GoldItem, evaluate
from app.modules.catalogue_ingestion.models import (
    CandidateStatus,
    CatalogueCandidate,
    CatalogueExtractionAttempt,
    IngestionMode,
    IngestionRunStatus,
)
from app.modules.catalogue_ingestion.provider import (
    AzureOpenAIExtractionProvider,
    ExtractionProviderError,
    FakeExtractionProvider,
    azure_structured_output_schema,
    estimate_cost,
)
from app.modules.catalogue_ingestion.schemas import CatalogueExtractionOutput
from app.modules.catalogue_ingestion.seed_parser import (
    LoadedSeed,
    LocalSeedDocumentParser,
    SeedParseError,
    SeedSourceLoader,
)
from app.modules.catalogue_ingestion.service import (
    CatalogueIngestionService,
    _canonical_identity_name,
    _identity_name_matches,
)
from app.modules.catalogue_ingestion.sources import OfficialSourceClassifier
from app.modules.catalogue_ingestion.validation import validate_and_build_proposal
from app.modules.opportunities.models import Opportunity, OpportunityStatus, VerificationStatus
from app.modules.opportunities.schemas import ReviewAction, ReviewActionRequest
from app.modules.opportunities.service import OpportunityService
from app.modules.opportunities.source_monitor import FetchedSource

OFFICIAL_URL = "https://scholarships.gov.uk/example"
SOURCE_TEXT = (
    "Example Scholarship offers awards. Official Provider administers the award. "
    "Applicants study in the United Kingdom. Masters programmes are eligible."
)


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
    ):
        assert client.get(path).status_code == 401


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
    assert not classifier.classify("https://scholarshipportal.com/example").is_official
    assert classifier.classify(
        "https://funding.example.edu/program",
        university_website_url="https://example.edu",
    ).is_official
    assert not classifier.classify("https://unknown.example/program").is_official


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

    assert result.status is IngestionRunStatus.COMPLETED
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
    assert result.aggregate_summary == {"needs_review": 500}


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


def test_azure_provider_uses_entra_strict_output_and_bounded_retry() -> None:
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
            if self.calls == 1:
                raise urllib.error.URLError("temporary")
            return Response()

    opener = Opener()
    waits: list[float] = []
    provider = AzureOpenAIExtractionProvider(
        enabled_settings(), credential=Credential(), opener=opener, sleeper=waits.append
    )
    result = provider.extract(source_url=OFFICIAL_URL, source_text=SOURCE_TEXT)

    assert opener.calls == 2
    assert waits == [1]
    assert opener.request.get_header("Authorization") == "Bearer entra-token"
    sent = json.loads(opener.request.data)
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert result.output.identity.name == "Example Scholarship"
    assert result.usage.estimated_cost == Decimal("0.000200")


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
