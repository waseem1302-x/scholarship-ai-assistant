"""Fetch due official sources and record content-hash monitoring checks."""

import os

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.catalogue_ingestion.metrics import get_catalogue_metrics
from app.modules.operations.service import OperationalJobService
from app.modules.opportunities.source_monitor import (
    DEFAULT_CHECK_INTERVAL_DAYS,
    SourceMonitor,
)


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes"}


def _env_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def main() -> None:
    settings = get_settings()
    dry_run = _env_bool("APP_SOURCE_MONITOR_DRY_RUN", default=False)
    limit = _env_int("APP_SOURCE_MONITOR_LIMIT", default=settings.source_monitor_batch_limit)
    check_interval_days = _env_int(
        "APP_SOURCE_MONITOR_INTERVAL_DAYS",
        default=DEFAULT_CHECK_INTERVAL_DAYS,
    )

    with SessionLocal() as session:
        health = OperationalJobService(session)
        health.started("source_monitor")
        try:
            result = SourceMonitor(
                session,
                claim_seconds=settings.source_monitor_claim_seconds,
                per_host_interval_seconds=float(settings.source_monitor_per_host_interval_seconds),
                metrics=get_catalogue_metrics(settings),
            ).run(
                dry_run=dry_run,
                limit=limit,
                check_interval_days=check_interval_days,
            )
            health.completed("source_monitor", result.checked)
        except Exception as exc:
            health.failed("source_monitor", exc)
            raise

    print(
        "Source monitor run: "
        f"{result.candidates} candidates, "
        f"{result.checked} checked, "
        f"{result.changed} changed, "
        f"{result.unchanged} unchanged, "
        f"{result.initialized_hashes} initialized hashes, "
        f"{result.failed} failed, "
        f"dry_run={result.dry_run}"
    )
    # Keep CLI telemetry free of source URLs and upstream response details;
    # operators can inspect the protected source-monitor records when needed.
    for failure in result.failures:
        print(
            f"Source monitor failure source_id={failure.source_id} error_code={failure.error_code}"
        )


if __name__ == "__main__":
    main()
