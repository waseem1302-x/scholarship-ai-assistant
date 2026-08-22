"""Strict-output provider for one source at a time in direct URL acquisition."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.modules.catalogue_ingestion.claim_schemas import ClaimExtractionOutput
from app.modules.catalogue_ingestion.provider import (
    ExtractionProviderError,
    ExtractionProviderTimeout,
    ExtractionProviderUnavailable,
    ExtractionSchemaError,
    estimate_cost,
)
from app.modules.catalogue_ingestion.schemas import ExtractionUsage

CLAIM_SYSTEM_INSTRUCTION = """Extract atomic scholarship claims only from this one official source.
Never use general knowledge or transfer a fact between application routes. Every claim must contain
the exact character offsets and verbatim excerpt from SOURCE TEXT. Use stable snake_case keys.
For MEXT, represent one scholarship; use embassy_recommendation and university_recommendation as
top-level track keys when explicit. Put cycle, track, institution, and programme keys in scope.
Unknown facts belong in unknown_objectives. Report contradictions; do not reconcile them."""


class ClaimExtractionResult(BaseModel):
    output: ClaimExtractionOutput
    usage: ExtractionUsage


class CatalogueClaimProvider(Protocol):
    name: str
    model: str

    def extract_claims(self, *, source_url: str, source_text: str) -> ClaimExtractionResult: ...


class UnavailableClaimProvider:
    name = "unavailable"

    def __init__(self, model: str) -> None:
        self.model = model

    def extract_claims(self, *, source_url: str, source_text: str) -> ClaimExtractionResult:
        del source_url, source_text
        raise ExtractionProviderUnavailable("Catalogue claim extraction is disabled")


class FakeClaimProvider:
    name = "fake_claims"

    def __init__(
        self,
        output: ClaimExtractionOutput | Callable[[str, str], ClaimExtractionOutput],
        *,
        model: str = "fake-catalogue-claims-v2",
    ) -> None:
        self.output = output
        self.model = model
        self.calls = 0

    def extract_claims(self, *, source_url: str, source_text: str) -> ClaimExtractionResult:
        self.calls += 1
        output = self.output(source_url, source_text) if callable(self.output) else self.output
        return ClaimExtractionResult(
            output=output,
            usage=ExtractionUsage(
                input_tokens=max(1, len(source_text) // 4),
                output_tokens=max(1, len(output.model_dump_json()) // 4),
                latency_ms=1,
            ),
        )


class AzureOpenAIClaimProvider:
    name = "azure_openai"

    def __init__(
        self,
        settings: Settings,
        *,
        credential: Any | None = None,
        opener: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not settings.catalogue_ai_endpoint or not settings.catalogue_ai_model:
            raise ExtractionProviderUnavailable("Azure catalogue extraction is not configured")
        self.settings = settings
        self.model = settings.catalogue_ai_model
        self.credential = credential or self._default_credential()
        self.opener = opener or urllib.request.build_opener()
        self.sleeper = sleeper

    @staticmethod
    def _default_credential() -> Any:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ExtractionProviderUnavailable("Azure Identity dependency is unavailable") from exc
        return DefaultAzureCredential()

    def extract_claims(self, *, source_url: str, source_text: str) -> ClaimExtractionResult:
        bounded = source_text[: self.settings.catalogue_ai_max_input_characters]
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CLAIM_SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": f"OFFICIAL SOURCE URL: {source_url}\n\nSOURCE TEXT:\n{bounded}",
                },
            ],
            "max_completion_tokens": self.settings.catalogue_ai_max_output_tokens,
            "reasoning_effort": "minimal",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "catalogue_claim_extraction",
                    "strict": True,
                    "schema": _azure_schema(ClaimExtractionOutput),
                },
            },
        }
        request_body = json.dumps(body, separators=(",", ":")).encode()
        endpoint = self.settings.catalogue_ai_endpoint.rstrip("/")
        started = time.perf_counter()
        last_error: BaseException | None = None
        for attempt in range(self.settings.catalogue_ai_max_retries + 1):
            try:
                token = self.credential.get_token(self.settings.catalogue_ai_token_scope).token
                request = urllib.request.Request(
                    f"{endpoint}/openai/v1/chat/completions",
                    data=request_body,
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "User-Agent": "ScholarshipAI-Catalogue/0.1",
                    },
                )
                with self.opener.open(
                    request, timeout=self.settings.catalogue_ai_timeout_seconds
                ) as response:
                    raw = response.read(self.settings.catalogue_ai_max_response_bytes + 1)
                if len(raw) > self.settings.catalogue_ai_max_response_bytes:
                    raise ExtractionSchemaError("AI response exceeded the configured byte limit")
                return self._parse(raw, started)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
            if attempt < self.settings.catalogue_ai_max_retries:
                self.sleeper(min(2**attempt, 4))
        if isinstance(last_error, TimeoutError):
            raise ExtractionProviderTimeout("Azure claim extraction timed out") from last_error
        raise ExtractionProviderError("Azure claim extraction request failed") from last_error

    def _parse(self, raw: bytes, started: float) -> ClaimExtractionResult:
        usage: ExtractionUsage | None = None
        try:
            response = json.loads(raw)
            usage_data = response["usage"]
            usage = ExtractionUsage(
                input_tokens=int(usage_data["prompt_tokens"]),
                output_tokens=int(usage_data["completion_tokens"]),
                estimated_cost=estimate_cost(
                    int(usage_data["prompt_tokens"]),
                    int(usage_data["completion_tokens"]),
                    input_per_million=self.settings.catalogue_ai_input_cost_per_million,
                    output_per_million=self.settings.catalogue_ai_output_cost_per_million,
                ),
                latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
            message = response["choices"][0]["message"]
            if message.get("refusal"):
                raise ExtractionSchemaError("Model refused the claim extraction", usage=usage)
            output = ClaimExtractionOutput.model_validate_json(message["content"])
        except ExtractionSchemaError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise ExtractionSchemaError(
                "Azure claim response did not match the strict schema", usage=usage
            ) from exc
        return ClaimExtractionResult(output=output, usage=usage)


def get_claim_provider(settings: Settings) -> CatalogueClaimProvider:
    if not settings.catalogue_ai_ingestion_enabled:
        return UnavailableClaimProvider(settings.catalogue_ai_model or "disabled")
    return AzureOpenAIClaimProvider(settings)


def _azure_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    unsupported = {
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
    }

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"title", "default"} or key in unsupported:
                    continue
                if key in {"properties", "$defs"} and isinstance(item, dict):
                    cleaned[key] = {
                        name: normalize(child_schema) for name, child_schema in item.items()
                    }
                else:
                    cleaned[key] = normalize(item)
            if cleaned.get("type") == "object" or "properties" in cleaned:
                properties = cleaned.get("properties", {})
                cleaned["additionalProperties"] = False
                cleaned["required"] = list(properties)
            return cleaned
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(schema)
