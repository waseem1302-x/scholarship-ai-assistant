import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.auth.models import AuditLog, verify_audit_integrity_chain

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL security tests")

    engine = create_engine(database_url, pool_size=8, max_overflow=0, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    yield engine
    engine.dispose()


def _audit_row(entity_id: str) -> AuditLog:
    return AuditLog(
        actor_user_id=None,
        action="test.postgres",
        entity_type="postgres-audit-security",
        entity_id=entity_id,
        metadata_json={"safe": True},
    )


def test_postgres_trigger_rejects_update_and_delete(postgres_engine) -> None:
    with Session(postgres_engine) as session:
        row = _audit_row(f"trigger-{uuid.uuid4()}")
        session.add(row)
        session.commit()
        audit_id = row.id

    for statement in (
        "UPDATE audit_logs SET action = 'tampered' WHERE id = :audit_id",
        "DELETE FROM audit_logs WHERE id = :audit_id",
    ):
        connection = postgres_engine.connect()
        transaction = connection.begin()
        try:
            with pytest.raises(DBAPIError) as exc_info:
                connection.execute(text(statement), {"audit_id": audit_id})
            assert "append-only" in str(exc_info.value.orig)
        finally:
            transaction.rollback()
            connection.close()


def test_postgres_verifier_detects_storage_tampering(postgres_engine) -> None:
    with Session(postgres_engine) as session:
        row = _audit_row(f"tamper-{uuid.uuid4()}")
        session.add(row)
        session.commit()
        audit_id = row.id

    connection = postgres_engine.connect()
    transaction = connection.begin()
    try:
        connection.exec_driver_sql(
            "ALTER TABLE audit_logs DISABLE TRIGGER trg_audit_logs_append_only"
        )
        connection.execute(
            text("UPDATE audit_logs SET action = 'tampered' WHERE id = :audit_id"),
            {"audit_id": audit_id},
        )
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
            assert verify_audit_integrity_chain(session) == (False, audit_id)
    finally:
        transaction.rollback()
        connection.close()

    with Session(postgres_engine) as session:
        assert verify_audit_integrity_chain(session) == (True, None)


def test_postgres_concurrent_appends_form_one_chain(postgres_engine) -> None:
    worker_count = 8
    barrier = threading.Barrier(worker_count)
    session_factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)

    def append(index: int) -> uuid.UUID:
        with session_factory() as session:
            row = _audit_row(f"concurrent-{uuid.uuid4()}-{index}")
            session.add(row)
            barrier.wait(timeout=10)
            session.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        audit_ids = list(executor.map(append, range(worker_count)))

    with Session(postgres_engine) as session:
        rows = session.scalars(select(AuditLog).where(AuditLog.id.in_(audit_ids))).all()
        assert len(rows) == worker_count
        assert len({row.integrity_hash for row in rows}) == worker_count
        assert verify_audit_integrity_chain(session) == (True, None)
