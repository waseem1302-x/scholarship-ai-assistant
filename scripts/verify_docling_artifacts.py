"""Verify the reviewed Docling artifact bundle baked into a worker image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _bundle_entries(root: Path) -> list[dict[str, int | str]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        # A model bundle is assembled on Windows and verified in a Linux
        # worker.  Sort the serialized POSIX paths rather than ``Path``
        # objects, whose comparison inherits host filesystem semantics.
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        if path.is_file() and ".cache" not in path.parts
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    args = parser.parse_args()

    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    entries = _bundle_entries(args.model_dir)
    bundle = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
    actual = {
        "file_count": len(entries),
        "total_bytes": sum(int(entry["bytes"]) for entry in entries),
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
    }
    expected = {name: lock[name] for name in actual}
    if actual != expected:
        raise SystemExit(f"Docling artifact lock mismatch: expected={expected!r} actual={actual!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
