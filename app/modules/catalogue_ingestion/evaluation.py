"""Gold-set evaluation with field-level accuracy, abstention, cost, and latency reporting."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.catalogue_ingestion.provider import (
    CatalogueExtractionProvider,
    ExtractionProviderError,
)


class GoldItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    official_url: str
    source_text: str = Field(min_length=20, max_length=500_000)
    expected: dict[str, Any]


@dataclass(frozen=True)
class EvaluationReport:
    sample_count: int
    official_source_correctness: float
    field_accuracy: dict[str, float]
    false_confident_values: int
    expected_unknown_accuracy: float
    duplicate_resolution_accuracy: float | None
    schema_validation_rate: float
    mean_cost: Decimal
    mean_latency_ms: int
    p95_latency_ms: int


def evaluate(
    provider: CatalogueExtractionProvider,
    gold: list[GoldItem],
    *,
    max_calls: int | None = None,
    max_cost: Decimal | None = None,
) -> EvaluationReport:
    if not gold:
        raise ValueError("gold set must not be empty")
    if max_calls is not None and len(gold) > max_calls:
        raise ValueError("gold set exceeds the configured model-call ceiling")
    correct: dict[str, int] = {}
    totals: dict[str, int] = {}
    official_correct = schema_success = false_confident = expected_unknown = unknown_correct = 0
    costs: list[Decimal] = []
    latencies: list[int] = []
    for item in gold:
        started = time.perf_counter()
        try:
            result = provider.extract(source_url=item.official_url, source_text=item.source_text)
        except ExtractionProviderError:
            latencies.append(int((time.perf_counter() - started) * 1000))
            costs.append(Decimal("0"))
            for path, expected in flatten(item.expected).items():
                totals[path] = totals.get(path, 0) + 1
                correct.setdefault(path, 0)
                if expected is None:
                    expected_unknown += 1
            continue
        schema_success += 1
        elapsed = max(result.usage.latency_ms, int((time.perf_counter() - started) * 1000))
        latencies.append(elapsed)
        costs.append(result.usage.estimated_cost)
        if max_cost is not None and sum(costs, Decimal("0")) > max_cost:
            raise RuntimeError("evaluation exceeded the configured estimated-cost ceiling")
        actual = result.output.model_dump(mode="json")
        evidence_urls = {entry.source_url for entry in result.output.evidence}
        official_correct += int(evidence_urls == {item.official_url})
        for path, expected in flatten(item.expected).items():
            actual_value = get_path(actual, path)
            totals[path] = totals.get(path, 0) + 1
            correct[path] = correct.get(path, 0) + int(actual_value == expected)
            if expected is None:
                expected_unknown += 1
                unknown_correct += int(actual_value is None)
                false_confident += int(actual_value is not None)
    ordered = sorted(latencies)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return EvaluationReport(
        sample_count=len(gold),
        official_source_correctness=official_correct / len(gold),
        field_accuracy={path: correct[path] / total for path, total in totals.items()},
        false_confident_values=false_confident,
        expected_unknown_accuracy=(unknown_correct / expected_unknown if expected_unknown else 1.0),
        duplicate_resolution_accuracy=None,
        schema_validation_rate=schema_success / len(gold),
        mean_cost=sum(costs, Decimal("0")) / Decimal(len(costs)),
        mean_latency_ms=int(statistics.mean(latencies)),
        p95_latency_ms=ordered[p95_index],
    )


def flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            result.update(flatten(item, path))
        else:
            result[path] = item
    return result


def get_path(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
