"""Run one zero-retry Azure OpenAI strict-schema capability request."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from app.core.config import get_settings
from app.modules.catalogue_ingestion.capability_probe import (
    DEFAULT_CAPABILITY_OBJECTIVE,
    persist_capability_probe_outcome,
    run_capability_probe,
)
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--objective",
        choices=[item.value for item in ClaimObjective],
        default=DEFAULT_CAPABILITY_OBJECTIVE.value,
    )
    result.add_argument("--max-completion-tokens", type=int, default=4_096)
    result.add_argument("--max-estimated-cost-usd", type=Decimal, default=Decimal("0.01"))
    result.add_argument("--evidence-path", type=Path, required=True)
    result.add_argument("--receipt-path", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    outcome = run_capability_probe(
        get_settings(),
        objective=ClaimObjective(args.objective),
        max_completion_tokens=args.max_completion_tokens,
        max_estimated_cost_usd=args.max_estimated_cost_usd,
    )
    persist_capability_probe_outcome(
        outcome,
        evidence_path=args.evidence_path,
        receipt_path=args.receipt_path,
    )
    evidence = outcome.evidence
    print(
        json.dumps(
            {
                "status": evidence["status"],
                "failure_category": evidence["failure_category"],
                "request": evidence["request"],
                "response": evidence["response"],
                "usage": evidence["usage"],
                "probe_contract": evidence["probe_contract"],
                "evidence_path": str(args.evidence_path),
                "receipt_created": outcome.receipt is not None,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if outcome.receipt is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
