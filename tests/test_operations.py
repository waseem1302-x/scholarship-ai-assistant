from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.modules.auth import models as auth_models
from app.modules.auth.models import AuditLog, verify_audit_integrity_chain
from app.modules.operations.models import OperationalJobHealth, OperationalJobRun
from app.modules.operations.service import OperationalJobService


def test_operational_job_health_records_safe_completion_and_failure(db_session) -> None:
    service = OperationalJobService(db_session)

    service.started("retention")
    service.completed("retention", processed=3)
    service.failed("retention", ValueError("private filename must not be stored"))

    record = db_session.get(OperationalJobHealth, "retention")
    assert record is not None
    assert record.last_started_at is not None
    assert record.last_completed_at is not None
    assert record.processed_count == 3
    assert record.failed_count == 1
    assert record.last_error_code == "ValueError"
    assert "filename" not in record.last_error_code
    runs = db_session.scalars(
        select(OperationalJobRun).where(OperationalJobRun.job_name == "retention")
    ).all()
    assert len(runs) == 2
    assert {run.failed_count for run in runs} == {0, 1}
    assert all(run.duration_ms is not None for run in runs)


def test_operational_health_reports_safe_job_summary(client, db_session) -> None:
    db_session.add(
        OperationalJobHealth(
            job_name="source_monitor",
            last_completed_at=datetime.now(UTC),
            processed_count=4,
            failed_count=0,
        )
    )
    db_session.commit()

    response = client.get(
        "/health/operations",
        headers={"X-Operations-Token": "test-operations-token"},
    )

    assert response.status_code == 200
    job = response.json()["jobs"]["source_monitor"]
    assert job["status"] == "fresh"
    assert job["processed_count"] == 4
    assert job["recent_runs"] == []
    assert response.json()["metrics_backend"] == "in_memory"


def test_metrics_snapshot_includes_latency_distribution(client) -> None:
    client.get("/health/live")

    response = client.get(
        "/health/operations",
        headers={"X-Operations-Token": "test-operations-token"},
    )

    assert response.status_code == 200
    health_metrics = response.json()["metrics"]["health"]
    assert health_metrics["requests"] >= 1
    assert "latency_buckets_ms" in health_metrics
    assert set(health_metrics["latency_buckets_ms"]) >= {"le_50", "gt_5000"}


def _two_audit_rows(db_session) -> tuple[AuditLog, AuditLog]:
    first = AuditLog(
        actor_user_id=None,
        action="test.first",
        entity_type="test",
        entity_id="one",
        metadata_json={"safe": True},
    )
    db_session.add(first)
    db_session.commit()
    second = AuditLog(
        actor_user_id=None,
        action="test.second",
        entity_type="test",
        entity_id="two",
        metadata_json={"safe": True},
    )
    db_session.add(second)
    db_session.commit()
    return first, second


def test_audit_logs_have_tamper_evident_hash_chain(db_session) -> None:
    first, second = _two_audit_rows(db_session)

    assert len(first.integrity_hash) == 64
    assert len(second.integrity_hash) == 64
    assert second.previous_integrity_hash == first.integrity_hash
    assert first.integrity_hash != second.integrity_hash
    assert verify_audit_integrity_chain(db_session) == (True, None)


def test_audit_logs_reject_orm_mutation(db_session) -> None:
    first, _ = _two_audit_rows(db_session)
    first.action = "tampered"

    with pytest.raises(RuntimeError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_audit_chain_verifier_detects_storage_tampering(db_session) -> None:
    first, _ = _two_audit_rows(db_session)

    # SQLite integration tests do not install the PostgreSQL append-only trigger,
    # so a raw mutation lets us prove the verifier detects storage-level damage.
    db_session.execute(
        text("UPDATE audit_logs SET action = :action WHERE id = :id"),
        {"action": "tampered-outside-orm", "id": first.id.hex},
    )
    db_session.commit()
    valid, bad_id = verify_audit_integrity_chain(db_session)

    assert valid is False
    assert bad_id == first.id


def test_multiple_audit_rows_in_one_flush_form_one_chain(db_session) -> None:
    first = AuditLog(
        actor_user_id=None,
        action="test.same_flush.first",
        entity_type="test",
        entity_id="same-flush-one",
        metadata_json={"safe": True},
    )
    second = AuditLog(
        actor_user_id=None,
        action="test.same_flush.second",
        entity_type="test",
        entity_id="same-flush-two",
        metadata_json={"safe": True},
    )
    db_session.add_all([first, second])
    db_session.commit()

    assert second.previous_integrity_hash == first.integrity_hash
    assert verify_audit_integrity_chain(db_session) == (True, None)


def test_audit_chain_orders_rows_when_clock_tick_repeats(db_session, monkeypatch) -> None:
    fixed_time = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    monkeypatch.setattr(auth_models, "utc_now", lambda: fixed_time)

    first = AuditLog(action="test.clock.first", entity_type="test", entity_id="clock-one")
    second = AuditLog(action="test.clock.second", entity_type="test", entity_id="clock-two")
    db_session.add_all([first, second])
    db_session.commit()

    third = AuditLog(action="test.clock.third", entity_type="test", entity_id="clock-three")
    db_session.add(third)
    db_session.commit()

    assert first.created_at < second.created_at < third.created_at
    assert verify_audit_integrity_chain(db_session) == (True, None)
