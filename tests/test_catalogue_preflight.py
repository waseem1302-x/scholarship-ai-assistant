from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.catalogue_ingestion.ai_contract import (
    AZURE_OPENAI_API_MODE,
    AZURE_OPENAI_REQUEST_PATH,
    CAPABILITY_RECEIPT_SCHEMA_VERSION,
    azure_openai_request_url,
)
from app.modules.catalogue_ingestion.preflight import (
    PreflightProbes,
    WorkerHealthSnapshot,
    expected_catalogue_capability_contract,
    run_catalogue_preflight,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "catalogue-preflight-test-secret-is-long-enough",
        "catalogue_worker_min_free_disk_bytes": 100_000_000,
    }
    values.update(overrides)
    return Settings(**values)


def _receipt(settings: Settings) -> dict[str, object]:
    return {
        **expected_catalogue_capability_contract(settings),
        "model_family": "gpt-test",
        "verification": {
            "method": "live_strict_json_schema_request",
            "request_id": "request-12345678",
            "response_id": "response-12345678",
        },
        "verified_at": (NOW - timedelta(days=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=30)).isoformat(),
    }


def _probes(
    settings: Settings,
    *,
    credential_calls: list[str] | None = None,
    current_heads: set[str] | None = None,
    expected_heads: set[str] | None = None,
    free_bytes: int = 1_000_000_000,
    worker: WorkerHealthSnapshot | None = None,
    crawlee: bool = True,
    browser: bool = True,
    document_worker: bool = True,
    receipt: dict[str, object] | None = None,
) -> PreflightProbes:
    def credential_probe(_settings: Settings) -> None:
        if credential_calls is not None:
            credential_calls.append("called")

    return PreflightProbes(
        database=lambda _settings: None,
        migration_heads=lambda _settings: (
            current_heads if current_heads is not None else {"head"},
            expected_heads if expected_heads is not None else {"head"},
        ),
        free_disk_bytes=lambda: free_bytes,
        worker_health=lambda _settings: worker,
        azure_credential=credential_probe,
        crawlee_available=lambda: crawlee,
        browser_available=lambda: browser,
        document_worker_ready=lambda _settings, _now: document_worker,
        capability_receipt=lambda _path: receipt or _receipt(settings),
    )


def test_disabled_capabilities_are_reported_without_credential_or_model_probe() -> None:
    settings = _settings()
    credential_calls: list[str] = []

    report = run_catalogue_preflight(
        settings,
        probes=_probes(settings, credential_calls=credential_calls),
        now=NOW,
    )

    assert report["status"] == "ready"
    assert report["side_effects"] == "read_only_no_ingestion_or_model_calls"
    assert credential_calls == []
    assert report["checks"]["ai_ingestion"]["status"] == "disabled"
    assert report["checks"]["azure_credential"]["status"] == "disabled"
    assert report["checks"]["model_capability"]["status"] == "disabled"
    assert report["checks"]["crawlee_runtime"]["status"] == "disabled"
    assert report["checks"]["document_worker"]["status"] == "disabled"
    assert report["checks"]["publication"]["status"] == "disabled"
    assert report["checks"]["kill_switch"]["status"] == "disabled"


def test_enabled_pilot_capabilities_pass_with_injected_read_only_probes(tmp_path: Path) -> None:
    settings = _settings(
        catalogue_worker_health_required=True,
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://catalogue-test.openai.azure.com",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=1,
        catalogue_ai_max_calls_per_run=12,
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
        catalogue_bounded_crawling_enabled=True,
        catalogue_crawlee_static_enabled=True,
        catalogue_browser_fetching_enabled=True,
        catalogue_document_intelligence_enabled=True,
        catalogue_document_ocr_enabled=True,
        catalogue_document_worker_transport_root=str(tmp_path / "jobs"),
        catalogue_source_routing_enabled=True,
    )
    credential_calls: list[str] = []
    worker = WorkerHealthSnapshot(completed_at=NOW - timedelta(seconds=10), error_code=None)

    report = run_catalogue_preflight(
        settings,
        probes=_probes(settings, credential_calls=credential_calls, worker=worker),
        now=NOW,
    )

    assert report["status"] == "ready"
    assert credential_calls == ["called"]
    for name in (
        "catalogue_worker",
        "ai_ingestion",
        "ai_pricing",
        "azure_credential",
        "model_capability",
        "bounded_crawling",
        "crawlee_static",
        "crawlee_runtime",
        "browser_fetching",
        "browser_runtime",
        "document_conversion",
        "document_ocr",
        "document_worker",
        "source_routing",
        "kill_switch",
    ):
        assert report["checks"][name]["status"] == "ready"
    capability = report["checks"]["model_capability"]
    assert capability["api_mode"] == AZURE_OPENAI_API_MODE
    assert capability["request_path"] == AZURE_OPENAI_REQUEST_PATH
    assert len(capability["schema_sha256"]) == 64
    assert len(capability["prompt_sha256"]) == 64


