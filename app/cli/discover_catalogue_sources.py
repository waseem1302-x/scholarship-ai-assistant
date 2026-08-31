"""Create or resume one bounded, review-gated catalogue discovery run."""

from __future__ import annotations

import argparse
import os
import socket
import uuid

from app.core.config import get_settings
from app.db.session import SystemSessionLocal
from app.modules.catalogue_ingestion.discovery import DiscoveryObjectiveKind
from app.modules.catalogue_ingestion.discovery_control import CatalogueDiscoveryControlService
from app.modules.catalogue_ingestion.discovery_schemas import CandidateDiscoveryRunRequest
from app.modules.operations.service import OperationalJobService


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    target = result.add_mutually_exclusive_group(required=True)
    target.add_argument("--candidate", type=uuid.UUID, help="Candidate UUID to discover for")
    target.add_argument("--resume", type=uuid.UUID, help="Existing discovery run UUID")
    result.add_argument(
        "--objective",
        choices=[item.value for item in DiscoveryObjectiveKind],
        default=DiscoveryObjectiveKind.RESOLVE_CANONICAL_SOURCE.value,
    )
    result.add_argument("--field-path", action="append", default=[])
    result.add_argument("--reason-code", action="append", default=[])
    result.add_argument("--reviewed-domain", action="append", default=[])
    result.add_argument("--criticality-tier", type=int, choices=range(4), default=0)
    result.add_argument("--max-queries", type=int, choices=range(1, 11), default=1)
    result.add_argument(
        "--live",
        action="store_false",
        dest="dry_run",
        help="Record a private non-dry discovery run; leads still require human review",
    )
    result.set_defaults(dry_run=True)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    settings = get_settings()
    worker_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or f"{socket.gethostname()}-{os.getpid()}"
    with SystemSessionLocal() as session:
        health = OperationalJobService(session)
        health.started("catalogue_discovery")
        service = CatalogueDiscoveryControlService(session, settings)
        try:
            if args.resume is not None:
                run_id = args.resume
            else:
                request = CandidateDiscoveryRunRequest(
                    candidate_id=args.candidate,
                    objective_kind=DiscoveryObjectiveKind(args.objective),
                    field_paths=tuple(args.field_path)
                    or ("identity.official_source", "identity.provider"),
                    reason_codes=tuple(args.reason_code) or ("OFFICIAL_SOURCE_MISSING",),
                    criticality_tier=args.criticality_tier,
                    reviewed_domains=tuple(args.reviewed_domain),
                    dry_run=args.dry_run,
                )
                run_id = service.create_candidate_run(request).id
            result = service.process_run(
                run_id,
                worker_id=worker_id,
                max_queries=args.max_queries,
            )
            health.completed("catalogue_discovery", result.provider_calls_completed)
        except Exception as exc:
            health.failed("catalogue_discovery", exc)
            raise
    print(
        "Catalogue discovery run "
        f"id={result.id} status={result.status.value} "
        f"provider_calls={result.provider_calls_completed} leads={result.unique_leads}"
    )


if __name__ == "__main__":
    main()
