"""Claim and process durable catalogue ingestion runs outside HTTP requests."""

import argparse
import os
import socket

from app.core.config import get_settings
from app.db.session import SystemSessionLocal
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
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

    worker_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or f"{socket.gethostname()}-{os.getpid()}"
    with SystemSessionLocal() as session:
        health = OperationalJobService(session)
        health.started("catalogue_ingestion")
        service = CatalogueIngestionService(session, get_settings())
        try:
            results = service.process_next_runs(
                worker_id=worker_id, limit=args.limit, batch_size=args.batch_size
            )
            health.completed("catalogue_ingestion", len(results))
        except Exception as exc:
            health.failed("catalogue_ingestion", exc)
            raise

    for result in results:
        print(
            "Catalogue ingestion run "
            f"id={result.id} status={result.status.value} stage={result.stage.value} "
            f"attempts={result.attempt_count} checkpoint={result.checkpoint_cursor}"
        )


if __name__ == "__main__":
    main()
