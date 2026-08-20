"""Low-cardinality catalogue pipeline metrics for local diagnostics and Azure Monitor."""

from collections import Counter
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from app.core.config import Settings

COUNTERS = {
    "ingestion_runs_total",
    "candidates_discovered",
    "official_sources_found",
    "official_sources_missing",
    "source_fetch_success",
    "source_fetch_failure",
    "ai_extraction_calls",
    "ai_extraction_failures",
    "ai_schema_failures",
    "validation_failures",
    "duplicate_candidates",
    "candidates_ready_for_review",
    "candidates_published",
    "source_changes_detected",
    "model_input_tokens",
    "model_output_tokens",
}
HISTOGRAMS = {"queue_lag", "estimated_ai_cost"}


@dataclass
class CatalogueMetrics:
    external_enabled: bool = False
    values: Counter[str] = field(default_factory=Counter)
    _lock: Lock = field(default_factory=Lock)
    _counters: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _histograms: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.external_enabled:
            return
        from opentelemetry import metrics

        meter = metrics.get_meter("scholarship.catalogue_ingestion", "1.0")
        self._counters = {
            name: meter.create_counter(name, unit="{event}") for name in sorted(COUNTERS)
        }
        self._histograms = {
            "queue_lag": meter.create_histogram("queue_lag", unit="s"),
            "estimated_ai_cost": meter.create_histogram("estimated_ai_cost", unit="USD"),
        }

    def add(self, name: str, value: int = 1) -> None:
        if name not in COUNTERS or value < 0:
            raise ValueError("unsupported catalogue counter")
        with self._lock:
            self.values[name] += value
        if self.external_enabled:
            self._counters[name].add(value)

    def observe(self, name: str, value: float) -> None:
        if name not in HISTOGRAMS or value < 0:
            raise ValueError("unsupported catalogue histogram")
        if self.external_enabled:
            self._histograms[name].record(value)


_LOCAL_METRICS = CatalogueMetrics()
_EXTERNAL_METRICS: CatalogueMetrics | None = None


def get_catalogue_metrics(settings: Settings) -> CatalogueMetrics:
    global _EXTERNAL_METRICS
    if settings.metrics_backend != "external":
        return _LOCAL_METRICS
    if _EXTERNAL_METRICS is None:
        _EXTERNAL_METRICS = CatalogueMetrics(external_enabled=True)
    return _EXTERNAL_METRICS
