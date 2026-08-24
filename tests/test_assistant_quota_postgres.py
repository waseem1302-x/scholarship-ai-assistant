import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.assistant.models import AssistantQuotaCounter, AssistantQuotaReservation
from app.modules.assistant.service import AssistantService
from app.modules.auth.models import User, UserRole

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for assistant quota concurrency tests")
    engine = create_engine(database_url, pool_size=4, max_overflow=0, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    yield engine
    engine.dispose()


def test_quota_reservation_admits_exactly_one_competing_limit_one_request(postgres_engine) -> None:
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    user = User(
        email=f"assistant-quota-{uuid.uuid4().hex}@example.com",
        password_hash="not-used-by-quota-test",
        role=UserRole.STUDENT,
        is_active=True,
    )
    with sessions() as setup:
        setup.add(user)
        setup.commit()
        user_id = user.id

    settings = Settings(
        env="test",
        database_url=str(postgres_engine.url),
        jwt_secret="postgres-quota-test-secret-at-least-32-characters",
        assistant_daily_user_limit=1,
        assistant_monthly_user_limit=1,
    )
    barrier = threading.Barrier(2)

    def reserve_once() -> str:
        with sessions() as session:
            service = AssistantService(session, settings)
            barrier.wait(timeout=10)
            try:
                service._reserve_quota(user_id)
                return "admitted"
            except AppError as error:
                assert error.code == "assistant_quota_exceeded"
                return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: reserve_once(), range(2)))
        assert sorted(outcomes) == ["admitted", "rejected"]
        with Session(postgres_engine) as verify:
            assert (
                verify.scalar(
                    select(AssistantQuotaCounter.used_slots).where(
                        AssistantQuotaCounter.user_id == user_id
                    )
                )
                == 1
            )
            assert (
                verify.scalar(
                    select(AssistantQuotaReservation).where(
                        AssistantQuotaReservation.user_id == user_id
                    )
                )
                is not None
            )
    finally:
        with sessions() as cleanup:
            cleanup.execute(
                delete(AssistantQuotaReservation).where(
                    AssistantQuotaReservation.user_id == user_id
                )
            )
            cleanup.execute(
                delete(AssistantQuotaCounter).where(AssistantQuotaCounter.user_id == user_id)
            )
            persisted = cleanup.get(User, user_id)
            if persisted is not None:
                cleanup.delete(persisted)
            cleanup.commit()
