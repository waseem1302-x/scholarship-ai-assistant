"""Run or validate the opt-in real-provider gold evaluation; never invoked by normal CI."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.core.config import get_settings
from app.modules.catalogue_ingestion.evaluation import (
    GoldItem,
    evaluate,
    validate_gold_set,
)
from app.modules.catalogue_ingestion.provider import get_extraction_provider


def load_gold(path: Path) -> list[GoldItem]:
    return [
        GoldItem.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the gold contract without constructing a provider or making model calls.",
    )
    args = parser.parse_args()

    gold = load_gold(args.gold)
    validation = validate_gold_set(gold)
    if args.validate_only:
        print(
            json.dumps(
                {
                    **validation,
                    "valid": True,
                    "model_calls_made": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    settings = get_settings()
    report = evaluate(
        get_extraction_provider(settings),
        gold,
        max_calls=settings.catalogue_ai_max_calls_per_run,
        max_cost=settings.catalogue_ai_max_estimated_cost_per_run,
    )
    print(json.dumps(asdict(report), default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