def test_capability_receipt_uses_the_same_normalized_route_as_provider(tmp_path: Path) -> None:
    settings = _settings(
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="HTTPS://CATALOGUE-TEST.OPENAI.AZURE.COM:443/",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=1,
        catalogue_ai_max_calls_per_run=12,
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
    )

    receipt = _receipt(settings)
    runtime = receipt["runtime_contract"]
    assert isinstance(runtime, dict)
    assert runtime["endpoint"] == "https://catalogue-test.openai.azure.com"
    assert azure_openai_request_url(settings.catalogue_ai_endpoint or "") == (
        "https://catalogue-test.openai.azure.com/openai/v1/chat/completions"
    )

    report = run_catalogue_preflight(
        settings, probes=_probes(settings, receipt=receipt), now=NOW
    )

    assert report["checks"]["model_capability"]["status"] == "ready"


@pytest.mark.parametrize(
    ("section", "field", "value", "mismatched_field"),
    [
        ("runtime_contract", "provider", "other_provider", "runtime_contract.provider"),
        (
            "runtime_contract",
            "endpoint",
            "https://other.openai.azure.com",
            "runtime_contract.endpoint",
        ),
        (
            "runtime_contract",
            "deployment",
            "different-deployment",
            "runtime_contract.deployment",
        ),
        (
            "runtime_contract",
            "api_mode",
            "dated_preview_chat_completions",
            "runtime_contract.api_mode",
        ),
        (
            "runtime_contract",
            "request_path",
            "/openai/deployments/example/chat/completions",
            "runtime_contract.request_path",
        ),
        (
            "runtime_contract",
            "strict_json_schema",
            False,
            "runtime_contract.strict_json_schema",
        ),
        (
            "extraction_contract",
            "schema_sha256",
            "0" * 64,
            "extraction_contract.schema_sha256",
        ),
        (
            "extraction_contract",
            "prompt_sha256",
            "f" * 64,
            "extraction_contract.prompt_sha256",
        ),
    ],
)
def test_capability_receipt_rejects_unrelated_runtime_or_extraction_contract(
    tmp_path: Path,
    section: str,
    field: str,
    value: object,
    mismatched_field: str,
) -> None:
    settings = _settings(
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://catalogue-test.openai.azure.com",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=1,
        catalogue_ai_max_calls_per_run=12,
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
    )
    receipt = deepcopy(_receipt(settings))
    nested = receipt[section]
    assert isinstance(nested, dict)
    nested[field] = value

    report = run_catalogue_preflight(
        settings, probes=_probes(settings, receipt=receipt), now=NOW
    )

    capability = report["checks"]["model_capability"]
    assert capability["status"] == "blocked"
    assert capability["reason"] == "model_capability_receipt_mismatch"
    assert capability["mismatched_fields"] == [mismatched_field]


