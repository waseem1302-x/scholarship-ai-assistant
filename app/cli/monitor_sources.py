"""Fetch due official sources and record content-hash monitoring checks."""

import os

from app.db.session import SessionLocal
from app.modules.opportunities.source_monitor import (
    DEFAULT_CHECK_INTERVAL_DAYS,
    DEFAULT_MONITOR_LIMIT,
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
    dry_run = _env_bool("APP_SOURCE_MONITOR_DRY_RUN", default=False)
    limit = _env_int("APP_SOURCE_MONITOR_LIMIT", default=DEFAULT_MONITOR_LIMIT)
    check_interval_days = _env_int(
        "APP_SOURCE_MONITOR_INTERVAL_DAYS",
        default=DEFAULT_CHECK_INTERVAL_DAYS,
    )

    with SessionLocal() as session:
        result = SourceMonitor(session).run(
            dry_run=dry_run,
            limit=limit,
            check_interval_days=check_interval_days,
        )

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
    for failure in result.failures:
        print(f"Failed source {failure.source_id} {failure.url}: {failure.error}")


if __name__ == "__main__":
    main()
