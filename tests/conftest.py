import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["APP_ENV"] = "test"
os.environ["APP_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["APP_JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long"
# Keep production-equivalent feature gates active. The shared application
# explicitly enables the capabilities its integration tests exercise.
TEST_APPLICATION_FEATURE_FLAGS = {
    "APP_ASSISTANT_ENABLED": "true",
    "APP_DOCUMENT_LAB_ENABLED": "true",
    "APP_COMMUNITY_ENABLED": "true",
    "APP_CATALOGUE_MAINTENANCE_MODE": "false",
}
os.environ.update(TEST_APPLICATION_FEATURE_FLAGS)
# Request-limit behavior is covered with an injected small limit. The shared
# TestClient address should not make otherwise independent test users collide.
os.environ["APP_ASSISTANT_RATE_LIMIT_PER_MINUTE"] = "120"
os.environ["APP_COMMUNITY_WRITE_RATE_LIMIT_PER_MINUTE"] = "120"

# Imports intentionally follow test environment setup so the shared app caches it.
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

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


def override_get_db() -> Generator[Session, None, None]:
    with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
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