def test_capability_receipt_rejects_legacy_incomplete_and_expired_evidence(
    tmp_path: Path,
) -> None:
    settings = _settings(
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://catalogue-test.openai.azure.com",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=1,
        catalogue_ai_max_calls_per_run=12,
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
    )

    legacy = _receipt(settings)
    legacy["schema_version"] = CAPABILITY_RECEIPT_SCHEMA_VERSION - 1
    legacy_report = run_catalogue_preflight(
        settings, probes=_probes(settings, receipt=legacy), now=NOW
    )
    assert legacy_report["checks"]["model_capability"] == {
        "status": "blocked",
        "reason": "unsupported_model_capability_receipt_schema",
        "required_schema_version": CAPABILITY_RECEIPT_SCHEMA_VERSION,
    }

    incomplete = deepcopy(_receipt(settings))
    verification = incomplete["verification"]
    assert isinstance(verification, dict)
    del verification["response_id"]
    incomplete_report = run_catalogue_preflight(
        settings, probes=_probes(settings, receipt=incomplete), now=NOW
    )
    assert incomplete_report["checks"]["model_capability"] == {
        "status": "blocked",
        "reason": "invalid_model_capability_receipt",
        "invalid_fields": ["verification.response_id:missing"],
    }

    expired = _receipt(settings)
    expired["expires_at"] = NOW.isoformat()
    expired_report = run_catalogue_preflight(
        settings, probes=_probes(settings, receipt=expired), now=NOW
    )
    assert expired_report["checks"]["model_capability"] == {
        "status": "blocked",
        "reason": "expired_or_invalid_model_capability_receipt",
    }


