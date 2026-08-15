"""Gold-set evaluation with evidence-backed scoring, abstention, cost, and latency reporting."""

from __future__ import annotations

import json
import math
import re
import statistics
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.catalogue_ingestion.provider import (
    CatalogueExtractionProvider,
    ExtractionProviderError,
)

# These values are resolved or derived by deterministic catalogue/link/cycle logic rather than AI.
NON_AI_PATHS = frozenset(
    {
        "identity.provider_canonical_id",
        "identity.provider_website_url",
        "identity.university_website_url",
        "identity.country_code",
        "identity.programme_family_id",
        "study.cycle_id",
        "funding.funding_type",
        "application.application_url",
        # The v1 extraction contract cannot represent "unknown" for this boolean safely.
        "application.is_rolling",
    }
)

# Fact paths that the extraction benchmark is allowed to score.
AI_SCORABLE_PATHS = frozenset(
    {
        "identity.name",
        "identity.provider_name",
        "identity.university_name",
        "identity.country",
        "study.degree_level",
        "study.field_eligibility",
        "study.intake_year",
        "funding.funding_policy",
        "funding.tuition_coverage_status",
        "funding.stipend_coverage_status",
        "funding.accommodation_coverage_status",
        "funding.travel_coverage_status",
        "funding.insurance_coverage_status",
        "funding.fees_coverage_status",
        "funding.application_fee_status",
        "funding.tuition_coverage",
        "funding.monthly_stipend_amount",
        "funding.monthly_stipend_currency",
        "funding.accommodation_coverage",
        "funding.travel_allowance",
        "funding.health_insurance",
        "funding.application_fee_info",
        "eligibility.nationality_eligibility",
        "eligibility.minimum_academic_requirement",
        "eligibility.english_language_requirement",
        "eligibility.standardized_test_requirement",
        "eligibility.rules",
        "application.application_opening_date",
        "application.application_deadline",
        "application.timezone",
        "application.application_method",
        "application.required_documents",
    }
)

URL_PATHS = frozenset(
    {
        "identity.provider_website_url",
        "identity.university_website_url",
        "application.application_url",
    }
)
DATETIME_PATHS = frozenset(
    {
        "application.application_opening_date",
        "application.application_deadline",
    }
)
UNORDERED_LIST_PATHS = frozenset(
    {
        "application.required_documents",
        "eligibility.rules",
    }
)
NUMERIC_PATHS = frozenset(
    {
        "study.intake_year",
        "funding.monthly_stipend_amount",
    }
)


