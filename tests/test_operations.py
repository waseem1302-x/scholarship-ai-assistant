from datetime import UTC, datetime

from app.modules.operations.models import OperationalJobHealth
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

    response = client.get("/health/operations")

    assert response.status_code == 200
    job = response.json()["jobs"]["source_monitor"]
    assert job["status"] == "fresh"
    assert job["processed_count"] == 4
