"""Single-attempt provider adapters for routed multi-objective claim bundles."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.modules.catalogue_ingestion.claim_bundle_schemas import (
    BundledAtomicClaim,
    BundleEvidenceReference,
    BundleObjectiveCoverage,
    ClaimBundleExtractionOutput,
)
from app.modules.catalogue_ingestion.claim_provider import (
    CLAIM_SYSTEM_INSTRUCTION,
    OBJECTIVE_ENTITY_TYPES,
    OBJECTIVE_FIELD_PATHS,
    OBJECTIVE_INSTRUCTIONS,
    ClaimOutputTruncated,
    _azure_schema,
)
from app.modules.catalogue_ingestion.claim_schemas import (
    SUPPORTED_CLAIM_FIELDS,
    ClaimObjective,
    ObjectiveCoverageState,
)
from app.modules.catalogue_ingestion.provider import (
    ExtractionProviderUnavailable,
    ExtractionSchemaError,
    estimate_cost,
)
from app.modules.catalogue_ingestion.provider_transport import send_json_request
from app.modules.catalogue_ingestion.schemas import ExtractionUsage

CLAIM_BUNDLE_PROMPT_VERSION = "catalogue-claim-bundle-prompt.v2"
CLAIM_BUNDLE_SYSTEM_INSTRUCTION = f"""{CLAIM_SYSTEM_INSTRUCTION}

This request may contain several compatible OBJECTIVES at once. Every atomic claim MUST include its
objective. Do not transfer a fact between objectives. Use shared evidence references: declare an
excerpt once in evidence_refs and let one or more claims point to that ref_id. Every evidence
reference MUST name one supplied block_key and use the absolute source-artifact character offsets
recorded in that block header, not prompt-relative offsets. Never cite block metadata as evidence.

