"""One-shot Azure OpenAI capability probe with sanitized durable evidence."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.modules.catalogue_ingestion.ai_contract import azure_openai_request_url
from app.modules.catalogue_ingestion.claim_provider import (
    CLAIM_SYSTEM_INSTRUCTION,
    OBJECTIVE_INSTRUCTIONS,
    _objective_azure_schema,
)
from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimExtractionOutput,
    ClaimObjective,
)
from app.modules.catalogue_ingestion.preflight import (
    expected_catalogue_capability_contract,
)
from app.modules.catalogue_ingestion.provider import estimate_cost

CAPABILITY_PROBE_EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_CAPABILITY_OBJECTIVE = ClaimObjective.DOCUMENTS_CORE
DEFAULT_CAPABILITY_SOURCE_TEXT = "Capability test source contains no scholarship facts."
DEFAULT_CAPABILITY_SOURCE_URL = "https://example.invalid/capability-test"


@dataclass(frozen=True)
class CapabilityProbePlan:
    request_url: str
    payload: bytes
    objective: ClaimObjective
    max_completion_tokens: int
    max_estimated_cost_usd: Decimal
    byte_upper_bound_cost_usd: Decimal


@dataclass(frozen=True)
class CapabilityProbeOutcome:
    evidence: dict[str, object]
    receipt: dict[str, object] | None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _raw_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    input_per_million: Decimal,
    output_per_million: Decimal,
) -> Decimal:
    return (
        Decimal(input_tokens) * input_per_million
        + Decimal(output_tokens) * output_per_million
    ) / Decimal(1_000_000)


def build_capability_probe_plan(
    settings: Settings,
    *,
    objective: ClaimObjective = DEFAULT_CAPABILITY_OBJECTIVE,
    max_completion_tokens: int = 4_096,
    max_estimated_cost_usd: Decimal = Decimal("0.01"),
) -> CapabilityProbePlan:
    """Build the smallest real objective request that retains production contracts."""

    if settings.catalogue_ai_provider != "azure_openai":
        raise ValueError("capability_probe_requires_azure_openai")
    if not settings.catalogue_ai_endpoint or settings.catalogue_ai_model == "unconfigured":
        raise ValueError("capability_probe_route_not_configured")
    if settings.catalogue_ai_max_retries != 0:
        raise ValueError("capability_probe_requires_zero_retries")
    if (
        settings.catalogue_ai_input_cost_per_million <= 0
        or settings.catalogue_ai_output_cost_per_million <= 0
    ):
        raise ValueError("capability_probe_requires_positive_pricing")
    if max_completion_tokens < 256:
        raise ValueError("capability_probe_completion_limit_too_small")

    instruction = (
        f"{CLAIM_SYSTEM_INSTRUCTION}\n\n{OBJECTIVE_INSTRUCTIONS[objective]}"
    )
    body = {
        "model": settings.catalogue_ai_model,
        "messages": [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": (
                    f"OFFICIAL SOURCE URL: {DEFAULT_CAPABILITY_SOURCE_URL}\n"
                    f"OBJECTIVE: {objective.value}\n"
                    "RESOURCE LINKS: []\n"
                    "Whitespace-only gaps in SOURCE TEXT are deliberately omitted regions; "
                    "character positions are preserved.\n\n"
                    f"SOURCE TEXT:\n{DEFAULT_CAPABILITY_SOURCE_TEXT}"
                ),
            },
        ],
        "max_completion_tokens": max_completion_tokens,
        "reasoning_effort": "minimal",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "catalogue_claim_extraction",
                "strict": True,
                "schema": _objective_azure_schema(objective),
            },
        },
    }
    payload = json.dumps(body, separators=(",", ":")).encode()
    # A tokenizer cannot emit more tokens than the UTF-8 byte count. This is
    # deliberately more conservative than a chars/4 estimate.
    upper_bound = _raw_cost(
        len(payload),
        max_completion_tokens,
        input_per_million=settings.catalogue_ai_input_cost_per_million,
        output_per_million=settings.catalogue_ai_output_cost_per_million,
    )
    if upper_bound > max_estimated_cost_usd:
        raise ValueError("capability_probe_cost_bound_exceeded")
    return CapabilityProbePlan(
        request_url=azure_openai_request_url(settings.catalogue_ai_endpoint),
        payload=payload,
        objective=objective,
        max_completion_tokens=max_completion_tokens,
        max_estimated_cost_usd=max_estimated_cost_usd,
        byte_upper_bound_cost_usd=upper_bound,
    )


def _provider_request_id(headers: Any) -> str | None:
    if headers is None:
        return None
    for name in ("apim-request-id", "x-request-id", "x-ms-request-id"):
        value = headers.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _content_filter_triggered(value: object) -> bool:
    if isinstance(value, Mapping):
        if value.get("filtered") is True:
            return True
        return any(_content_filter_triggered(item) for item in value.values())
    if isinstance(value, list):
        return any(_content_filter_triggered(item) for item in value)
    return False


def _usage_metadata(
    payload: Mapping[str, Any], settings: Settings
) -> dict[str, object] | None:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return None
    try:
        input_tokens = int(usage["prompt_tokens"])
        output_tokens = int(usage["completion_tokens"])
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))
    except (KeyError, TypeError, ValueError):
        return None
    if min(input_tokens, output_tokens, total_tokens) < 0:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": str(
            estimate_cost(
                input_tokens,
                output_tokens,
                input_per_million=settings.catalogue_ai_input_cost_per_million,
                output_per_million=settings.catalogue_ai_output_cost_per_million,
            )
        ),
    }


def _base_evidence(
    settings: Settings,
    plan: CapabilityProbePlan,
    *,
    client_request_id: str,
    observed_at: datetime,
) -> dict[str, object]:
    return {
        "schema_version": CAPABILITY_PROBE_EVIDENCE_SCHEMA_VERSION,
        "status": "failed",
        "failure_category": "not_started",
        "runtime_contract": expected_catalogue_capability_contract(settings)[
            "runtime_contract"
        ],
        "probe_contract": {
            "objective": plan.objective.value,
            "response_format_name": "catalogue_claim_extraction",
            "strict_json_schema": True,
            "request_bytes": len(plan.payload),
            "input_token_upper_bound": len(plan.payload),
            "max_completion_tokens": plan.max_completion_tokens,
            "max_estimated_cost_usd": str(plan.max_estimated_cost_usd),
            "byte_upper_bound_cost_usd": str(plan.byte_upper_bound_cost_usd),
            "automatic_retries": 0,
        },
        "request": {
            "count": 0,
            "client_request_id": client_request_id,
            "provider_request_id": None,
        },
        "response": {
            "http_status": None,
            "response_id": None,
            "model": None,
            "finish_reason": None,
            "refusal_present": None,
            "content_filter_triggered": None,
        },
        "usage": None,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
    }


def run_capability_probe(
    settings: Settings,
    *,
    objective: ClaimObjective = DEFAULT_CAPABILITY_OBJECTIVE,
    max_completion_tokens: int = 4_096,
    max_estimated_cost_usd: Decimal = Decimal("0.01"),
    credential: Any | None = None,
    opener: Any | None = None,
    now: Callable[[], datetime] | None = None,
    request_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
) -> CapabilityProbeOutcome:
    """Make exactly one provider request and retain only sanitized metadata."""

    plan = build_capability_probe_plan(
        settings,
        objective=objective,
        max_completion_tokens=max_completion_tokens,
        max_estimated_cost_usd=max_estimated_cost_usd,
    )
    observed_at = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
    client_request_id = str(request_id_factory())
    evidence = _base_evidence(
        settings,
        plan,
        client_request_id=client_request_id,
        observed_at=observed_at,
    )
    request_metadata = evidence["request"]
    response_metadata = evidence["response"]
    assert isinstance(request_metadata, dict)
    assert isinstance(response_metadata, dict)

    owns_credential = credential is None
    if credential is None:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
    opener = opener or urllib.request.build_opener(_NoRedirect())
    try:
        try:
            token = credential.get_token(settings.catalogue_ai_token_scope).token
        except Exception:
            evidence["failure_category"] = "credential"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)

        request = urllib.request.Request(
            plan.request_url,
            data=plan.payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "ScholarshipAI-Catalogue-Capability/0.2",
                "x-ms-client-request-id": client_request_id,
            },
        )
        request_metadata["count"] = 1
        try:
            started = time.perf_counter()
            with opener.open(request, timeout=settings.catalogue_ai_timeout_seconds) as response:
                response_metadata["http_status"] = getattr(response, "status", 200)
                request_metadata["provider_request_id"] = _provider_request_id(
                    getattr(response, "headers", None)
                )
                raw = response.read(settings.catalogue_ai_max_response_bytes + 1)
            response_metadata["latency_ms"] = max(
                0, int((time.perf_counter() - started) * 1_000)
            )
        except urllib.error.HTTPError as exc:
            response_metadata["http_status"] = exc.code
            request_metadata["provider_request_id"] = _provider_request_id(exc.headers)
            evidence["failure_category"] = "http_error"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        except (TimeoutError, urllib.error.URLError):
            evidence["failure_category"] = "transport"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)

        if len(raw) > settings.catalogue_ai_max_response_bytes:
            evidence["failure_category"] = "response_too_large"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence["failure_category"] = "malformed_output"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if not isinstance(payload, dict):
            evidence["failure_category"] = "malformed_output"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)

        response_id = payload.get("id")
        response_model = payload.get("model")
        response_metadata["response_id"] = (
            response_id.strip()
            if isinstance(response_id, str) and response_id.strip()
            else None
        )
        response_metadata["model"] = (
            response_model.strip()
            if isinstance(response_model, str) and response_model.strip()
            else None
        )
        evidence["usage"] = _usage_metadata(payload, settings)
        choices = payload.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, Mapping) else None
        finish_reason = choice.get("finish_reason") if isinstance(choice, Mapping) else None
        response_metadata["finish_reason"] = (
            finish_reason if isinstance(finish_reason, str) else None
        )
        refusal = message.get("refusal") if isinstance(message, Mapping) else None
        response_metadata["refusal_present"] = refusal not in {None, ""}
        response_metadata["content_filter_triggered"] = (
            finish_reason == "content_filter" or _content_filter_triggered(payload)
        )

        if response_metadata["content_filter_triggered"]:
            evidence["failure_category"] = "content_filter"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if response_metadata["refusal_present"]:
            evidence["failure_category"] = "refusal"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if finish_reason == "length":
            evidence["failure_category"] = "length"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if finish_reason != "stop":
            evidence["failure_category"] = "incomplete"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if response_metadata["response_id"] is None:
            evidence["failure_category"] = "response_id_missing"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if not isinstance(response_model, str) or "gpt-5-mini" not in response_model:
            evidence["failure_category"] = "model_mismatch"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            evidence["failure_category"] = "parser_contract"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        try:
            parsed = ClaimExtractionOutput.model_validate_json(message["content"])
        except (TypeError, ValueError):
            evidence["failure_category"] = "parser_contract"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if parsed.objective is not objective:
            evidence["failure_category"] = "parser_contract"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)

        usage = evidence["usage"]
        if not isinstance(usage, Mapping):
            evidence["failure_category"] = "usage_missing"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)
        if Decimal(str(usage["estimated_cost_usd"])) > max_estimated_cost_usd:
            evidence["failure_category"] = "cost_bound_exceeded"
            return CapabilityProbeOutcome(evidence=evidence, receipt=None)

        provider_request_id = request_metadata["provider_request_id"]
        receipt_request_id = (
            provider_request_id
            if isinstance(provider_request_id, str) and provider_request_id
            else client_request_id
        )
        receipt = {
            **expected_catalogue_capability_contract(settings),
            "model_family": "gpt-5-mini",
            "verification": {
                "method": "live_strict_json_schema_request",
                "request_id": receipt_request_id,
                "response_id": response_metadata["response_id"],
            },
            "verified_at": observed_at.isoformat().replace("+00:00", "Z"),
            "expires_at": (observed_at + timedelta(days=7)).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        evidence["status"] = "succeeded"
        evidence["failure_category"] = None
        return CapabilityProbeOutcome(evidence=evidence, receipt=receipt)
    finally:
        if owns_credential:
            close = getattr(credential, "close", None)
            if callable(close):
                close()


def _sanitize_evidence(evidence: dict[str, object]) -> dict[str, object]:
    """Return a sanitized copy of the evidence with any raw prompt/response bodies removed.

    Keeps required metadata (request/provider ids, finish_reason, refusal flags, and usage)
    but strips any fields that may contain raw messages, payloads, or tokens.
    """
    sanitized: dict[str, object] = {}
    sensitive_top_keys = {
        "request_payload",
        "request_body",
        "response_payload",
        "response_body",
        "raw_request",
        "raw_response",
        "prompt",
        "messages",
        "content",
    }
    for k, v in evidence.items():
        if k in sensitive_top_keys:
            continue
        if k in ("request", "response") and isinstance(v, dict):
            sub: dict[str, object] = {}
            for sk, sv in v.items():
                if sk in {"payload", "body", "raw", "message", "messages", "content"}:
                    continue
                sub[sk] = sv
            sanitized[k] = sub
        else:
            sanitized[k] = v
    return sanitized
def _atomic_json_write(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary_name)
        raise



def persist_capability_probe_outcome(
    outcome: CapabilityProbeOutcome,
    *,
    evidence_path: Path,
    receipt_path: Path,
) -> None:
    """Persist sanitized evidence always and a v2 receipt only on success.

    The evidence is sanitized to remove any raw prompt/response bodies or tokens before
    durable persistence. If a local operator receipt directory `.catalogue-local/` exists,
    a secondary copy is also written there for durable inspection. This secondary write is
    best-effort and will not raise on failure.
    """

    sanitized = _sanitize_evidence(outcome.evidence)
    _atomic_json_write(evidence_path, sanitized)

    # Best-effort: also write a copy into the ignored local receipt directory if present.
    default_dir = Path(".catalogue-local")
    try:
        if default_dir.exists() and default_dir.is_dir():
            _atomic_json_write(default_dir / "capability-probe-evidence.json", sanitized)
    except Exception:
        # Do not fail the main persist if the optional secondary write fails
        pass

    if outcome.receipt is not None:
        _atomic_json_write(receipt_path, outcome.receipt)
__all__ = [
    "CAPABILITY_PROBE_EVIDENCE_SCHEMA_VERSION",
    "CapabilityProbeOutcome",
    "CapabilityProbePlan",
    "build_capability_probe_plan",
    "persist_capability_probe_outcome",
    "run_capability_probe",
]



