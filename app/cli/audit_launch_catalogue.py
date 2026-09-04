"""Audit the reviewed scholarship catalogue immediately before launch approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import SystemSessionLocal
from app.modules.opportunities.launch_audit import LaunchManifestEntry, audit_launch_catalogue


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--minimum-records", type=_positive_integer, default=12)
    result.add_argument("--manifest", type=Path)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    manifest_entries = None
    if args.manifest is not None:
        raw_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(raw_manifest, list):
            raise ValueError("launch manifest must be a JSON array")
        manifest_entries = [LaunchManifestEntry.model_validate(item) for item in raw_manifest]
        if len({entry.canonical_name.casefold() for entry in manifest_entries}) != len(
            manifest_entries
        ):
            raise ValueError("launch manifest canonical names must be unique")
    with SystemSessionLocal() as session:
        result = audit_launch_catalogue(
            session,
            minimum_records=args.minimum_records,
            manifest_entries=manifest_entries,
        )
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    if not result.ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