Return objective_coverage exactly once for every requested objective. A coverage state describes
only the supplied evidence blocks, not the whole website. If the supplied routed blocks are
insufficient, use partial or not_stated and name what remains unknown rather than guessing."""


class BundleClaimExtractionResult(BaseModel):
    output: ClaimBundleExtractionOutput
    usage: ExtractionUsage


class CatalogueBundleClaimProvider(Protocol):
    name: str
    model: str
    capability_identity: str

    def extract_bundle(
        self,
        *,
        source_url: str,
        evidence_text: str,
        objectives: tuple[ClaimObjective, ...],
        scope_targets: list[dict[str, str]],
        source_links: list[dict[str, Any]] | None = None,
        max_output_tokens: int,
    ) -> BundleClaimExtractionResult: ...


class UnavailableBundleClaimProvider:
    name = "unavailable"

    def __init__(self, model: str) -> None:
        self.model = model
        self.capability_identity = f"unavailable:{model}:claim_bundle_v1"

    def extract_bundle(
        self,
        *,
        source_url: str,
        evidence_text: str,
        objectives: tuple[ClaimObjective, ...],
        scope_targets: list[dict[str, str]],
        source_links: list[dict[str, Any]] | None = None,
        max_output_tokens: int,
    ) -> BundleClaimExtractionResult:
        del source_url, evidence_text, objectives, scope_targets, source_links, max_output_tokens
        raise ExtractionProviderUnavailable("Catalogue bundle extraction is disabled")


class FakeBundleClaimProvider:
    name = "fake_claim_bundle"

    def __init__(
        self,
        output: ClaimBundleExtractionOutput | Callable[[str, str], ClaimBundleExtractionOutput],
        *,
        model: str = "fake-catalogue-claim-bundle-v1",
    ) -> None:
        self.output = output
        self.model = model
        self.capability_identity = f"fake:{model}:claim_bundle_v1"
        self.calls = 0

    def extract_bundle(
        self,
        *,
        source_url: str,
        evidence_text: str,
        objectives: tuple[ClaimObjective, ...],
        scope_targets: list[dict[str, str]],
        source_links: list[dict[str, Any]] | None = None,
        max_output_tokens: int,
    ) -> BundleClaimExtractionResult:
        del scope_targets, source_links, max_output_tokens
        self.calls += 1
        output = self.output(source_url, evidence_text) if callable(self.output) else self.output
        requested = set(objectives)
        if any(claim.objective not in requested for claim in output.claims):
            raise ExtractionSchemaError("Fake bundle output contains an unrequested objective")
        return BundleClaimExtractionResult(
            output=output,
            usage=ExtractionUsage(
                input_tokens=max(1, len(evidence_text) // 4),
                output_tokens=max(1, len(output.model_dump_json()) // 4),
                latency_ms=1,
            ),
        )


class AzureOpenAIBundleClaimProvider:
    """One physical Azure request for one deterministic evidence bundle."""

    name = "azure_openai"

    def __init__(
        self,
        settings: Settings,
        *,
        credential: Any | None = None,
        opener: Any | None = None,
    ) -> None:
        if not settings.catalogue_ai_endpoint or not settings.catalogue_ai_model:
            raise ExtractionProviderUnavailable("Azure catalogue extraction is not configured")
        self.settings = settings
        self.model = settings.catalogue_ai_model
        self.capability_identity = (
            f"azure_openai:{self.model}:strict_json_schema:multi_objective:shared_evidence:v1"
        )
        self.credential = credential or self._default_credential()
        self.opener = opener or urllib.request.build_opener()

    @staticmethod
    def _default_credential() -> Any:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ExtractionProviderUnavailable("Azure Identity dependency is unavailable") from exc
        return DefaultAzureCredential()

    def extract_bundle(
        self,
        *,
        source_url: str,
        evidence_text: str,
        objectives: tuple[ClaimObjective, ...],
        scope_targets: list[dict[str, str]],
        source_links: list[dict[str, Any]] | None = None,
        max_output_tokens: int,
    ) -> BundleClaimExtractionResult:
        requested = tuple(dict.fromkeys(objectives))
        if not requested:
            raise ExtractionSchemaError("Bundle extraction requires at least one objective")
        if len(evidence_text) > self.settings.catalogue_ai_max_input_characters:
            raise ExtractionSchemaError(
                "Planned evidence bundle exceeds the configured input-character limit",
                failure_class="pre_dispatch_failure",
            )
        if (
            max_output_tokens < 1
            or max_output_tokens > self.settings.catalogue_ai_max_output_tokens
        ):
            raise ExtractionSchemaError(
                "Planned output-token bound exceeds the configured provider limit",
                failure_class="pre_dispatch_failure",
            )
        objective_instructions = "\n\n".join(OBJECTIVE_INSTRUCTIONS[item] for item in requested)
        links = source_links if ClaimObjective.APPLICATION_TIMELINE in requested else []
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": f"{CLAIM_BUNDLE_SYSTEM_INSTRUCTION}\n\n{objective_instructions}",
                },
                {
                    "role": "user",
                    "content": (
                        f"OFFICIAL SOURCE URL: {source_url}\n"
                        "OBJECTIVES: "
                        f"{json.dumps([item.value for item in requested], separators=(',', ':'))}\n"
                        "SCOPE TARGETS: "
                        f"{json.dumps(scope_targets, ensure_ascii=True, separators=(',', ':'))}\n"
                        "RESOURCE LINKS: "
                        f"{json.dumps(links or [], ensure_ascii=True, separators=(',', ':'))}\n\n"
                        "ROUTED EVIDENCE BLOCKS:\n"
                        f"{evidence_text}"
                    ),
                },
            ],
            "max_completion_tokens": max_output_tokens,
            "reasoning_effort": "minimal",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "catalogue_claim_bundle_extraction",
                    "strict": True,
                    "schema": _bundle_azure_schema(requested),
                },
            },
        }
        response = send_json_request(
            credential=self.credential,
            token_scope=self.settings.catalogue_ai_token_scope,
            url=f"{self.settings.catalogue_ai_endpoint.rstrip('/')}/openai/v1/chat/completions",
            payload=json.dumps(body, separators=(",", ":")).encode(),
            timeout_seconds=self.settings.catalogue_ai_timeout_seconds,
            max_response_bytes=self.settings.catalogue_ai_max_response_bytes,
            opener=self.opener,
            user_agent="ScholarshipAI-Catalogue/0.1",
        )
        return self._parse(
            response.raw,
            requested=requested,
            latency_ms=response.latency_ms,
            provider_request_id=response.provider_request_id,
        )

    def _parse(
        self,
        raw: bytes,
        *,
        requested: tuple[ClaimObjective, ...],
        latency_ms: int,
        provider_request_id: str | None,
    ) -> BundleClaimExtractionResult:
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
                latency_ms=latency_ms,
                provider_request_id=provider_request_id,
            )
            choice = response["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ClaimOutputTruncated(
                    "Model output reached the planned bundle token limit",
                    usage=usage,
                    provider_request_id=provider_request_id,
                )
            message = choice["message"]
            if message.get("refusal"):
                raise ExtractionSchemaError(
                    "Model refused the bundled claim extraction",
                    usage=usage,
                    provider_request_id=provider_request_id,
                    failure_class="safety_refusal",
                )
            payload = json.loads(message["content"])
            payload, dropped_objectives, diagnostic_warnings = _sanitize_bundle_payload(payload)
            output = ClaimBundleExtractionOutput.model_validate(payload)
            requested_set = set(requested)
            if any(claim.objective not in requested_set for claim in output.claims):
                raise ExtractionSchemaError(
                    "Bundle response contained an unrequested objective",
                    usage=usage,
                    provider_request_id=provider_request_id,
                )
            coverage = {item.objective: item for item in output.objective_coverage}
            for objective in requested:
                if objective in dropped_objectives and objective in coverage:
                    item = coverage[objective]
                    coverage[objective] = item.model_copy(
                        update={
                            "coverage_state": ObjectiveCoverageState.PARTIAL,
                            "unknown_objectives": list(
                                dict.fromkeys(
                                    [
                                        *item.unknown_objectives,
                                        "Provider emitted one or more invalid bundled items",
                                    ]
                                )
                            ),
                        }
                    )
            output = output.model_copy(
                update={
                    "objective_coverage": list(coverage.values()),
                    "warnings": list(dict.fromkeys([*output.warnings, *diagnostic_warnings])),
                }
            )
        except ExtractionSchemaError:
            raise
        except ValidationError as exc:
            diagnostic = json.dumps(
                exc.errors(include_input=False, include_url=False),
                separators=(",", ":"),
                default=str,
            )[:2000]
            raise ExtractionSchemaError(
                f"Azure bundle response did not match the strict schema: {diagnostic}",
                usage=usage,
                provider_request_id=provider_request_id,
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExtractionSchemaError(
                "Azure bundle response did not match the strict schema",
                usage=usage,
                provider_request_id=provider_request_id,
            ) from exc
        return BundleClaimExtractionResult(output=output, usage=usage)


def bundle_claim_prompt_hash(objectives: Iterable[ClaimObjective]) -> str:
    requested = tuple(sorted({item for item in objectives}, key=lambda item: item.value))
    prompt = "\n".join(
        (
            CLAIM_BUNDLE_PROMPT_VERSION,
            CLAIM_BUNDLE_SYSTEM_INSTRUCTION,
            *(OBJECTIVE_INSTRUCTIONS[item] for item in requested),
        )
    )
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def get_bundle_claim_provider(settings: Settings) -> CatalogueBundleClaimProvider:
    if not settings.catalogue_ai_ingestion_enabled:
        return UnavailableBundleClaimProvider(settings.catalogue_ai_model or "disabled")
    return AzureOpenAIBundleClaimProvider(settings)


def _bundle_azure_schema(objectives: tuple[ClaimObjective, ...]) -> dict[str, Any]:
    schema = _azure_schema(ClaimBundleExtractionOutput)
    definitions = schema.get("$defs", {})
    objective_schema = definitions.get("ClaimObjective")
    if isinstance(objective_schema, dict):
        objective_schema["enum"] = sorted(item.value for item in objectives)
    allowed_entities = frozenset(
        entity for objective in objectives for entity in OBJECTIVE_ENTITY_TYPES[objective]
    )
    entity_schema = definitions.get("ClaimEntityType")
    if isinstance(entity_schema, dict):
        entity_schema["enum"] = sorted(item.value for item in allowed_entities)
    allowed_fields = frozenset(
        field_path
        for objective in objectives
        for field_path in (
            OBJECTIVE_FIELD_PATHS.get(objective)
            or frozenset(
                path
                for entity_type in OBJECTIVE_ENTITY_TYPES[objective]
                for path in SUPPORTED_CLAIM_FIELDS[entity_type]
            )
        )
    )
    claim_schema = definitions.get("BundledAtomicClaim")
    if isinstance(claim_schema, dict):
        properties = claim_schema.get("properties")
        if isinstance(properties, dict):
            properties["field_path"] = {"type": "string", "enum": sorted(allowed_fields)}
    return schema


def _sanitize_bundle_payload(
    payload: object,
) -> tuple[object, set[ClaimObjective], list[str]]:
    if not isinstance(payload, dict):
        return payload, set(), []
    dropped_objectives: set[ClaimObjective] = set()
    warnings: list[str] = []

    raw_refs = payload.get("evidence_refs")
    valid_refs: list[dict[str, Any]] = []
    valid_ref_ids: set[str] = set()
    invalid_ref_ids: set[str] = set()
    if isinstance(raw_refs, list):
        for raw in raw_refs:
            try:
                ref = BundleEvidenceReference.model_validate(raw)
            except ValidationError:
                ref_id = raw.get("ref_id") if isinstance(raw, dict) else None
                if isinstance(ref_id, str):
                    invalid_ref_ids.add(ref_id)
                continue
            valid_refs.append(ref.model_dump(mode="json"))
            valid_ref_ids.add(ref.ref_id)
        if len(valid_refs) != len(raw_refs):
            warnings.append(
                f"provider_invalid_evidence_refs_dropped:{len(raw_refs) - len(valid_refs)}"
            )
        payload["evidence_refs"] = valid_refs

    raw_claims = payload.get("claims")
    valid_claims: list[dict[str, Any]] = []
    if isinstance(raw_claims, list):
        for raw in raw_claims:
            try:
                claim = BundledAtomicClaim.model_validate(raw)
            except ValidationError:
                objective = _raw_objective(raw)
                if objective is not None:
                    dropped_objectives.add(objective)
                continue
            if (
                claim.evidence_ref_id not in valid_ref_ids
                or claim.evidence_ref_id in invalid_ref_ids
            ):
                dropped_objectives.add(claim.objective)
                continue
            valid_claims.append(claim.model_dump(mode="json"))
        if len(valid_claims) != len(raw_claims):
            warnings.append(
                f"provider_invalid_bundle_claims_dropped:{len(raw_claims) - len(valid_claims)}"
            )
        payload["claims"] = valid_claims

    raw_coverage = payload.get("objective_coverage")
    valid_coverage: list[dict[str, Any]] = []
    if isinstance(raw_coverage, list):
        for raw in raw_coverage:
            try:
                item = BundleObjectiveCoverage.model_validate(raw)
            except ValidationError:
                objective = _raw_objective(raw)
                if objective is not None:
                    dropped_objectives.add(objective)
                continue
            valid_coverage.append(item.model_dump(mode="json"))
        if len(valid_coverage) != len(raw_coverage):
            warnings.append(
                "provider_invalid_bundle_coverage_dropped:"
                f"{len(raw_coverage) - len(valid_coverage)}"
            )
        payload["objective_coverage"] = valid_coverage
    return payload, dropped_objectives, warnings


def _raw_objective(raw: object) -> ClaimObjective | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("objective")
    try:
        return ClaimObjective(str(value))
    except ValueError:
        return None


__all__ = [
    "CLAIM_BUNDLE_PROMPT_VERSION",
    "CLAIM_BUNDLE_SYSTEM_INSTRUCTION",
    "AzureOpenAIBundleClaimProvider",
    "BundleClaimExtractionResult",
    "CatalogueBundleClaimProvider",
    "FakeBundleClaimProvider",
    "UnavailableBundleClaimProvider",
    "bundle_claim_prompt_hash",
    "get_bundle_claim_provider",
]
