"""Create or resume a bounded catalogue ingestion run outside synchronous HTTP requests."""

import argparse
import os
import socket
import uuid

from app.core.config import get_settings
from app.db.session import SystemSessionLocal
from app.modules.catalogue_ingestion.models import IngestionMode
from app.modules.catalogue_ingestion.service import CatalogueIngestionService
from app.modules.operations.service import OperationalJobService


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", help="Local seed path or private Azure Blob HTTPS URI")
    result.add_argument("--resume", type=uuid.UUID, help="Existing ingestion run UUID")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--max-candidates", type=int)
    result.add_argument("--batch-size", type=int, default=25)
    result.add_argument(
        "--mode",
        choices=[mode.value for mode in IngestionMode],
        default=IngestionMode.CANDIDATE_ONLY.value,
    )
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if (args.source is None) == (args.resume is None):
        parser().error("provide exactly one of --source or --resume")
    if args.max_candidates is not None and args.max_candidates < 1:
        parser().error("--max-candidates must be positive")
    if not 1 <= args.batch_size <= 100:
        parser().error("--batch-size must be between 1 and 100")

    settings = get_settings()
    worker_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or f"{socket.gethostname()}-{os.getpid()}"
    with SystemSessionLocal() as session:
        health = OperationalJobService(session)
        health.started("catalogue_ingestion")
        service = CatalogueIngestionService(session, settings)
        try:
            if args.resume:
                run_id = args.resume
            else:
                run = service.create_run_from_source(
                    args.source,
                    mode=IngestionMode(args.mode),
                    dry_run=args.dry_run,
                    max_candidates=args.max_candidates,
                )
                run_id = run.id
            result = service.process_run(run_id, worker_id=worker_id, batch_size=args.batch_size)
            processed = result.checkpoint_cursor
            health.completed("catalogue_ingestion", processed)
        except Exception as exc:
            health.failed("catalogue_ingestion", exc)
            raise

    print(
        "Catalogue ingestion run "
        f"id={result.id} status={result.status.value} checkpoint={result.checkpoint_cursor} "
        f"model_calls={result.model_calls} estimated_cost={result.estimated_cost}"
    )


if __name__ == "__main__":
    main()
