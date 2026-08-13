"""Operational health endpoint registration."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.modules.applications.models import ReminderWorkerHealth
from app.modules.operations.models import OperationalJobHealth


def register_health_routes(application: FastAPI, settings: Settings) -> None:
    """Register health probes without coupling them to the application factory."""

    @application.get("/health/live", tags=["operations"])
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["operations"])
    def readiness(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}

    @application.get("/health/reminders", tags=["operations"])
    def reminder_worker_readiness(
        session: Annotated[Session, Depends(get_db)],
    ) -> dict[str, str]:
        health = session.get(ReminderWorkerHealth, "default")
        completed = health.last_completed_at if health else None
        completed_utc = (
            completed.replace(tzinfo=UTC) if completed and completed.tzinfo is None else completed
        )
        is_current = bool(
            completed_utc and completed_utc >= datetime.now(UTC) - timedelta(minutes=5)
        )
        if settings.reminder_worker_required and not is_current:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Reminder worker is not healthy",
            )
        return {"status": "ready" if is_current else "not_running"}

    @application.get("/health/operations", tags=["operations"])
    def operational_health(
        request: Request,
        session: Annotated[Session, Depends(get_db)],
    ) -> dict[str, object]:
        from app.core.email import get_account_email_sender
        from app.core.rate_limit import create_rate_limit_store

        rate_limit_store_healthy = create_rate_limit_store(settings).health()
        account_email_healthy = get_account_email_sender(settings).health()
        now = datetime.now(UTC)
        jobs = {}
        for job in session.scalars(select(OperationalJobHealth)).all():
            completed = job.last_completed_at
            completed_utc = (
                completed.replace(tzinfo=UTC)
                if completed and completed.tzinfo is None
                else completed
            )
            jobs[job.job_name] = {
                "status": (
                    "fresh"
                    if completed_utc
                    and completed_utc
                    >= now - timedelta(minutes=settings.operational_job_stale_minutes)
                    else "stale"
                ),
                "last_completed_at": completed_utc.isoformat() if completed_utc else None,
                "processed_count": job.processed_count,
                "failed_count": job.failed_count,
                "last_error_code": job.last_error_code,
            }
        return {
            "release_version": settings.release_version,
            "rate_limit_store_healthy": rate_limit_store_healthy,
            "account_email_healthy": account_email_healthy,
            "metrics": request.app.state.metrics.snapshot(),
            "jobs": jobs,
        }
