"""Bounded, content-free Phase 9 staging load evidence harness.

This is deliberately a standard-library script: it can run in a restricted
staging runner without adding a load-testing client to the application image.
It sends only public catalogue reads by default. Authenticated refresh and a
bounded write probe are optional and must use dedicated disposable accounts.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass(frozen=True)
class Result:
    operation: str
    elapsed_ms: float
    status: int


def request(base_url: str, path: str, method: str = "GET", body: bytes | None = None) -> Result:
    started = time.perf_counter()
    operation = f"{method} {path.split('?')[0]}"
    target = urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
    try:
        with urllib.request.urlopen(
            urllib.request.Request(target, data=body, method=method), timeout=15
        ) as response:
            return Result(operation, (time.perf_counter() - started) * 1000, response.status)
    except urllib.error.HTTPError as error:
        return Result(operation, (time.perf_counter() - started) * 1000, error.code)
    except urllib.error.URLError:
        return Result(operation, (time.perf_counter() - started) * 1000, 0)


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * percent))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("PHASE9_LOAD_BASE_URL"))
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--include-refresh", action="store_true")
    args = parser.parse_args()
    if not args.base_url or args.requests < 1 or args.concurrency < 1:
        parser.error("--base-url plus positive --requests and --concurrency are required")

    operations = [("/api/v1/opportunities?limit=10&offset=0", "GET", None)] * args.requests
    if args.include_refresh:
        # This verifies session-refresh behavior only; it intentionally sends
        # no credential or account data. Configure a staging cookie at the edge
        # if authenticated refresh coverage is required.
        operations.append(("/api/v1/auth/refresh", "POST", b"{}"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda item: request(args.base_url, *item), operations))

    summary = {}
    for operation in sorted({result.operation for result in results}):
        current = [result for result in results if result.operation == operation]
        timings = [result.elapsed_ms for result in current]
        summary[operation] = {
            "count": len(current),
            "p50_ms": round(percentile(timings, 0.50), 1),
            "p95_ms": round(percentile(timings, 0.95), 1),
            "max_ms": round(max(timings), 1),
            "error_count": sum(result.status == 0 or result.status >= 500 for result in current),
            "status_counts": {
                str(status): sum(result.status == status for result in current)
                for status in sorted({result.status for result in current})
            },
        }
    print(
        json.dumps(
            {
                "base_url": args.base_url,
                "concurrency": args.concurrency,
                "operations": summary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
