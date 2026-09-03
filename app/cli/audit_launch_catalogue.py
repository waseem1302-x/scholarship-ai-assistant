"""Audit the reviewed scholarship catalogue immediately before launch approval."""

from __future__ import annotations

import argparse
import json

from app.db.session import SystemSessionLocal
from app.modules.opportunities.launch_audit import audit_launch_catalogue


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--minimum-records", type=_positive_integer, default=12)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    with SystemSessionLocal() as session:
        result = audit_launch_catalogue(session, minimum_records=args.minimum_records)
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    if not result.ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
