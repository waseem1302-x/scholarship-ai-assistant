import hashlib
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, or_, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["APP_ENV"] = "test"
os.environ["APP_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["APP_JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long"
# Keep production-equivalent gates and limiters active. The shared application
# explicitly enables the capabilities its integration tests exercise and uses
# high limits so independent tests sharing TestClient's IP do not interfere.
TEST_APPLICATION_FEATURE_FLAGS = {
    "APP_ASSISTANT_ENABLED": "true",
    "APP_DOCUMENT_LAB_ENABLED": "true",
    "APP_COMMUNITY_ENABLED": "true",
    "APP_CATALOGUE_MAINTENANCE_MODE": "false",
    "APP_AUTH_LOGIN_RATE_LIMIT_PER_MINUTE": "120",
    "APP_AUTH_LOGIN_GLOBAL_RATE_LIMIT_PER_MINUTE": "10000",
    "APP_AUTH_REGISTRATION_RATE_LIMIT_PER_MINUTE": "120",
}
os.environ.update(TEST_APPLICATION_FEATURE_FLAGS)
# Request-limit behavior is covered with an injected small limit. The shared
# TestClient address should not make otherwise independent test users collide.
os.environ["APP_ASSISTANT_RATE_LIMIT_PER_MINUTE"] = "120"
os.environ["APP_COMMUNITY_WRITE_RATE_LIMIT_PER_MINUTE"] = "120"
os.environ["APP_OPERATIONS_HEALTH_TOKEN"] = "test-operations-token"

# Imports intentionally follow test environment setup so the shared app caches it.
from app.db.base import Base  # noqa: E402
from app.db.session import get_db, get_system_db  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.opportunities.evidence_models import (  # noqa: E402
    EvidenceSupportType,
    EvidenceValidatorStatus,
    FieldEvidence,
    OfficialityStatus,
    SourceOwnerType,
    SourceSnapshot,
)
from app.modules.opportunities.models import (  # noqa: E402
    DuplicateSuggestion,
    DuplicateSuggestionStatus,
    FundingClassification,
    FundingCoverageStatus,
    IndependenceStatus,
    Opportunity,
    VerificationStatus,
)

# The shared application has cached its explicit test settings. Remove these
# temporary environment values so standalone Settings tests remain isolated.
for feature_flag_name in TEST_APPLICATION_FEATURE_FLAGS:
    os.environ.pop(feature_flag_name, None)

test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


PUBLICATION_EVIDENCE_PATHS = (
    "name",
    "provider_name",
    "country",
    "degree_level",
    "route_scope",
    "intake_year",
    "application_deadline",
    "application_url",
    "application_method",
    "tuition_coverage_status",
    "tuition_coverage",
    "stipend_coverage_status",
    "monthly_stipend_amount",
    "funding_classification",
    "nationality_eligibility",
    "minimum_academic_requirement",
    "english_language_requirement",
    "required_documents",
)


def support_opportunity_for_publication(
    opportunity_id: str | uuid.UUID, *, fill_missing_values: bool = True
) -> None:
    """Attach deterministic, exact official evidence for legacy publication tests."""

    with TestSessionLocal() as session:
        opportunity = session.get(Opportunity, uuid.UUID(str(opportunity_id)))
        assert opportunity is not None
        source = opportunity.sources[0]
        source.officiality_status = OfficialityStatus.OFFICIAL
        source.source_owner_type = SourceOwnerType.PROVIDER
        source.source_owner_id = opportunity.provider_id
        source.verification_status = VerificationStatus.OFFICIALLY_VERIFIED
        source.last_verified_at = datetime.now(UTC)
        opportunity.independence_status = IndependenceStatus.CONFIRMED_INDEPENDENT
        if fill_missing_values:
            opportunity.application_deadline = opportunity.application_deadline or datetime(
                2027, 5, 30, 23, 59, tzinfo=UTC
            )
            opportunity.catalogue_application_deadline = (
                opportunity.catalogue_application_deadline or opportunity.application_deadline
            )
            opportunity.application_url = (
                opportunity.application_url or "https://official.example/apply"
            )
            opportunity.application_method = (
                opportunity.application_method or "Apply through the official portal."
            )
            opportunity.nationality_eligibility = (
                opportunity.nationality_eligibility or "International applicants"
            )
            opportunity.minimum_academic_requirement = (
                opportunity.minimum_academic_requirement or "A relevant degree is required."
            )
            opportunity.english_language_requirement = (
                opportunity.english_language_requirement or "English requirements apply."
            )
            opportunity.required_documents = opportunity.required_documents or ["Transcript"]
            opportunity.funding_policy = (
                opportunity.funding_policy
                or "Official policy confirms tuition and stipend coverage."
            )
            opportunity.tuition_coverage = (
                opportunity.tuition_coverage or "Official tuition coverage is stated."
            )
            if opportunity.tuition_coverage_status is FundingCoverageStatus.UNKNOWN:
                opportunity.tuition_coverage_status = FundingCoverageStatus.CONFIRMED
            if opportunity.stipend_coverage_status is FundingCoverageStatus.UNKNOWN:
                opportunity.stipend_coverage_status = FundingCoverageStatus.CONFIRMED
            opportunity.funding_classification = FundingClassification.FULLY_FUNDED
        for suggestion in session.scalars(
            select(DuplicateSuggestion).where(
                or_(
                    DuplicateSuggestion.opportunity_id == opportunity.id,
                    DuplicateSuggestion.matched_opportunity_id == opportunity.id,
                )
            )
        ):
            suggestion.status = DuplicateSuggestionStatus.DISMISSED

        excerpts = {path: f"Synthetic evidence for {path}." for path in PUBLICATION_EVIDENCE_PATHS}
        normalized_text = "\n".join(excerpts.values())
        content_hash = source.content_hash or hashlib.sha256(
            normalized_text.encode("utf-8")
        ).hexdigest()
        source.content_hash = content_hash
        snapshot = SourceSnapshot(
            source_id=source.id,
            http_status=200,
            content_hash=content_hash,
            normalized_text=normalized_text,
            extraction_method="synthetic-test-fixture",
            byte_count=len(normalized_text.encode("utf-8")),
            character_count=len(normalized_text),
        )
        session.add(snapshot)
        session.flush()
        for path, excerpt in excerpts.items():
            start = normalized_text.index(excerpt)
            session.add(
                FieldEvidence(
                    entity_type="opportunity",
                    entity_id=opportunity.id,
                    field_path=path,
                    source_snapshot_id=snapshot.id,
                    excerpt=excerpt,
                    excerpt_start=start,
                    excerpt_end=start + len(excerpt),
                    support_type=EvidenceSupportType.EXPLICIT,
                    validator_status=EvidenceValidatorStatus.PASSED,
                )
            )
        session.commit()


def override_get_db() -> Generator[Session, None, None]:
    with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_system_db] = override_get_db


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    # Rebuild middleware for each test so its in-memory request limiter cannot
    # retain attempts from an unrelated TestClient. Rate limiting stays active
    # within each test and production continues to use the shared Redis store.
    app.middleware_stack = None
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    with TestSessionLocal() as session:
        yield session
