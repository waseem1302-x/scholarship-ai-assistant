"""Validate local catalogue-worker readiness without processing a scholarship."""

import json

from app.core.config import get_settings
from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight


def main() -> None:
    report = run_catalogue_preflight(get_settings())
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
