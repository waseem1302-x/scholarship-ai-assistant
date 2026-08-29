"""Configurable strict-output extraction provider; catalogue facts never bypass validation."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from pydantic import ValidationError

from app.core.config import Settings
from app.modules.catalogue_ingestion.provider_transport import (
    ExtractionProviderConnectionError,
    ExtractionProviderError,
    ExtractionProviderRateLimited,
    ExtractionProviderResponseInterrupted,
    ExtractionProviderServerError,
    ExtractionProviderTimeout,
    ExtractionProviderUnavailable,
    ExtractionSchemaError,
    extraction_retry_delay,
    send_json_request,
)
from app.modules.catalogue_ingestion.schemas import (
    CatalogueExtractionOutput,
    ExtractionResult,
    ExtractionUsage,
)

SYSTEM_INSTRUCTION = """You extract scholarship facts only from the supplied official-source text.
Return null/unknown when the text does not explicitly support a value. Never use general knowledge.
Every non-null decision-critical value must have field-level evidence whose excerpt appears verbatim
in the supplied text. Normalization may standardize an explicit value but must be marked normalized.

Identity semantics:
- identity.name is the most specific explicit scholarship or programme title
  supported by the source.
  Prefer the exact scholarship or programme heading in the content when one is present.
  Do not singularize or pluralize that heading, and do not drop leading official tokens
  such as "SI" or "The". Use a shorter browser or navigation title only when no more
  specific scholarship heading exists.
- identity.provider_name is the organisation the source explicitly identifies as responsible for
  awarding, providing, funding, sponsoring, administering, owning, or developing the scholarship
  programme. A website publisher, portal, host, or site brand is not automatically the provider when
  the source explicitly identifies another responsible organisation.
- identity.country is the scholarship's destination or host study country, not an applicant's
  nationality or country of origin. Explicit statements that recipients study, attend courses, or
  enroll at universities in a country support that destination country. The country itself must be
  explicit in the supplied text. Never infer it from a university name, city, provider, URL,
  internet domain, language, currency, or general geographic knowledge.

Funding coverage status semantics:
- confirmed: the official source explicitly confirms that the benefit exists. A fixed grant,
  allowance, contribution, transportation benefit, insurance benefit, or other explicitly included
  benefit is confirmed even when it may not cover every real-world expense.
- partial: use only when the official source explicitly says that a defined benefit or charge is
  only partly covered, percentage-covered, capped as partial coverage, or otherwise explicitly
  describes the coverage itself as partial. Do not use partial merely because a grant is fixed,
  one-time, described as a contribution, or may be smaller than the recipient's total expenses.
- not_covered: use only when the official source explicitly states that the benefit, cost, or charge
  is excluded, not paid, or not covered.
- unknown: use when the supplied source does not establish either coverage or explicit non-coverage.
  Absence of a benefit from the page must never be converted into not_covered.

For every funding coverage status other than unknown, provide field-level evidence for the exact
coverage-status field using a verbatim source excerpt.

Field-specific funding rules:
- funding.monthly_stipend_amount and funding.monthly_stipend_currency may be populated only when
  the source explicitly describes a recurring monthly or per-month stipend or allowance. Do not
  map an overall scholarship value, annual amount, lump sum, one-time grant, instalment total, or
  general living-cost contribution into the monthly stipend fields.
- funding.tuition_coverage_status may be confirmed or not_covered only when the source explicitly
  establishes tuition or tuition-fee coverage or non-coverage. "Full scholarship",
  "participation costs", generic costs, or generic fees alone do not establish tuition coverage.

For identity.provider_name, inspect authoritative scholarship content, organisation statements,
programme headings, and official identity text. Prefer an organisation explicitly described as
responsible for the scholarship over the website or publishing platform that hosts the page.
When an awarding, providing, funding, sponsoring, administering, or developing statement names
the responsible organisation, prefer the organisation wording from that evidence. Do not append
an acronym, translated label, or alternate site-brand wording that is absent from that evidence.

Create eligibility.rules only for explicit applicant eligibility requirements or mandatory
conditions stated by the official source. Do not convert descriptive programme characteristics,
typical or majority patterns, preferences, benefits, target audiences, or qualified wording such as
"mostly", "typically", "usually", or "preferred" into eligibility rules. Such information may be
represented in the appropriate descriptive field or warning when supported, but must not become a
structured eligibility rule unless the source clearly states it as an eligibility requirement.

For eligibility.minimum_academic_requirement, populate a value only when the source states an
explicit required prior qualification or academic threshold, such as a required degree, grade,
percentage, GPA, or equivalent academic condition. Labels such as "graduates", "students",
"professionals", target groups, eligible programme types, or descriptions of the degree being
pursued are not minimum academic requirements.

For study.degree_level, if the supplied source explicitly covers multiple materially different
degree levels and the scalar field cannot represent them faithfully, return null rather than
selecting one level or synthesizing a narrower value.

