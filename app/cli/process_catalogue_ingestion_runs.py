"""Claim and process durable catalogue ingestion runs outside HTTP requests."""

import argparse
import json
import os
import socket

from app.core.config import get_settings
from app.db.session import SystemSessionLocal
from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
from app.modules.operations.service import OperationalJobService


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--limit", type=int, default=10, help="Maximum queued runs to claim")
    result.add_argument("--batch-size", type=int, default=25, help="Candidates per claimed run")
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if not 1 <= args.limit <= 100:
        parser().error("--limit must be between 1 and 100")
    if not 1 <= args.batch_size <= 100:
        parser().error("--batch-size must be between 1 and 100")

    settings = get_settings()
    worker_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or f"{socket.gethostname()}-{os.getpid()}"

    # Respect operator kill switch first
    stopped = kill_switch_active(settings.catalogue_worker_kill_switch_path)

    preflight_report = None
    # Skip preflight probes when operator kill switch is active.
    # Avoid unnecessary network/readiness probes.
    if not stopped:
        # Run preflight checks and fail-closed if readiness is blocked
        try:
            preflight_report = run_catalogue_preflight(settings)
        except Exception as exc:
            # Do not expose exception messages which may contain secrets; show class name only
            err = type(exc).__name__
            print(f"Catalogue preflight check failed; aborting ingestion. Error: {err}")
            stopped = True
        else:
            if preflight_report.get("status") != "ready":
                print("Catalogue preflight blocked ingestion. Report summary (status/reason only):")
                try:
                    sanitized = {
                        k: {
                            "status": v.get("status"),
                            "reason": v.get("reason"),
                            "error_code": v.get("error_code"),
                        }
                        for k, v in preflight_report.get("checks", {}).items()
                    }
                    print(json.dumps(sanitized, indent=2, sort_keys=True))
                except Exception:
                    pass
                stopped = True
    with SystemSessionLocal() as session:
        health = OperationalJobService(session)
        health.started("catalogue_ingestion")
        service = CatalogueIngestionService(
            session,
            settings,
            kill_switch=lambda: kill_switch_active(
                settings.catalogue_worker_kill_switch_path
            ),
        )
        try:
            results = (
                []
                if stopped
                else service.process_next_runs(
                    worker_id=worker_id, limit=args.limit, batch_size=args.batch_size
                )
            )
            health.completed("catalogue_ingestion", len(results))
        except Exception as exc:
            health.failed("catalogue_ingestion", exc)
            raise

    if stopped:
        print("Catalogue ingestion paused: preflight blocked or operator kill switch is active")
    for result in results:
        print(
            "Catalogue ingestion run "
            f"id={result.id} status={result.status.value} stage={result.stage.value} "
            f"attempts={result.attempt_count} checkpoint={result.checkpoint_cursor}"
        )


if __name__ == "__main__":
    main()