def test_preflight_blocks_migration_disk_worker_and_capability_mismatches(tmp_path: Path) -> None:
    settings = _settings(
        catalogue_worker_health_required=True,
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://catalogue-test.openai.azure.com",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=1,
        catalogue_ai_max_calls_per_run=12,
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
        catalogue_crawlee_static_enabled=True,
        catalogue_document_intelligence_enabled=True,
        catalogue_document_worker_transport_root=str(tmp_path / "jobs"),
    )
    mismatched_receipt = _receipt(settings)
    runtime_contract = mismatched_receipt["runtime_contract"]
    assert isinstance(runtime_contract, dict)
    runtime_contract["deployment"] = "different-deployment"
    worker = WorkerHealthSnapshot(completed_at=NOW - timedelta(hours=1), error_code="WorkerFailure")

    report = run_catalogue_preflight(
        settings,
        probes=_probes(
            settings,
            current_heads={"old"},
            expected_heads={"head"},
            free_bytes=99_999_999,
            worker=worker,
            crawlee=False,
            document_worker=False,
            receipt=mismatched_receipt,
        ),
        now=NOW,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["database_migrations"]["reason"] == (
        "database_migration_heads_mismatch"
    )
    assert report["checks"]["disk_capacity"]["reason"] == "insufficient_free_disk"
    assert report["checks"]["catalogue_worker"]["reason"] == ("catalogue_worker_stale_or_failed")
    assert report["checks"]["model_capability"]["mismatched_fields"] == [
        "runtime_contract.deployment"
    ]
    assert report["checks"]["crawlee_runtime"]["reason"] == "crawlee_not_installed"
    assert report["checks"]["document_worker"]["reason"] == (
        "document_worker_transport_stale_or_unavailable"
    )


def test_browser_runtime_and_remaining_forbidden_capabilities_fail_closed() -> None:
    settings = _settings(
        catalogue_browser_fetching_enabled=True,
        catalogue_scheduled_ingestion_enabled=True,
        catalogue_graph_writes_enabled=True,
    )

    report = run_catalogue_preflight(
        settings,
        probes=_probes(settings, browser=False),
        now=NOW,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["browser_fetching"]["status"] == "ready"
    assert report["checks"]["browser_runtime"] == {
        "status": "blocked",
        "reason": "playwright_chromium_not_installed",
    }
    assert report["checks"]["scheduled_ingestion"]["status"] == "blocked"
    assert report["checks"]["graph_writes"]["status"] == "blocked"


def test_enabled_ai_reports_only_safe_credential_failure_code(tmp_path: Path) -> None:
    settings = _settings(
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://catalogue-test.openai.azure.com",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=1,
        catalogue_ai_max_calls_per_run=12,
        catalogue_ai_max_retries=0,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
    )
    probes = _probes(settings)

    def rejected_credential(_settings: Settings) -> None:
        raise RuntimeError("private tenant and account details")

    probes = PreflightProbes(
        database=probes.database,
        migration_heads=probes.migration_heads,
        free_disk_bytes=probes.free_disk_bytes,
        worker_health=probes.worker_health,
        azure_credential=rejected_credential,
        crawlee_available=probes.crawlee_available,
        browser_available=probes.browser_available,
        document_worker_ready=probes.document_worker_ready,
        capability_receipt=probes.capability_receipt,
    )

    report = run_catalogue_preflight(settings, probes=probes, now=NOW)

    assert report["status"] == "blocked"
    credential = report["checks"]["azure_credential"]
    assert credential == {
        "status": "blocked",
        "reason": "azure_credential_probe_failed",
        "error_code": "RuntimeError",
    }
    assert "private tenant" not in str(report)


def test_enabled_ai_rejects_unverified_batch_and_insufficient_call_budget(
    tmp_path: Path,
) -> None:
    settings = _settings(
        catalogue_ai_ingestion_enabled=True,
        catalogue_ai_provider="azure_openai",
        catalogue_ai_endpoint="https://catalogue-test.openai.azure.com",
        catalogue_ai_model="catalogue-test-deployment",
        catalogue_ai_max_candidates_per_run=26,
        catalogue_ai_max_pages_per_candidate=4,
        catalogue_ai_max_calls_per_run=13,
        catalogue_ai_max_retries=1,
        catalogue_ai_input_cost_per_million=Decimal("1.25"),
        catalogue_ai_output_cost_per_million=Decimal("5.00"),
        catalogue_ai_capability_receipt_path=str(tmp_path / "receipt.json"),
        catalogue_worker_kill_switch_path=str(tmp_path / "STOP"),
    )

    report = run_catalogue_preflight(settings, probes=_probes(settings), now=NOW)

    assert report["status"] == "blocked"
    assert report["checks"]["run_budgets"] == {
        "status": "blocked",
        "reason": "unsafe_catalogue_run_budget",
        "violations": [
            "max_candidates_exceeds_verified_batch_size",
            "max_model_calls_cannot_cover_all_objectives",
            "automatic_provider_retries_must_be_zero",
        ],
        "max_candidates": 26,
        "max_pages_per_candidate": 4,
        "max_model_calls": 13,
        "max_provider_retries": 1,
        "max_input_characters": 80_000,
        "max_output_tokens": 6_000,
        "max_estimated_cost": "50.00",
    }


def test_enabled_ai_preflight_requires_an_available_inactive_kill_switch(tmp_path: Path) -> None:
    common = {
        "catalogue_ai_ingestion_enabled": True,
        "catalogue_ai_provider": "azure_openai",
        "catalogue_ai_endpoint": "https://catalogue-test.openai.azure.com",
        "catalogue_ai_model": "catalogue-test-deployment",
        "catalogue_ai_max_candidates_per_run": 1,
        "catalogue_ai_max_calls_per_run": 8,
        "catalogue_ai_max_retries": 0,
        "catalogue_ai_input_cost_per_million": Decimal("1.25"),
        "catalogue_ai_output_cost_per_million": Decimal("5.00"),
        "catalogue_ai_capability_receipt_path": str(tmp_path / "receipt.json"),
    }

    missing = _settings(**common)
    missing_report = run_catalogue_preflight(
        missing, probes=_probes(missing), now=NOW
    )
    assert missing_report["checks"]["kill_switch"] == {
        "status": "blocked",
        "reason": "kill_switch_path_required",
    }

    unavailable = _settings(
        **common,
        catalogue_worker_kill_switch_path=str(tmp_path / "missing" / "STOP"),
    )
    unavailable_report = run_catalogue_preflight(
        unavailable, probes=_probes(unavailable), now=NOW
    )
    assert unavailable_report["checks"]["kill_switch"] == {
        "status": "blocked",
        "reason": "kill_switch_parent_unavailable",
    }

    switch = tmp_path / "STOP"
    switch.write_text("stop\n", encoding="utf-8")
    active = _settings(**common, catalogue_worker_kill_switch_path=str(switch))
    active_report = run_catalogue_preflight(active, probes=_probes(active), now=NOW)
    assert active_report["checks"]["kill_switch"] == {
        "status": "blocked",
        "reason": "operator_kill_switch_active",
    }
