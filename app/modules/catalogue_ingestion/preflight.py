"""Read-only readiness checks for the opt-in catalogue ingestion worker."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.catalogue_ingestion.acquisition_bundle import MAX_ACCEPTED_ARTIFACTS
from app.modules.catalogue_ingestion.ai_contract import (
    CAPABILITY_RECEIPT_SCHEMA_VERSION,
    azure_openai_runtime_contract,
)
from app.modules.catalogue_ingestion.claim_provider import (
    _objective_azure_schema,
    claim_extraction_prompt_hash,
)
from app.modules.catalogue_ingestion.claim_schemas import CLAIM_SCHEMA_VERSION, ClaimObjective
from app.modules.catalogue_ingestion.provider import (
    azure_structured_output_schema,
    extraction_prompt_hash,
)
from app.modules.catalogue_ingestion.schemas import EXTRACTION_SCHEMA_VERSION
from app.modules.catalogue_ingestion.worker_safety import (
    kill_switch_active,
    kill_switch_available,
)
from app.modules.operations.models import OperationalJobHealth


@dataclass(frozen=True)
class WorkerHealthSnapshot:
    completed_at: datetime | None
    error_code: str | None


@dataclass(frozen=True)
class PreflightProbes:
    """Injectable boundaries keep the readiness contract deterministic in tests."""

    database: Callable[[Settings], None]
    migration_heads: Callable[[Settings], tuple[set[str], set[str]]]
    free_disk_bytes: Callable[[], int]
    worker_health: Callable[[Settings], WorkerHealthSnapshot | None]
    azure_credential: Callable[[Settings], None]
    crawlee_available: Callable[[], bool]
    browser_available: Callable[[], bool]
    document_worker_ready: Callable[[Settings, datetime], bool]
    capability_receipt: Callable[[Path], Mapping[str, Any]]


def _database_probe(settings: Settings) -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    finally:
        engine.dispose()


def _migration_heads_probe(settings: Settings) -> tuple[set[str], set[str]]:
    expected = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    return current, expected


def _free_disk_bytes_probe() -> int:
    return shutil.disk_usage(tempfile.gettempdir()).free


def _worker_health_probe(settings: Settings) -> WorkerHealthSnapshot | None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            health = session.get(OperationalJobHealth, "catalogue_ingestion")
            if health is None:
                return None
            return WorkerHealthSnapshot(
                completed_at=health.last_completed_at,
                error_code=health.last_error_code,
            )
    finally:
        engine.dispose()


def _azure_credential_probe(settings: Settings) -> None:
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    try:
        credential.get_token(settings.catalogue_ai_token_scope)
    finally:
        close = getattr(credential, "close", None)
        if callable(close):
            close()


def _crawlee_available_probe() -> bool:
    return importlib.util.find_spec("crawlee") is not None


def _browser_available_probe() -> bool:
    if importlib.util.find_spec("playwright") is None:
        return False
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        return Path(playwright.chromium.executable_path).is_file()


def _document_worker_ready_probe(settings: Settings, now: datetime) -> bool:
    root = settings.catalogue_document_worker_transport_root
    if not root:
        return False
    heartbeat = Path(root) / "health" / "worker-heartbeat"
    try:
        return (
            heartbeat.is_file()
            and heartbeat.stat().st_mtime
            >= (now - timedelta(minutes=settings.operational_job_stale_minutes)).timestamp()
        )
    except OSError:
        return False


def _capability_receipt_probe(path: Path) -> Mapping[str, Any]:
    if path.stat().st_size > 65_536:
        raise ValueError("capability_receipt_too_large")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("capability_receipt_duplicate_key")
            value[key] = item
        return value

    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
    )
    if not isinstance(value, dict):
        raise ValueError("capability_receipt_not_an_object")
    return value


DEFAULT_PROBES = PreflightProbes(
    database=_database_probe,
    migration_heads=_migration_heads_probe,
    free_disk_bytes=_free_disk_bytes_probe,
    worker_health=_worker_health_probe,
    azure_credential=_azure_credential_probe,
    crawlee_available=_crawlee_available_probe,
    browser_available=_browser_available_probe,
    document_worker_ready=_document_worker_ready_probe,
    capability_receipt=_capability_receipt_probe,
)


def _check(status: str, *, reason: str | None = None, **details: object) -> dict[str, object]:
    result: dict[str, object] = {"status": status}
    if reason:
        result["reason"] = reason
    result.update(details)
    return result


def _probe_failure(name: str, exc: BaseException) -> dict[str, object]:
    # Exception messages may contain credentials, hosts, or local paths. Only
    # expose a stable check name and exception class in operator output.
    return _check("blocked", reason=f"{name}_probe_failed", error_code=type(exc).__name__)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_receipt_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field}_missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field}_timezone_missing")
    return parsed.astimezone(UTC)


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def catalogue_extraction_contract_identity() -> dict[str, object]:
    """Fingerprint every strict extraction schema and prompt the worker may send."""

    objectives = sorted(ClaimObjective, key=lambda item: item.value)
    schema_manifest = {
        "catalogue_extraction": {
            "schema_version": EXTRACTION_SCHEMA_VERSION,
            "response_format_name": "catalogue_extraction",
            "schema": azure_structured_output_schema(),
        },
        "catalogue_claim_extraction": {
            objective.value: {
                "schema_version": f"{CLAIM_SCHEMA_VERSION}.{objective.value}",
                "response_format_name": "catalogue_claim_extraction",
                "schema": _objective_azure_schema(objective),
            }
            for objective in objectives
        },
    }
    prompt_manifest = {
        "catalogue_extraction": extraction_prompt_hash(),
        "catalogue_claim_extraction": {
            objective.value: claim_extraction_prompt_hash(objective)
            for objective in objectives
        },
    }
    return {
        "identity_version": 1,
        "schema_sha256": _canonical_json_hash(schema_manifest),
        "prompt_sha256": _canonical_json_hash(prompt_manifest),
    }


def expected_catalogue_capability_contract(settings: Settings) -> dict[str, object]:
    """Return the non-evidence portion of a current capability receipt."""

    return {
        "schema_version": CAPABILITY_RECEIPT_SCHEMA_VERSION,
        "runtime_contract": azure_openai_runtime_contract(
            settings.catalogue_ai_endpoint or "", settings.catalogue_ai_model
        ),
        "extraction_contract": catalogue_extraction_contract_identity(),
    }


_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "runtime_contract",
        "extraction_contract",
        "model_family",
        "verification",
        "verified_at",
        "expires_at",
    }
)
_RUNTIME_CONTRACT_FIELDS = frozenset(
    {
        "provider",
        "endpoint",
        "deployment",
        "api_mode",
        "request_path",
        "strict_json_schema",
    }
)
_EXTRACTION_CONTRACT_FIELDS = frozenset(
    {"identity_version", "schema_sha256", "prompt_sha256"}
)
_VERIFICATION_FIELDS = frozenset({"method", "request_id", "response_id"})
_LIVE_VERIFICATION_METHOD = "live_strict_json_schema_request"


def _mapping_shape_errors(
    value: object, expected_fields: frozenset[str], prefix: str
) -> list[str]:
    if not isinstance(value, Mapping):
        return [prefix]
    actual_fields = set(value)
    return [
        *(f"{prefix}.{field}:missing" for field in sorted(expected_fields - actual_fields)),
        *(f"{prefix}.{field}:unexpected" for field in sorted(actual_fields - expected_fields)),
    ]


def _is_receipt_evidence_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 8 <= len(value) <= 256
        and all(character.isprintable() and not character.isspace() for character in value)
    )


def _matches_exactly(actual: object, expected: object) -> bool:
    return type(actual) is type(expected) and actual == expected


def _validate_capability_receipt(
    receipt: Mapping[str, Any], settings: Settings, now: datetime
) -> dict[str, object]:
    if not _matches_exactly(
        receipt.get("schema_version"), CAPABILITY_RECEIPT_SCHEMA_VERSION
    ):
        return _check(
            "blocked",
            reason="unsupported_model_capability_receipt_schema",
            required_schema_version=CAPABILITY_RECEIPT_SCHEMA_VERSION,
        )

    invalid_fields = _mapping_shape_errors(receipt, _RECEIPT_FIELDS, "receipt")
    runtime_contract = receipt.get("runtime_contract")
    extraction_contract = receipt.get("extraction_contract")
    verification = receipt.get("verification")
    invalid_fields.extend(
        _mapping_shape_errors(
            runtime_contract, _RUNTIME_CONTRACT_FIELDS, "runtime_contract"
        )
    )
    invalid_fields.extend(
        _mapping_shape_errors(
            extraction_contract,
            _EXTRACTION_CONTRACT_FIELDS,
            "extraction_contract",
        )
    )
    invalid_fields.extend(
        _mapping_shape_errors(verification, _VERIFICATION_FIELDS, "verification")
    )
    model_family = receipt.get("model_family")
    if not isinstance(model_family, str) or not model_family.strip():
        invalid_fields.append("model_family")
    if isinstance(verification, Mapping):
        for field in ("request_id", "response_id"):
            if field in verification and not _is_receipt_evidence_id(verification.get(field)):
                invalid_fields.append(f"verification.{field}")
    if invalid_fields:
        return _check(
            "blocked",
            reason="invalid_model_capability_receipt",
            invalid_fields=sorted(set(invalid_fields)),
        )

    try:
        verified_at = _parse_receipt_time(receipt.get("verified_at"), "verified_at")
        expires_at = _parse_receipt_time(receipt.get("expires_at"), "expires_at")
    except (TypeError, ValueError):
        return _check("blocked", reason="invalid_model_capability_receipt")
    now_utc = _as_utc(now)
    if verified_at > now_utc or expires_at <= now_utc or expires_at <= verified_at:
        return _check("blocked", reason="expired_or_invalid_model_capability_receipt")

    expected = expected_catalogue_capability_contract(settings)
    mismatched: list[str] = []
    for field, expected_value in expected["runtime_contract"].items():
        if not _matches_exactly(runtime_contract.get(field), expected_value):
            mismatched.append(f"runtime_contract.{field}")
    for field, expected_value in expected["extraction_contract"].items():
        if not _matches_exactly(extraction_contract.get(field), expected_value):
            mismatched.append(f"extraction_contract.{field}")
    if verification.get("method") != _LIVE_VERIFICATION_METHOD:
        mismatched.append("verification.method")
    if mismatched:
        return _check(
            "blocked",
            reason="model_capability_receipt_mismatch",
            mismatched_fields=sorted(set(mismatched)),
        )
    return _check(
        "ready",
        model_family=model_family.strip(),
        api_mode=runtime_contract["api_mode"],
        request_path=runtime_contract["request_path"],
        schema_sha256=extraction_contract["schema_sha256"],
        prompt_sha256=extraction_contract["prompt_sha256"],
        verified_at=verified_at.isoformat(),
        expires_at=expires_at.isoformat(),
    )


def _feature(enabled: bool) -> dict[str, object]:
    return _check("ready" if enabled else "disabled")


def run_catalogue_preflight(
    settings: Settings,
    *,
    probes: PreflightProbes = DEFAULT_PROBES,
    now: datetime | None = None,
) -> dict[str, object]:
    """Validate worker readiness without creating a run or calling a model."""

    checked_at = _as_utc(now or datetime.now(UTC))
    checks: dict[str, dict[str, object]] = {}

    database_ready = False
    try:
        probes.database(settings)
        checks["database"] = _check("ready")
        database_ready = True
    except Exception as exc:  # pragma: no cover - exact driver errors vary
        checks["database"] = _probe_failure("database", exc)

    if database_ready:
        try:
            current, expected = probes.migration_heads(settings)
            checks["database_migrations"] = _check(
                "ready" if current == expected else "blocked",
                reason=None if current == expected else "database_migration_heads_mismatch",
                current_heads=sorted(current),
                expected_heads=sorted(expected),
            )
        except Exception as exc:  # pragma: no cover - exact driver errors vary
            checks["database_migrations"] = _probe_failure("database_migrations", exc)
    else:
        checks["database_migrations"] = _check("blocked", reason="database_unavailable")

    try:
        free_bytes = probes.free_disk_bytes()
        minimum = settings.catalogue_worker_min_free_disk_bytes
        checks["disk_capacity"] = _check(
            "ready" if free_bytes >= minimum else "blocked",
            reason=None if free_bytes >= minimum else "insufficient_free_disk",
            free_bytes=free_bytes,
            minimum_bytes=minimum,
        )
    except Exception as exc:  # pragma: no cover - platform errors vary
        checks["disk_capacity"] = _probe_failure("disk_capacity", exc)

    kill_switch_path = settings.catalogue_worker_kill_switch_path
    if not kill_switch_path:
        checks["kill_switch"] = _check(
            "blocked" if settings.catalogue_ai_ingestion_enabled else "disabled",
            reason=(
                "kill_switch_path_required"
                if settings.catalogue_ai_ingestion_enabled
                else None
            ),
        )
    elif not kill_switch_available(kill_switch_path):
        checks["kill_switch"] = _check(
            "blocked",
            reason="kill_switch_parent_unavailable",
        )
    elif kill_switch_active(kill_switch_path):
        checks["kill_switch"] = _check(
            "blocked",
            reason="operator_kill_switch_active",
        )
    else:
        checks["kill_switch"] = _check("ready")

    pilot_budget_violations: list[str] = []
    if settings.catalogue_ai_ingestion_enabled:
        if settings.catalogue_ai_max_candidates_per_run > 25:
            pilot_budget_violations.append("max_candidates_exceeds_verified_batch_size")
        if settings.catalogue_ai_max_pages_per_candidate > MAX_ACCEPTED_ARTIFACTS:
            pilot_budget_violations.append("max_pages_exceeds_acquisition_bound")
        minimum_calls = settings.catalogue_ai_max_candidates_per_run * len(ClaimObjective)
        maximum_calls = (
            settings.catalogue_ai_max_candidates_per_run
            * settings.catalogue_ai_max_pages_per_candidate
            * len(ClaimObjective)
        )
        if settings.catalogue_ai_max_calls_per_run < minimum_calls:
            pilot_budget_violations.append("max_model_calls_cannot_cover_all_objectives")
        if settings.catalogue_ai_max_calls_per_run > maximum_calls:
            pilot_budget_violations.append("max_model_calls_exceeds_source_objective_bound")
        # Provider-internal retries are not independently reservable yet. The
        # first paid pilot therefore fails closed at zero automatic retries.
        if settings.catalogue_ai_max_retries != 0:
            pilot_budget_violations.append("automatic_provider_retries_must_be_zero")
    checks["run_budgets"] = _check(
        "blocked" if pilot_budget_violations else "ready",
        reason="unsafe_catalogue_run_budget" if pilot_budget_violations else None,
        violations=pilot_budget_violations,
        max_candidates=settings.catalogue_ai_max_candidates_per_run,
        max_pages_per_candidate=settings.catalogue_ai_max_pages_per_candidate,
        max_model_calls=settings.catalogue_ai_max_calls_per_run,
        max_provider_retries=settings.catalogue_ai_max_retries,
        max_input_characters=settings.catalogue_ai_max_input_characters,
        max_output_tokens=settings.catalogue_ai_max_output_tokens,
        max_estimated_cost=str(settings.catalogue_ai_max_estimated_cost_per_run),
    )

    if settings.catalogue_worker_health_required:
        if not database_ready:
            checks["catalogue_worker"] = _check("blocked", reason="database_unavailable")
        else:
            try:
                health = probes.worker_health(settings)
                completed_at = (
                    _as_utc(health.completed_at) if health and health.completed_at else None
                )
                max_age = timedelta(seconds=max(60, settings.catalogue_worker_poll_seconds * 3))
                fresh = bool(
                    health
                    and completed_at
                    and completed_at >= checked_at - max_age
                    and not health.error_code
                )
                checks["catalogue_worker"] = _check(
                    "ready" if fresh else "blocked",
                    reason=None if fresh else "catalogue_worker_stale_or_failed",
                    last_completed_at=completed_at.isoformat() if completed_at else None,
                    error_code=health.error_code if health else None,
                )
            except Exception as exc:  # pragma: no cover - exact driver errors vary
                checks["catalogue_worker"] = _probe_failure("catalogue_worker", exc)
    else:
        checks["catalogue_worker"] = _check("disabled")

    checks["ai_ingestion"] = _feature(settings.catalogue_ai_ingestion_enabled)
    if settings.catalogue_ai_ingestion_enabled:
        pricing_ready = (
            settings.catalogue_ai_input_cost_per_million > 0
            and settings.catalogue_ai_output_cost_per_million > 0
            and settings.catalogue_ai_max_estimated_cost_per_run > 0
        )
        checks["ai_pricing"] = _check(
            "ready" if pricing_ready else "blocked",
            reason=None if pricing_ready else "explicit_positive_ai_pricing_required",
            input_per_million=str(settings.catalogue_ai_input_cost_per_million),
            output_per_million=str(settings.catalogue_ai_output_cost_per_million),
        )
        try:
            probes.azure_credential(settings)
            checks["azure_credential"] = _check("ready", provider="DefaultAzureCredential")
        except Exception as exc:
            checks["azure_credential"] = _probe_failure("azure_credential", exc)

        receipt_path = settings.catalogue_ai_capability_receipt_path
        if not receipt_path:
            checks["model_capability"] = _check(
                "blocked", reason="model_capability_receipt_required"
            )
        else:
            try:
                receipt = probes.capability_receipt(Path(receipt_path))
                checks["model_capability"] = _validate_capability_receipt(
                    receipt, settings, checked_at
                )
            except Exception as exc:
                checks["model_capability"] = _probe_failure("model_capability_receipt", exc)
    else:
        checks["ai_pricing"] = _check("disabled")
        checks["azure_credential"] = _check("disabled")
        checks["model_capability"] = _check("disabled")

    checks["bounded_crawling"] = _feature(settings.catalogue_bounded_crawling_enabled)
    checks["crawlee_static"] = _feature(settings.catalogue_crawlee_static_enabled)
    if settings.catalogue_crawlee_static_enabled:
        try:
            available = probes.crawlee_available()
            checks["crawlee_runtime"] = _check(
                "ready" if available else "blocked",
                reason=None if available else "crawlee_not_installed",
            )
        except Exception as exc:  # pragma: no cover - import system errors vary
            checks["crawlee_runtime"] = _probe_failure("crawlee_runtime", exc)
    else:
        checks["crawlee_runtime"] = _check("disabled")

    checks["browser_fetching"] = _feature(settings.catalogue_browser_fetching_enabled)
    if settings.catalogue_browser_fetching_enabled:
        try:
            browser_available = probes.browser_available()
            checks["browser_runtime"] = _check(
                "ready" if browser_available else "blocked",
                reason=None if browser_available else "playwright_chromium_not_installed",
            )
        except Exception as exc:  # pragma: no cover - browser runtime errors vary
            checks["browser_runtime"] = _probe_failure("browser_runtime", exc)
    else:
        checks["browser_runtime"] = _check("disabled")

    checks["document_conversion"] = _feature(settings.catalogue_document_intelligence_enabled)
    if (
        settings.catalogue_document_ocr_enabled
        and not settings.catalogue_document_intelligence_enabled
    ):
        checks["document_ocr"] = _check("blocked", reason="document_conversion_required_for_ocr")
    else:
        checks["document_ocr"] = _feature(settings.catalogue_document_ocr_enabled)
    if settings.catalogue_document_intelligence_enabled:
        try:
            document_ready = probes.document_worker_ready(settings, checked_at)
            checks["document_worker"] = _check(
                "ready" if document_ready else "blocked",
                reason=None if document_ready else "document_worker_transport_stale_or_unavailable",
            )
        except Exception as exc:  # pragma: no cover - filesystem errors vary
            checks["document_worker"] = _probe_failure("document_worker", exc)
    else:
        checks["document_worker"] = _check("disabled")

    checks["source_routing"] = _feature(settings.catalogue_source_routing_enabled)

    first_pilot_disabled = {
        "web_discovery": settings.catalogue_web_discovery_enabled,
        "scheduled_ingestion": settings.catalogue_scheduled_ingestion_enabled,
        "graph_reads": settings.catalogue_graph_reads_enabled,
        "graph_writes": settings.catalogue_graph_writes_enabled,
    }
    for name, enabled in first_pilot_disabled.items():
        checks[name] = (
            _check("blocked", reason="capability_must_remain_disabled_for_first_pilot")
            if enabled
            else _check("disabled")
        )
    checks["publication"] = _check("disabled", reason="manual_admin_action_only")

    ready = all(check["status"] in {"ready", "disabled"} for check in checks.values())
    return {
        "status": "ready" if ready else "blocked",
        "checked_at": checked_at.isoformat(),
        "side_effects": "read_only_no_ingestion_or_model_calls",
        "checks": checks,
    }


__all__ = [
    "DEFAULT_PROBES",
    "PreflightProbes",
    "WorkerHealthSnapshot",
    "run_catalogue_preflight",
]
