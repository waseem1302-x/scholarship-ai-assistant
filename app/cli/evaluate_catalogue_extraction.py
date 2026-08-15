"""Run the opt-in real-provider gold evaluation; never invoked by normal CI."""

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.modules.catalogue_ingestion.evaluation import GoldItem, evaluate
from app.modules.catalogue_ingestion.provider import get_extraction_provider


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    args = parser.parse_args()
    gold = [
        GoldItem.model_validate_json(line) for line in args.gold.read_text().splitlines() if line
    ]
    settings = get_settings()
    report = evaluate(
        get_extraction_provider(settings),
        gold,
        max_calls=settings.catalogue_ai_max_calls_per_run,
        max_cost=settings.catalogue_ai_max_estimated_cost_per_run,
    )
    print(json.dumps(report.__dict__, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