For these decision-critical fields:
- identity.name
- identity.provider_name
- identity.country
- study.degree_level

a non-null value MUST have at least one matching evidence item whose field_path is exactly the same
field name and whose excerpt is a verbatim substring of the supplied source text. If the value is a
normalization of explicit source wording, cite the original wording verbatim and set basis to
"normalized". Examples include explicitly stated "UK" normalized to "United Kingdom" and
explicitly stated "Masters degrees" normalized to the masters degree enum. If no valid source
excerpt can support one of these fields, return the field as null rather than emitting an
unsupported value.

Do not assume that populating the factual field itself is sufficient; the matching FieldEvidence
entry is mandatory for every populated decision-critical field listed above.

Report conflicts and warnings; do not resolve conflicting official statements silently."""


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
    """One physical Azure request per ``extract`` invocation; orchestration owns retries."""

    name = "azure_openai"

    def __init__(
        self,
        settings: Settings,
        *,
        credential: Any | None = None,
        opener: Any | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if not settings.catalogue_ai_endpoint or not settings.catalogue_ai_model:
            raise ExtractionProviderUnavailable("Azure catalogue extraction is not configured")
        self.settings = settings
        self.model = settings.catalogue_ai_model
        self.credential = credential or self._default_credential()
        self.opener = opener or urllib.request.build_opener()
        # Retained only for constructor compatibility with existing callers.  It is intentionally
        # unused: retries now belong to the durable orchestration layer.
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
        response = send_json_request(
            credential=self.credential,
            token_scope=self.settings.catalogue_ai_token_scope,
            url=f"{endpoint}/openai/v1/chat/completions",
            payload=payload,
            timeout_seconds=self.settings.catalogue_ai_timeout_seconds,
            max_response_bytes=self.settings.catalogue_ai_max_response_bytes,
            opener=self.opener,
            user_agent="ScholarshipAI-Catalogue/0.1",
        )
        return self._parse_response(
            response.raw,
            latency_ms=response.latency_ms,
            provider_request_id=response.provider_request_id,
        )

    def _parse_response(
        self,
        raw: bytes,
        *,
        latency_ms: int,
        provider_request_id: str | None,
    ) -> ExtractionResult:
        try:
            response = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ExtractionSchemaError(
                "Azure response was not valid JSON",
                provider_request_id=provider_request_id,
            ) from exc

        if not isinstance(response, dict):
            raise ExtractionSchemaError(
                "Azure response did not match the strict schema",
                provider_request_id=provider_request_id,
            )

        try:
            usage_payload = response["usage"]
            if not isinstance(usage_payload, dict):
                raise TypeError("usage must be an object")

            input_tokens = int(usage_payload["prompt_tokens"])
            output_tokens = int(usage_payload["completion_tokens"])

            usage = ExtractionUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimate_cost(
                    input_tokens,
                    output_tokens,
                    input_per_million=self.settings.catalogue_ai_input_cost_per_million,
                    output_per_million=self.settings.catalogue_ai_output_cost_per_million,
                ),
                latency_ms=latency_ms,
                provider_request_id=provider_request_id,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtractionSchemaError(
                "Azure response usage was missing or invalid",
                provider_request_id=provider_request_id,
            ) from exc

        try:
            message = response["choices"][0]["message"]
            if message.get("refusal"):
                raise ExtractionSchemaError(
                    "Model refused the extraction request",
                    usage=usage,
                    provider_request_id=provider_request_id,
                    failure_class="safety_refusal",
                )
            output = CatalogueExtractionOutput.model_validate_json(message["content"])
        except ExtractionSchemaError:
            raise
        except ValidationError as exc:
            diagnostic = json.dumps(
                exc.errors(
                    include_input=False,
                    include_url=False,
                ),
                separators=(",", ":"),
            )[:2000]
            raise ExtractionSchemaError(
                f"Azure response did not match the strict schema: {diagnostic}",
                usage=usage,
                provider_request_id=provider_request_id,
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ExtractionSchemaError(
                "Azure response did not match the strict schema",
                usage=usage,
                provider_request_id=provider_request_id,
            ) from exc

        return ExtractionResult(output=output, usage=usage)


def azure_structured_output_schema() -> dict[str, Any]:
    """Return the Pydantic contract normalized to Azure's supported strict JSON Schema subset."""

    schema = CatalogueExtractionOutput.model_json_schema()

    unsupported_keywords = {
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "multipleOf",
        "patternProperties",
        "unevaluatedProperties",
        "propertyNames",
        "minProperties",
        "maxProperties",
        "unevaluatedItems",
        "contains",
        "minContains",
        "maxContains",
        "minItems",
        "maxItems",
        "uniqueItems",
    }

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}

            for key, item in value.items():
                if key in {"title", "default"} or key in unsupported_keywords:
                    continue

                # Property/definition names are user-domain names, not JSON Schema
                # keywords, so preserve them even if a future field happens to be
                # named "format", "pattern", etc.
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
