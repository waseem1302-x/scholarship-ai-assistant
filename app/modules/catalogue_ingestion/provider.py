"""Configurable strict-output extraction provider; catalogue facts never bypass validation."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from app.core.config import Settings
from app.modules.catalogue_ingestion.schemas import (
    CatalogueExtractionOutput,
    ExtractionResult,
    ExtractionUsage,
)

SYSTEM_INSTRUCTION = """You extract scholarship facts only from the supplied official-source text.
Return null/unknown when the text does not explicitly support a value. Never use general knowledge.
Every non-null decision-critical value must have field-level evidence whose excerpt appears verbatim
in the supplied text. Normalization may standardize an explicit value but must be marked normalized.
Report conflicts and warnings; do not resolve conflicting official statements silently."""


class ExtractionProviderError(RuntimeError):
    code = "ai_extraction_failed"


class ExtractionProviderUnavailable(ExtractionProviderError):
    code = "ai_provider_unavailable"


class ExtractionProviderTimeout(ExtractionProviderError):
    code = "ai_provider_timeout"


class ExtractionSchemaError(ExtractionProviderError):
    code = "ai_schema_failed"


class CatalogueExtractionProvider(Protocol):
    name: str
    model: str

    def extract(self, *, source_url: str, source_text: str) -> ExtractionResult: ...


class UnavailableExtractionProvider:
    name = "unavailable"

    def __init__(self, model: str) -> None:
        self.model = model

    def extract(self, *, source_url: str, source_text: str) -> ExtractionResult:
        del source_url, source_text
        raise ExtractionProviderUnavailable("Catalogue AI extraction is disabled")


class FakeExtractionProvider:
    name = "fake"

    def __init__(
        self,
        output: CatalogueExtractionOutput | Callable[[str, str], CatalogueExtractionOutput],
        *,
        model: str = "fake-catalogue-v1",
    ) -> None:
        self.output = output
        self.model = model
        self.calls = 0

    def extract(self, *, source_url: str, source_text: str) -> ExtractionResult:
        self.calls += 1
        output = self.output(source_url, source_text) if callable(self.output) else self.output
        return ExtractionResult(
            output=output,
            usage=ExtractionUsage(
                input_tokens=max(1, len(source_text) // 4),
                output_tokens=max(1, len(output.model_dump_json()) // 4),
                latency_ms=1,
            ),
        )


class AzureOpenAIExtractionProvider:
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

    def extract(self, *, source_url: str, source_text: str) -> ExtractionResult:
        bounded_text = source_text[: self.settings.catalogue_ai_max_input_characters]
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": f"OFFICIAL SOURCE URL: {source_url}\n\nSOURCE TEXT:\n{bounded_text}",
                },
            ],
            "max_completion_tokens": self.settings.catalogue_ai_max_output_tokens,
            "reasoning_effort": "minimal",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "catalogue_extraction",
                    "strict": True,
                    "schema": azure_structured_output_schema(),
                },
            },
        }
        payload = json.dumps(body, separators=(",", ":")).encode()
        endpoint = self.settings.catalogue_ai_endpoint.rstrip("/")
        url = f"{endpoint}/openai/v1/chat/completions"
        started = time.perf_counter()
        last_error: BaseException | None = None
        for attempt in range(self.settings.catalogue_ai_max_retries + 1):
            try:
                token = self.credential.get_token(self.settings.catalogue_ai_token_scope).token
                request = urllib.request.Request(
                    url,
                    data=payload,
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
                return self._parse_response(raw, started)
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            if attempt < self.settings.catalogue_ai_max_retries:
                self.sleeper(min(2**attempt, 4))
        if isinstance(last_error, TimeoutError):
            raise ExtractionProviderTimeout("Azure extraction timed out") from last_error
        raise ExtractionProviderError("Azure extraction request failed") from last_error

    def _parse_response(self, raw: bytes, started: float) -> ExtractionResult:
        try:
            response = json.loads(raw)
            message = response["choices"][0]["message"]
            if message.get("refusal"):
                raise ExtractionSchemaError("Model refused the extraction request")
            output = CatalogueExtractionOutput.model_validate_json(message["content"])
            usage = response.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
        except ExtractionSchemaError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ExtractionSchemaError("Azure response did not match the strict schema") from exc
        return ExtractionResult(
            output=output,
            usage=ExtractionUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimate_cost(
                    input_tokens,
                    output_tokens,
                    input_per_million=self.settings.catalogue_ai_input_cost_per_million,
                    output_per_million=self.settings.catalogue_ai_output_cost_per_million,
                ),
                latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            ),
        )


def azure_structured_output_schema() -> dict[str, Any]:
    """Return the Pydantic contract with Azure's strict required-property convention."""

    schema = CatalogueExtractionOutput.model_json_schema()

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned = {
                key: normalize(item)
                for key, item in value.items()
                if key not in {"title", "default"}
            }
            if cleaned.get("type") == "object" or "properties" in cleaned:
                properties = cleaned.get("properties", {})
                cleaned["additionalProperties"] = False
                cleaned["required"] = list(properties)
            return cleaned
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(schema)


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    input_per_million: Decimal,
    output_per_million: Decimal,
) -> Decimal:
    cost = (
        Decimal(input_tokens) * input_per_million + Decimal(output_tokens) * output_per_million
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


def extraction_prompt_hash() -> str:
    return hashlib.sha256(SYSTEM_INSTRUCTION.encode()).hexdigest()


def get_extraction_provider(settings: Settings) -> CatalogueExtractionProvider:
    if not settings.catalogue_ai_ingestion_enabled:
        return UnavailableExtractionProvider(settings.catalogue_ai_model)
    if settings.catalogue_ai_provider == "azure_openai":
        return AzureOpenAIExtractionProvider(settings)
    return UnavailableExtractionProvider(settings.catalogue_ai_model)
