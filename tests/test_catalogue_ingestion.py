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
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
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
        )
    ]
    report = evaluate(FakeExtractionProvider(extraction_output()), gold, max_calls=1)
    assert report.schema_validation_rate == 1
    assert report.official_source_correctness == 1
    assert report.field_accuracy["identity.name"] == 1

    class FailingProvider:
        name = "failing"
        model = "test"

        def extract(self, *, source_url: str, source_text: str):
            del source_url, source_text
            raise ExtractionProviderError("invalid response")

    failed = evaluate(FailingProvider(), gold)
    assert failed.schema_validation_rate == 0
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
        "Non-mandatory AI-extracted eligibility rules were omitted"
        in warning
        for warning in validated.payload.eligibility_warnings
    )
