"""Operational health endpoint registration."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.modules.applications.models import ReminderWorkerHealth
from app.modules.catalogue_ingestion.models import CatalogueIngestionRun, IngestionRunStatus
from app.modules.document_lab.service import document_intake_readiness
from app.modules.operations.models import OperationalJobHealth


def aggregate_readiness(session: Session, settings: Settings) -> dict[str, object]:
    """Report enabled capability dependencies without exposing configuration secrets.

    Disabled high-risk capabilities are deliberately excluded from the ready
    gate.  Enabled capabilities without a verifiable worker/provider boundary
    are blocked instead of inheriting a misleading database-only ready result.
    """

    from app.core.rate_limit import create_rate_limit_store

    session.execute(text("SELECT 1"))
    dependencies: dict[str, dict[str, object]] = {"database": {"status": "ready"}}

    if settings.rate_limit_backend == "redis":
        redis_ready = create_rate_limit_store(settings).health()
        dependencies["redis"] = {
            "status": "ready" if redis_ready else "blocked",
            "reason": None if redis_ready else "rate_limit_store_unavailable",
        }
    else:
        dependencies["redis"] = {"status": "disabled"}

    dependencies["catalogue_queue"] = _catalogue_queue_readiness(session, settings)
    dependencies["catalogue_document_worker"] = _catalogue_document_worker_readiness(settings)
    dependencies["catalogue_browser_worker"] = _catalogue_browser_worker_readiness(settings)
    dependencies["catalogue_extraction_provider"] = _catalogue_extraction_provider_readiness(
        settings
    )
    dependencies["document_lab"] = _document_lab_readiness(session, settings)
    ready = all(item["status"] in {"ready", "disabled"} for item in dependencies.values())
    return {"status": "ready" if ready else "blocked", "dependencies": dependencies}


def _catalogue_queue_readiness(session: Session, settings: Settings) -> dict[str, object]:
    if not settings.catalogue_scheduled_ingestion_enabled:
        return {"status": "disabled"}
    health = session.get(OperationalJobHealth, "catalogue_ingestion")
    is_fresh = _job_is_fresh(health, settings)
    dead_letters = session.scalar(
        select(func.count())
        .select_from(CatalogueIngestionRun)
        .where(CatalogueIngestionRun.status == IngestionRunStatus.DEAD_LETTER)
    )
    if not is_fresh:
        return {
            "status": "blocked",
            "reason": "catalogue_worker_stale",
            "dead_letter_count": dead_letters,
        }
    if dead_letters:
        return {
            "status": "blocked",
            "reason": "catalogue_dead_letters_present",
            "dead_letter_count": dead_letters,
        }
    return {"status": "ready", "dead_letter_count": 0}


def _catalogue_document_worker_readiness(settings: Settings) -> dict[str, object]:
    if not settings.catalogue_document_intelligence_enabled:
        return {"status": "disabled"}
    return {"status": "blocked", "reason": "dedicated_worker_transport_unavailable"}


def _catalogue_browser_worker_readiness(settings: Settings) -> dict[str, object]:
    if not settings.catalogue_browser_fetching_enabled:
        return {"status": "disabled"}
    return {"status": "blocked", "reason": "isolated_browser_worker_unavailable"}


def _catalogue_extraction_provider_readiness(settings: Settings) -> dict[str, object]:
    if not settings.catalogue_ai_ingestion_enabled:
        return {"status": "disabled"}
    return {"status": "blocked", "reason": "extraction_provider_runtime_probe_unavailable"}


def _document_lab_readiness(session: Session, settings: Settings) -> dict[str, object]:
    if not settings.document_lab_enabled:
        return {"status": "disabled"}
    scanner_ready, worker_ready, accepting_uploads = document_intake_readiness(session, settings)
    if settings.env != "production" and accepting_uploads:
        return {
            "status": "ready",
            "scanner_ready": scanner_ready,
            "worker_ready": worker_ready,
        }
    if accepting_uploads:
        return {
            "status": "blocked",
            "reason": "document_storage_runtime_probe_unavailable",
            "scanner_ready": scanner_ready,
            "worker_ready": worker_ready,
        }
    return {
        "status": "blocked",
        "reason": "document_intake_dependencies_unready",
        "scanner_ready": scanner_ready,
        "worker_ready": worker_ready,
    }


def _job_is_fresh(health: OperationalJobHealth | None, settings: Settings) -> bool:
    if not health or not health.last_completed_at or health.last_error_code:
        return False
    completed = health.last_completed_at
    completed_utc = completed.replace(tzinfo=UTC) if completed.tzinfo is None else completed
    return completed_utc >= datetime.now(UTC) - timedelta(
        minutes=settings.operational_job_stale_minutes
    )


def register_health_routes(application: FastAPI, settings: Settings) -> None:
    """Register health probes without coupling them to the application factory."""

    @application.get("/health/live", tags=["operations"])
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["operations"])
    def readiness(session: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
        report = aggregate_readiness(session, settings)
        if report["status"] != "ready":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, report)
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
        _require_operations_access(request, settings)
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
                "recent_runs": [
                    {
                        "run_id": str(run.id),
                        "started_at": run.started_at.isoformat(),
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        "duration_ms": run.duration_ms,
                        "processed": run.processed_count,
                        "failed": run.failed_count,
                        "error_code": run.error_code,
                        "release_version": run.release_version,
                    }
                    for run in job.recent_runs[:10]
                ],
            }
        return {
            "release_version": settings.release_version,
            "readiness": aggregate_readiness(session, settings),
            "rate_limit_store_healthy": rate_limit_store_healthy,
            "account_email_healthy": account_email_healthy,
            "metrics_backend": settings.metrics_backend,
            "metrics": request.app.state.metrics.snapshot(),
            "jobs": jobs,
        }


def _require_operations_access(request: Request, settings: Settings) -> None:
    expected = (
        settings.operations_health_token.get_secret_value()
        if settings.operations_health_token
        else None
    )
    if not expected:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    authorization = request.headers.get("authorization", "")
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    supplied = request.headers.get("x-operations-token") or bearer
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