class GoldItem(BaseModel):
    """One evidence-backed extraction benchmark item.

    Every expected non-null value must have a verbatim support excerpt from source_text.
    Unknowns are explicit paths, never implicit nulls mixed into expected.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    official_url: str
    source_text: str = Field(min_length=20, max_length=500_000)
    expected: dict[str, Any]
    support: dict[str, str] = Field(default_factory=dict)
    expected_unknown: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gold_contract(self) -> GoldItem:
        flattened = flatten(self.expected)
        if not flattened and not self.expected_unknown:
            raise ValueError("gold item must score at least one expected or expected-unknown path")

        null_paths = sorted(path for path, value in flattened.items() if value is None)
        if null_paths:
            raise ValueError(
                "null expectations must use expected_unknown instead: " + ", ".join(null_paths)
            )

        expected_paths = set(flattened)
        unknown_paths = set(self.expected_unknown)

        if len(self.expected_unknown) != len(unknown_paths):
            raise ValueError("expected_unknown contains duplicate paths")

        overlap = sorted(expected_paths & unknown_paths)
        if overlap:
            raise ValueError(
                "paths cannot be both expected and expected_unknown: " + ", ".join(overlap)
            )

        invalid_paths = sorted((expected_paths | unknown_paths) - AI_SCORABLE_PATHS)
        if invalid_paths:
            derived = [path for path in invalid_paths if path in NON_AI_PATHS]
            if derived:
                raise ValueError(
                    "paths are deterministic/resolved and not AI-scored: " + ", ".join(derived)
                )
            raise ValueError("unknown extraction benchmark paths: " + ", ".join(invalid_paths))

        support_paths = set(self.support)
        missing_support = sorted(expected_paths - support_paths)
        extra_support = sorted(support_paths - expected_paths)
        if missing_support:
            raise ValueError(
                "every expected value requires a support excerpt: " + ", ".join(missing_support)
            )
        if extra_support:
            raise ValueError("support contains unscored paths: " + ", ".join(extra_support))

        for path, excerpt in self.support.items():
            if not excerpt.strip():
                raise ValueError(f"support excerpt is empty for {path}")
            if excerpt not in self.source_text:
                raise ValueError(f"support excerpt is not verbatim source text for {path}")

        return self


@dataclass(frozen=True)
class EvaluationReport:
    sample_count: int
    successful_extractions: int
    provider_failure_count: int
    official_source_correctness: float
    official_source_mismatches: int
    field_accuracy: dict[str, float]
    field_totals: dict[str, int]
    false_confident_values: int
    expected_unknown_accuracy: float | None
    expected_unknown_count: int
    benchmark_expected_unknown_count: int
    duplicate_resolution_accuracy: float | None
    schema_validation_rate: float
    total_estimated_cost: Decimal
    mean_cost: Decimal
    costed_call_count: int
    uncosted_provider_failure_count: int
    total_estimated_cost_is_lower_bound: bool
    mean_latency_ms: int
    p95_latency_ms: int
    item_results: list[dict[str, Any]]


def validate_gold_set(gold: list[GoldItem]) -> dict[str, int | float]:
    """Fail before provider calls when the benchmark itself cannot test the safety contract."""

    if not gold:
        raise ValueError("gold set must not be empty")

    ids = [item.id for item in gold]
    if len(ids) != len(set(ids)):
        raise ValueError("gold set contains duplicate item ids")

    expected_field_count = sum(len(flatten(item.expected)) for item in gold)
    expected_unknown_count = sum(len(item.expected_unknown) for item in gold)
    support_count = sum(len(item.support) for item in gold)

    if expected_unknown_count == 0:
        raise ValueError(
            "gold set must include explicit expected_unknown paths so "
            "hallucination scoring is meaningful"
        )

    return {
        "sample_count": len(gold),
        "expected_field_count": expected_field_count,
        "expected_unknown_count": expected_unknown_count,
        "support_count": support_count,
        "support_coverage": (support_count / expected_field_count if expected_field_count else 1.0),
    }


def evaluate(
    provider: CatalogueExtractionProvider,
    gold: list[GoldItem],
    *,
    max_calls: int | None = None,
    max_cost: Decimal | None = None,
) -> EvaluationReport:
    validate_gold_set(gold)
    if max_calls is not None and len(gold) > max_calls:
        raise ValueError("gold set exceeds the configured model-call ceiling")

    correct: dict[str, int] = {}
    totals: dict[str, int] = {}
    successful_extractions = 0
    provider_failures = 0
    official_correct = 0
    official_mismatches = 0
    false_confident = 0
    expected_unknown = 0
    benchmark_expected_unknown = sum(len(item.expected_unknown) for item in gold)
    unknown_correct = 0
    costs: list[Decimal] = []
    uncosted_provider_failures = 0
    latencies: list[int] = []
    item_results: list[dict[str, Any]] = []

    for item in gold:
        flattened_expected = flatten(item.expected)
        started = time.perf_counter()

        try:
            result = provider.extract(source_url=item.official_url, source_text=item.source_text)
        except ExtractionProviderError as exc:
            measured_latency = int((time.perf_counter() - started) * 1000)
            failure_usage = getattr(exc, "usage", None)

            if failure_usage is not None:
                latency = max(failure_usage.latency_ms, measured_latency)
                failure_cost: Decimal | None = failure_usage.estimated_cost
                costs.append(failure_cost)

                total_cost = sum(costs, Decimal("0"))
                if max_cost is not None and total_cost > max_cost:
                    raise RuntimeError(
                        "evaluation exceeded the configured estimated-cost ceiling"
                    ) from exc
            else:
                latency = measured_latency
                failure_cost = None
                uncosted_provider_failures += 1

            latencies.append(latency)
            provider_failures += 1

            item_results.append(
                {
                    "id": item.id,
                    "status": "provider_error",
                    "error_code": getattr(exc, "code", "ai_extraction_failed"),
                    "latency_ms": latency,
                    "estimated_cost": (str(failure_cost) if failure_cost is not None else None),
                    "cost_known": failure_cost is not None,
                }
            )
            continue

        successful_extractions += 1
        expected_unknown += len(item.expected_unknown)

        elapsed = max(
            result.usage.latency_ms,
            int((time.perf_counter() - started) * 1000),
        )
        latencies.append(elapsed)
        costs.append(result.usage.estimated_cost)

        total_cost = sum(costs, Decimal("0"))
        if max_cost is not None and total_cost > max_cost:
            raise RuntimeError("evaluation exceeded the configured estimated-cost ceiling")

        actual = result.output.model_dump(mode="json")
        evidence_urls = {entry.source_url for entry in result.output.evidence}
        source_ok = evidence_urls == {item.official_url}
        official_correct += int(source_ok)
        official_mismatches += int(not source_ok)

        item_field_results: dict[str, bool] = {}
        item_field_mismatches: list[dict[str, Any]] = []

        for path, expected in flattened_expected.items():
            actual_value = get_path(actual, path)
            matched = values_equal(path, actual_value, expected)
            totals[path] = totals.get(path, 0) + 1
            correct[path] = correct.get(path, 0) + int(matched)
            item_field_results[path] = matched

            if not matched:
                item_field_mismatches.append(
                    {
                        "path": path,
                        "expected": expected,
                        "actual": actual_value,
                    }
                )

        item_unknown_results: dict[str, bool] = {}
        item_unknown_mismatches: list[dict[str, Any]] = []

        for path in item.expected_unknown:
            actual_value = get_path(actual, path)
            abstained = is_unknown_value(path, actual_value)
            unknown_correct += int(abstained)
            false_confident += int(not abstained)
            item_unknown_results[path] = abstained

            if not abstained:
                item_unknown_mismatches.append(
                    {
                        "path": path,
                        "actual": actual_value,
                    }
                )

        item_results.append(
            {
                "id": item.id,
                "status": "ok",
                "official_source_correct": source_ok,
                "field_results": item_field_results,
                "field_mismatches": item_field_mismatches,
                "unknown_results": item_unknown_results,
                "unknown_mismatches": item_unknown_mismatches,
                "latency_ms": elapsed,
                "estimated_cost": str(result.usage.estimated_cost),
                "cost_known": True,
            }
        )

    ordered = sorted(latencies)
    p95_index = max(
        0,
        min(
            len(ordered) - 1,
            math.ceil(len(ordered) * 0.95) - 1,
        ),
    )
    total_cost = sum(costs, Decimal("0"))

    return EvaluationReport(
        sample_count=len(gold),
        successful_extractions=successful_extractions,
        provider_failure_count=provider_failures,
        official_source_correctness=(
            official_correct / successful_extractions if successful_extractions else 0.0
        ),
        official_source_mismatches=official_mismatches,
        field_accuracy={path: correct[path] / total for path, total in totals.items()},
        field_totals=totals,
        false_confident_values=false_confident,
        expected_unknown_accuracy=(
            unknown_correct / expected_unknown if expected_unknown else None
        ),
        expected_unknown_count=expected_unknown,
        benchmark_expected_unknown_count=benchmark_expected_unknown,
        duplicate_resolution_accuracy=None,
        schema_validation_rate=successful_extractions / len(gold),
        total_estimated_cost=total_cost,
        mean_cost=(total_cost / Decimal(len(costs)) if costs else Decimal("0")),
        costed_call_count=len(costs),
        uncosted_provider_failure_count=uncosted_provider_failures,
        total_estimated_cost_is_lower_bound=uncosted_provider_failures > 0,
        mean_latency_ms=int(statistics.mean(latencies)),
        p95_latency_ms=ordered[p95_index],
        item_results=item_results,
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


def values_equal(path: str, actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return actual is expected

    if path in URL_PATHS and isinstance(actual, str) and isinstance(expected, str):
        return _normalize_url(actual) == _normalize_url(expected)

    if path in DATETIME_PATHS and isinstance(actual, str) and isinstance(expected, str):
        actual_dt = _parse_datetime(actual)
        expected_dt = _parse_datetime(expected)
        return actual_dt is not None and expected_dt is not None and actual_dt == expected_dt

    if path in UNORDERED_LIST_PATHS and isinstance(actual, list) and isinstance(expected, list):
        return _normalize_unordered_list(actual) == _normalize_unordered_list(expected)

    if path in NUMERIC_PATHS:
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except InvalidOperation:
            return False

    if _is_number(actual) and _is_number(expected):
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except InvalidOperation:
            return False

    if path == "identity.name" and isinstance(actual, str) and isinstance(expected, str):
        return _normalize_identity_name(actual) == _normalize_identity_name(expected)

    if isinstance(actual, str) and isinstance(expected, str):
        return _normalize_text(actual) == _normalize_text(expected)

    return actual == expected


def is_unknown_value(path: str, value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and _normalize_text(value) == "unknown":
        return True
    return path in {"application.required_documents", "eligibility.rules"} and value == []


def _normalize_identity_name(value: str) -> str:
    """Normalize narrow, non-semantic official-page title decoration."""

    normalized = _normalize_text(value)

    # Audience decoration used by official opportunity pages.
    normalized = re.sub(
        r"\s+\((?:student|students)\)$",
        "",
        normalized,
    )

    # Some official pages append an organisation acronym to the
    # programme title, e.g. "... (EPOS) - DAAD". Strip only an
    # uppercase acronym-shaped suffix from the original value.
    acronym_suffix = re.search(
        r"\s+-\s+([A-Z][A-Z0-9.&]{1,15})\s*$",
        value.strip(),
    )

    if acronym_suffix is not None:
        suffix = _normalize_text(acronym_suffix.group(0))

        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].rstrip()

    return normalized


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2013": "-",
                "\u2014": "-",
                "\u00a0": " ",
            }
        )
    )
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold()
    port = parsed.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _parse_datetime(value: str) -> datetime | None:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _normalize_unordered_list(value: list[Any]) -> list[str]:
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized.append(_normalize_text(item))
        else:
            normalized.append(
                json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            )
    return sorted(normalized)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
