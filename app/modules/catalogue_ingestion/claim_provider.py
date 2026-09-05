"""Strict-output provider for one source at a time in direct URL acquisition."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.modules.catalogue_ingestion.claim_schemas import (
    SUPPORTED_CLAIM_FIELDS,
    ClaimEntityType,
    ClaimExtractionOutput,
    ClaimObjective,
    ExtractedClaim,
    ObjectiveCoverageState,
)
from app.modules.catalogue_ingestion.provider import (
    ExtractionProviderUnavailable,
    ExtractionSchemaError,
    estimate_cost,
)
from app.modules.catalogue_ingestion.provider_transport import send_json_request
from app.modules.catalogue_ingestion.schemas import ExtractionUsage

CLAIM_SYSTEM_INSTRUCTION = """Extract exhaustive atomic scholarship facts from one official source.
Never use general knowledge or transfer a fact across scholarship programmes, degree levels,
application routes, cycles, countries, or institutions. Every claim must cite an exact verbatim
excerpt and exact character offsets in SOURCE TEXT. Use stable snake_case entity keys. The one
top-level scholarship entity key must be `scholarship`; programme keys identify official award
categories such as `undergraduate_students` or `research_students`; route keys identify application
routes such as `embassy_recommendation` or `university_recommendation`.

Scope every programme-specific or route-specific fact with cycle_key, programme_key, track_key,
institution_key as supported by the source. Do not broaden a scoped fact. A source that only covers
Research Students cannot establish Undergraduate requirements. A general overview can establish a
programme or route only to the detail explicitly present there.

field_path must be exactly one field name requested by OBJECTIVE. Never prefix it with the entity
type, use slash paths, pluralize it, or substitute a synonym. Emit intake_year on a cycle entity,
administering bodies as institution entities, route facts as track entities, and links as resource
url fields.

Each claim value must have exactly one non-null field. Use string_value for text and enums,
decimal_value for money, integer_value for years/counts/order, boolean_value for true/false, and
string_list_value for lists. Set the other four value fields to null. Use `explicit` for source
wording and `normalized` only for deterministic representations such as Japan -> JP, master's ->
masters, or a written date -> ISO date.

Return every fact requested by OBJECTIVE. Do not stop after one document, funding
component, eligibility rule, programme, route, deadline, event, step, or resource. Set
coverage_state=complete only when every requested item stated in this source has been emitted;
partial when output limits or ambiguity prevented exhaustive extraction; not_stated when the source
contains none of the requested facts; not_applicable only when the source explicitly establishes
that the objective does not apply. Put absent or unresolved requested facts in unknown_objectives.
Report real contradictions; do not silently reconcile them."""

CLAIM_SOURCE_SELECTION_VERSION = "objective-evidence-mask.v3"

OBJECTIVE_SOURCE_TERMS: dict[ClaimObjective, tuple[str, ...]] = {
    ClaimObjective.IDENTITY: (
        "scholarship",
        "fellowship",
        "award",
        "programme",
        "program",
        "grant",
        "bursary",
        "academic year",
        "intake",
        "ministry of education",
        "mext",
        "daad",
        "chevening",
        "fulbright",
        "erasmus",
    ),
    ClaimObjective.PROGRAMMES: (
        "degree",
        "masters",
        "master's",
        "phd",
        "doctoral",
        "doctorate",
        "postgraduate",
        "undergraduate",
        "bachelors",
        "bachelor's",
        "fields of study",
        "disciplines",
        "academic level",
        "degree course",
        "research students",
        "study period",
        "categories of students",
    ),
    ClaimObjective.PROGRAMME_DETAILS: (
        "degree",
        "masters",
        "master's",
        "phd",
        "doctoral",
        "doctorate",
        "postgraduate",
        "undergraduate",
        "bachelors",
        "bachelor's",
        "fields of study",
        "disciplines",
        "academic level",
        "degree course",
        "duration",
        "course structure",
    ),
    ClaimObjective.ROUTES: (
        "application process",
        "how to apply",
        "application route",
        "embassy recommendation",
        "university recommendation",
        "direct application",
        "online portal",
        "diplomatic mission",
        "nominating agency",
        "placement",
    ),
    ClaimObjective.ELIGIBILITY: (
        "eligibility",
        "qualifications and conditions",
        "requirements",
        "criteria",
        "nationality",
        "citizenship",
        "academic background",
        "gpa",
        "cgpa",
        "percentage",
        "age limit",
        "student visa",
        "work experience",
        "english proficiency",
        "language",
    ),
    ClaimObjective.ELIGIBILITY_CONTEXT: (
        "eligibility",
        "qualifications and conditions",
        "requirements",
        "nationality",
        "citizenship",
        "academic background",
        "minimum grade",
        "degree requirement",
        "language requirement",
        "ielts",
        "toefl",
    ),
    ClaimObjective.DOCUMENTS_CORE: (
        "documents to be submitted",
        "application documents",
        "required documents",
        "academic transcript",
        "graduation certificate",
        "degree certificate",
        "recommendation letter",
        "reference letter",
        "statement of purpose",
        "motivation letter",
        "research plan",
        "cv",
        "passport",
        "medical certificate",
        "language proficiency",
    ),
    ClaimObjective.DOCUMENTS_REQUIREMENTS: (
        "documents to be submitted",
        "application documents",
        "required documents",
        "academic transcript",
        "graduation certificate",
        "recommendation letter",
        "recommendation form",
        "statement of purpose",
        "research proposal",
        "medical certificate",
        "language certificate",
    ),
    ClaimObjective.DOCUMENTS_COUNTS: (
        "documents to be submitted",
        "application documents",
        "copies",
        "original",
        "number of documents",
        "academic transcript",
        "recommendation letter",
        "certified copies",
    ),
    ClaimObjective.DOCUMENTS_FORMAT: (
        "documents to be submitted",
        "application documents",
        "format",
        "pdf format",
        "apostille",
        "attestation",
        "notarized",
        "translation",
        "prescribed form",
    ),
    ClaimObjective.FUNDING: (
        "scholarship benefits",
        "funding",
        "allowance",
        "stipend",
        "monthly stipend",
        "living allowance",
        "tuition",
        "tuition fees",
        "waiver",
        "traveling costs",
        "airfare",
        "travel grant",
        "insurance",
        "health insurance",
        "accommodation",
    ),
    ClaimObjective.APPLICATION_TIMELINE: (
        "application deadline",
        "application period",
        "closing date",
        "due date",
        "cutoff",
        "cut-off",
        "selection schedule",
        "timeline",
        "first screening",
        "second screening",
        "interview",
        "provisional acceptance",
        "notification of results",
        "announcement",
    ),
}


OBJECTIVE_INSTRUCTIONS: dict[ClaimObjective, str] = {
    ClaimObjective.IDENTITY: """OBJECTIVE: identity.
Extract only scholarship name, provider_name, destination country_code, aliases, intake_year, and
named administering institutions. Do not enumerate programmes, routes, requirements, or benefits
in this pass. The scholarship title may contain a programme qualifier; preserve that qualifier only
when this official source is programme-specific. Use scholarship.country_code and scholarship.alias;
emit intake_year as cycle.intake_year. Extract every named administering or participating
institution as its own institution entity with role. Emit
scholarship.participating_institution_count when the official source states a total. Preserve
official programme purpose and FAQ answers as guidance entities with guidance_type, title, text,
and display_order.""",
    ClaimObjective.PROGRAMMES: """OBJECTIVE: programmes.
Extract every explicitly named scholarship programme/category. Emit name for every programme, plus
programme_type, degree_levels, and display_order when stated. Do not extract track, institution,
fields_of_study, duration, description, or application_route_keys in this pass. Do not treat a
degree, major, university course, or route as a separate scholarship.""",
    ClaimObjective.PROGRAMME_DETAILS: """OBJECTIVE: programme_details.
For every scholarship programme/category whose details are stated, emit only fields_of_study,
duration, description, and application_route_keys. Use the same stable programme entity keys and
supported scopes. Do not repeat programme names or core degree/type fields.""",
    ClaimObjective.ROUTES: """OBJECTIVE: routes.
Extract every explicit application route as a track. Emit name for every route, plus track_type,
parent_track_key,
application_method, application_url, and display_order. Extract route institutions when explicit.
Do not extract programme fields in this pass. Do not require both embassy and university routes
when the source supports only one.""",
    ClaimObjective.ELIGIBILITY: """OBJECTIVE: eligibility.
Extract every explicit eligibility requirement and exclusion. For each eligibility entity emit
only rule_type, operator, value, unit, required, and display_order when supported. Useful rule types
include nationality, residence, age, academic_background,
current_education_level, target_degree, field, language, work_experience, health, visa, and other.
Preserve programme, route, cycle, and institution scope. Do not extract documents in this pass.""",
    ClaimObjective.ELIGIBILITY_CONTEXT: """OBJECTIVE: eligibility_context.
For every eligibility rule whose context is stated, emit only condition, is_exclusion, and notes.
Use the same stable eligibility entity keys and programme/route/cycle/institution scopes supported
by the source. Preserve official selection criteria and candidate-profile statements as guidance
entities with guidance_type, title, text, and display_order. Do not repeat core rule fields or
invent exclusions and conditions.""",
    ClaimObjective.DOCUMENTS_CORE: """OBJECTIVE: documents_core.
Extract the complete required-document table/list, including conditional documents. For each
document emit only name and display_order when stated. Preserve programme, route, cycle, and
institution scope. Do not summarize a multi-item list into one document.""",
    ClaimObjective.DOCUMENTS_REQUIREMENTS: """OBJECTIVE: documents_requirements.
For every document whose requirement semantics are stated, emit only required, condition, and
submission_stage. Use the same stable document entity keys and programme/route/cycle/institution
scopes supported by the source. An if-applicable item is conditional, not universally required.
Do not repeat document names.""",
    ClaimObjective.DOCUMENTS_COUNTS: """OBJECTIVE: documents_counts.
For every document whose copy or version details are stated, emit only original_count, copy_count,
and form_year. Use the same stable document entity keys and programme/route/cycle/institution scopes
supported by the source. Do not repeat document names or invent zero counts and form years.""",
    ClaimObjective.DOCUMENTS_FORMAT: """OBJECTIVE: documents_format.
For every document whose format details are stated, emit only translation_requirement,
certification_requirement, and notes. Use the same stable document entity keys and
programme/route/cycle/institution scopes that the source supports. Do not repeat document names or
invent translations, certifications, or notes.""",
    ClaimObjective.FUNDING: """OBJECTIVE: funding.
Extract every funding component separately, including tuition/fees, stipend amounts by degree or
programme, travel, accommodation, insurance, regional supplements, and explicit out-of-pocket
items. Emit component_type, coverage_status, amount, currency, frequency, and description. Preserve
programme, route, cycle, and institution scope.""",
    ClaimObjective.APPLICATION_TIMELINE: """OBJECTIVE: application_timeline.
Extract application or document submission cutoffs as deadline entities. Arrival windows,
screening periods, result dates, study periods, and other milestones are event entities, never
application deadlines. For deadlines emit deadline_at or deadline_text, deadline_type, precision,
timezone, varies_by, label, and notes. For events emit event_type, starts_at, ends_at or date_text,
precision, timezone, label, notes, and order. Extract every ordered application/selection step.
Extract official forms, guidelines, apply pages, programme pages, and templates as resource
entities. RESOURCE LINKS is authoritative fetched link metadata; cite the matching anchor text from
SOURCE TEXT and never invent or modify a URL.""",
}


OBJECTIVE_ENTITY_TYPES: dict[ClaimObjective, frozenset[ClaimEntityType]] = {
    ClaimObjective.IDENTITY: frozenset(
        {
            ClaimEntityType.SCHOLARSHIP,
            ClaimEntityType.CYCLE,
            ClaimEntityType.INSTITUTION,
            ClaimEntityType.GUIDANCE,
        }
    ),
    ClaimObjective.PROGRAMMES: frozenset({ClaimEntityType.PROGRAMME}),
    ClaimObjective.PROGRAMME_DETAILS: frozenset({ClaimEntityType.PROGRAMME}),
    ClaimObjective.ROUTES: frozenset({ClaimEntityType.TRACK, ClaimEntityType.INSTITUTION}),
    ClaimObjective.ELIGIBILITY: frozenset({ClaimEntityType.ELIGIBILITY}),
    ClaimObjective.ELIGIBILITY_CONTEXT: frozenset(
        {ClaimEntityType.ELIGIBILITY, ClaimEntityType.GUIDANCE}
    ),
    ClaimObjective.DOCUMENTS_CORE: frozenset({ClaimEntityType.DOCUMENT}),
    ClaimObjective.DOCUMENTS_REQUIREMENTS: frozenset({ClaimEntityType.DOCUMENT}),
    ClaimObjective.DOCUMENTS_COUNTS: frozenset({ClaimEntityType.DOCUMENT}),
    ClaimObjective.DOCUMENTS_FORMAT: frozenset({ClaimEntityType.DOCUMENT}),
    ClaimObjective.FUNDING: frozenset({ClaimEntityType.FUNDING}),
    ClaimObjective.APPLICATION_TIMELINE: frozenset(
        {
            ClaimEntityType.DEADLINE,
            ClaimEntityType.EVENT,
            ClaimEntityType.STEP,
            ClaimEntityType.RESOURCE,
            ClaimEntityType.TRACK,
        }
    ),
}

OBJECTIVE_FIELD_PATHS: dict[ClaimObjective, frozenset[str]] = {
    ClaimObjective.PROGRAMMES: frozenset(
        {"name", "programme_type", "degree_levels", "display_order"}
    ),
    ClaimObjective.PROGRAMME_DETAILS: frozenset(
        {"fields_of_study", "duration", "description", "application_route_keys"}
    ),
    ClaimObjective.ELIGIBILITY: frozenset(
        {"rule_type", "operator", "value", "unit", "required", "display_order"}
    ),
    ClaimObjective.ELIGIBILITY_CONTEXT: frozenset(
        {
            "condition",
            "is_exclusion",
            "notes",
            "title",
            "guidance_type",
            "text",
            "display_order",
        }
    ),
    ClaimObjective.DOCUMENTS_CORE: frozenset({"name", "display_order"}),
    ClaimObjective.DOCUMENTS_REQUIREMENTS: frozenset({"required", "condition", "submission_stage"}),
    ClaimObjective.DOCUMENTS_COUNTS: frozenset({"original_count", "copy_count", "form_year"}),
    ClaimObjective.DOCUMENTS_FORMAT: frozenset(
        {
            "translation_requirement",
            "certification_requirement",
            "notes",
        }
    ),
}


class ClaimOutputTruncated(ExtractionSchemaError):
    code = "ai_output_truncated"


class ClaimExtractionResult(BaseModel):
    output: ClaimExtractionOutput
    usage: ExtractionUsage


class CatalogueClaimProvider(Protocol):
    name: str
    model: str

    def extract_claims(
        self,
        *,
        source_url: str,
        source_text: str,
        objective: ClaimObjective = ClaimObjective.IDENTITY,
        source_links: list[dict[str, str | None]] | None = None,
    ) -> ClaimExtractionResult: ...


class UnavailableClaimProvider:
    name = "unavailable"

    def __init__(self, model: str) -> None:
        self.model = model

    def extract_claims(
        self,
        *,
        source_url: str,
        source_text: str,
        objective: ClaimObjective = ClaimObjective.IDENTITY,
        source_links: list[dict[str, str | None]] | None = None,
    ) -> ClaimExtractionResult:
        del source_url, source_text, objective, source_links
        raise ExtractionProviderUnavailable("Catalogue claim extraction is disabled")


class FakeClaimProvider:
    name = "fake_claims"

    def __init__(
        self,
        output: (
            ClaimExtractionOutput
            | dict[ClaimObjective, ClaimExtractionOutput]
            | Callable[[str, str], ClaimExtractionOutput]
        ),
        *,
        model: str = "fake-catalogue-claims-v2",
    ) -> None:
        self.output = output
        self.model = model
        self.calls = 0

    def extract_claims(
        self,
        *,
        source_url: str,
        source_text: str,
        objective: ClaimObjective = ClaimObjective.IDENTITY,
        source_links: list[dict[str, str | None]] | None = None,
    ) -> ClaimExtractionResult:
        del source_links
        self.calls += 1
        if callable(self.output):
            output = self.output(source_url, source_text)
        elif isinstance(self.output, dict):
            output = self.output[objective]
        else:
            output = self.output
        output = _normalize_claim_output(output, source_text, objective=objective)
        return ClaimExtractionResult(
            output=output,
            usage=ExtractionUsage(
                input_tokens=max(1, len(source_text) // 4),
                output_tokens=max(1, len(output.model_dump_json()) // 4),
                latency_ms=1,
            ),
        )


class AzureOpenAIClaimProvider:
    """One physical Azure request per objective invocation; orchestration owns retries."""

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
        self.sleeper = sleeper

    @staticmethod
    def _default_credential() -> Any:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ExtractionProviderUnavailable("Azure Identity dependency is unavailable") from exc
        return DefaultAzureCredential()

    def extract_claims(
        self,
        *,
        source_url: str,
        source_text: str,
        objective: ClaimObjective = ClaimObjective.IDENTITY,
        source_links: list[dict[str, str | None]] | None = None,
    ) -> ClaimExtractionResult:
        prompt_text = _objective_source_text(
            source_text,
            objective,
            target_evidence_characters=min(
                self.settings.catalogue_ai_max_input_characters,
                16_000,
            ),
        )
        objective_links = source_links if objective is ClaimObjective.APPLICATION_TIMELINE else []
        links_text = json.dumps(objective_links or [], ensure_ascii=True, separators=(",", ":"))
        instruction = f"{CLAIM_SYSTEM_INSTRUCTION}\n\n{OBJECTIVE_INSTRUCTIONS[objective]}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instruction},
                {
                    "role": "user",
                    "content": (
                        f"OFFICIAL SOURCE URL: {source_url}\n"
                        f"OBJECTIVE: {objective.value}\n"
                        f"RESOURCE LINKS: {links_text}\n"
                        "Whitespace-only gaps in SOURCE TEXT are deliberately omitted regions; "
                        "character positions are preserved.\n\n"
                        f"SOURCE TEXT:\n{prompt_text}"
                    ),
                },
            ],
            "max_completion_tokens": self.settings.catalogue_ai_max_output_tokens,
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
        request_body = json.dumps(body, separators=(",", ":")).encode()
        endpoint = self.settings.catalogue_ai_endpoint.rstrip("/")
        response = send_json_request(
            credential=self.credential,
            token_scope=self.settings.catalogue_ai_token_scope,
            url=f"{endpoint}/openai/v1/chat/completions",
            payload=request_body,
            timeout_seconds=self.settings.catalogue_ai_timeout_seconds,
            max_response_bytes=self.settings.catalogue_ai_max_response_bytes,
            opener=self.opener,
            user_agent="ScholarshipAI-Catalogue/0.1",
        )
        result = self._parse(
            response.raw,
            latency_ms=response.latency_ms,
            provider_request_id=response.provider_request_id,
        )
        result.output = _normalize_claim_output(result.output, source_text, objective=objective)
        return result

    def _parse(
        self,
        raw: bytes,
        start_time: float | None = None,
        *,
        latency_ms: int = 0,
        provider_request_id: str | None = None,
    ) -> ClaimExtractionResult:
        if start_time is not None and latency_ms == 0:
            import time

            latency_ms = max(0, int((time.perf_counter() - start_time) * 1000))
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
            message = response["choices"][0]["message"]
            if response["choices"][0].get("finish_reason") == "length":
                raise ClaimOutputTruncated(
                    "Model output reached the configured token limit",
                    usage=usage,
                    provider_request_id=provider_request_id,
                )
            if message.get("refusal"):
                raise ExtractionSchemaError(
                    "Model refused the claim extraction",
                    usage=usage,
                    provider_request_id=provider_request_id,
                    failure_class="safety_refusal",
                )
            output_data = json.loads(message["content"])
            output_data, invalid_claims, placeholders = _drop_invalid_atomic_claims(output_data)
            output = ClaimExtractionOutput.model_validate(output_data)
            if invalid_claims:
                output.coverage_state = ObjectiveCoverageState.PARTIAL
                output.warnings.append(f"provider_invalid_claims_dropped:{len(invalid_claims)}")
                output.warnings.extend(
                    f"provider_invalid_claim:{item}" for item in invalid_claims[:5]
                )
                output.unknown_objectives.append(
                    "One or more requested facts had invalid typed values or evidence spans"
                )
            if placeholders:
                output.warnings.append(f"provider_null_placeholders_dropped:{placeholders}")
        except ExtractionSchemaError:
            raise
        except ValidationError as exc:
            diagnostic = json.dumps(
                exc.errors(include_input=False, include_url=False),
                separators=(",", ":"),
                default=str,
            )[:2000]
            raise ExtractionSchemaError(
                f"Azure claim response did not match the strict schema: {diagnostic}",
                usage=usage,
                provider_request_id=provider_request_id,
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExtractionSchemaError(
                "Azure claim response did not match the strict schema",
                usage=usage,
                provider_request_id=provider_request_id,
            ) from exc
        return ClaimExtractionResult(output=output, usage=usage)


def _drop_invalid_atomic_claims(payload: object) -> tuple[object, list[str], int]:
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        return payload, [], 0
    valid: list[object] = []
    invalid: list[str] = []
    placeholders = 0
    for raw_claim in payload["claims"]:
        if isinstance(raw_claim, dict) and isinstance(raw_claim.get("value"), dict):
            values = raw_claim["value"].values()
            if not any(value not in (None, []) for value in values):
                placeholders += 1
                continue
        try:
            ExtractedClaim.model_validate(raw_claim)
        except ValidationError as exc:
            entity_type = (
                raw_claim.get("entity_type", "unknown")
                if isinstance(raw_claim, dict)
                else "unknown"
            )
            field_path = (
                raw_claim.get("field_path", "unknown") if isinstance(raw_claim, dict) else "unknown"
            )
            error_type = exc.errors(include_input=False, include_url=False)[0]["type"]
            invalid.append(f"{entity_type}:{field_path}:{error_type}")
            continue
        valid.append(raw_claim)
    payload["claims"] = valid
    return payload, invalid, placeholders


def claim_extraction_prompt_hash(
    objective: ClaimObjective = ClaimObjective.IDENTITY,
) -> str:
    prompt = (
        f"{CLAIM_SOURCE_SELECTION_VERSION}\n{CLAIM_SYSTEM_INSTRUCTION}\n\n"
        f"{OBJECTIVE_INSTRUCTIONS[objective]}"
    )
    return hashlib.sha256(prompt.encode()).hexdigest()


def _objective_source_text(
    source_text: str,
    objective: ClaimObjective,
    *,
    passthrough_characters: int = 6_000,
    target_evidence_characters: int = 8_000,
) -> str:
    """Mask irrelevant text while preserving every original evidence offset."""
    if len(source_text) <= passthrough_characters:
        return source_text

    folded = source_text.casefold()
    ranges: list[tuple[int, int]] = [(0, min(len(source_text), 2_000))]
    for term in OBJECTIVE_SOURCE_TERMS[objective]:
        start = 0
        matches = 0
        while matches < 8:
            position = folded.find(term, start)
            if position < 0:
                break
            ranges.append((max(0, position - 800), min(len(source_text), position + 2_400)))
            start = position + len(term)
            matches += 1

    selected = bytearray(len(source_text))
    remaining = target_evidence_characters
    for start, end in ranges:
        for index in range(start, end):
            if selected[index]:
                continue
            if remaining == 0:
                break
            selected[index] = 1
            remaining -= 1
        if remaining == 0:
            break
    masked = [" " if not character.isspace() else character for character in source_text]
    for index, is_selected in enumerate(selected):
        if is_selected:
            masked[index] = source_text[index]
    return "".join(masked)


def get_claim_provider(settings: Settings) -> CatalogueClaimProvider:
    if not settings.catalogue_ai_ingestion_enabled:
        return UnavailableClaimProvider(settings.catalogue_ai_model or "disabled")
    return AzureOpenAIClaimProvider(settings)


def _normalize_claim_output(
    output: ClaimExtractionOutput,
    source_text: str,
    *,
    objective: ClaimObjective = ClaimObjective.IDENTITY,
) -> ClaimExtractionOutput:
    allowed = OBJECTIVE_ENTITY_TYPES[objective]
    allowed_fields = OBJECTIVE_FIELD_PATHS.get(objective)
    normalized_claims = [_normalize_claim_shape(item) for item in output.claims]
    claims = [
        _bind_unique_evidence_span(item, source_text)
        for item in normalized_claims
        if item.entity_type in allowed
        and (allowed_fields is None or item.field_path in allowed_fields)
    ]
    warnings = list(output.warnings)
    return output.model_copy(
        update={
            "objective": objective,
            "claims": claims,
            "warnings": warnings,
        }
    )


def _normalize_claim_shape(claim: ExtractedClaim) -> ExtractedClaim:
    if claim.entity_type is ClaimEntityType.SCHOLARSHIP and claim.field_path == "intake_year":
        value = claim.value.primitive()
        cycle_key = claim.scope.cycle_key or f"intake_{value}"
        return claim.model_copy(
            update={
                "entity_type": ClaimEntityType.CYCLE,
                "entity_key": cycle_key,
                "scope": claim.scope.model_copy(update={"cycle_key": cycle_key}),
            }
        )
    if claim.entity_type is ClaimEntityType.DEADLINE and claim.field_path in {
        "starts_at",
        "ends_at",
    }:
        return claim.model_copy(update={"entity_type": ClaimEntityType.EVENT})
    return claim


def _bind_unique_evidence_span(claim: ExtractedClaim, source_text: str) -> ExtractedClaim:
    if (
        claim.excerpt_end <= len(source_text)
        and source_text[claim.excerpt_start : claim.excerpt_end] == claim.excerpt
    ):
        return claim
    starts: list[int] = []
    position = source_text.find(claim.excerpt)
    while position >= 0 and len(starts) < 100:
        starts.append(position)
        position = source_text.find(claim.excerpt, position + 1)
    if not starts:
        stripped = claim.excerpt.strip()
        if stripped:
            position = source_text.find(stripped)
            while position >= 0 and len(starts) < 100:
                starts.append(position)
                position = source_text.find(stripped, position + 1)
    if not starts:
        norm_claim = unicodedata.normalize("NFKC", claim.excerpt).replace("\u00a0", " ")
        norm_source = unicodedata.normalize("NFKC", source_text).replace("\u00a0", " ")
        position = norm_source.find(norm_claim)
        while position >= 0 and len(starts) < 100:
            starts.append(position)
            position = norm_source.find(norm_claim, position + 1)
    if not starts:
        return claim
    distance = min(abs(start - claim.excerpt_start) for start in starts)
    nearest = [start for start in starts if abs(start - claim.excerpt_start) == distance]
    if len(nearest) != 1:
        return claim
    start = nearest[0]
    return claim.model_copy(
        update={"excerpt_start": start, "excerpt_end": start + len(claim.excerpt)}
    )


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


def _objective_azure_schema(objective: ClaimObjective) -> dict[str, Any]:
    schema = _azure_schema(ClaimExtractionOutput)
    allowed_entities = OBJECTIVE_ENTITY_TYPES[objective]
    allowed_fields = OBJECTIVE_FIELD_PATHS.get(objective) or frozenset(
        field_path
        for entity_type in allowed_entities
        for field_path in SUPPORTED_CLAIM_FIELDS[entity_type]
    )
    definitions = schema["$defs"]
    definitions["ClaimEntityType"]["enum"] = sorted(item.value for item in allowed_entities)
    definitions["ClaimObjective"]["enum"] = [objective.value]
    definitions["ExtractedClaim"]["properties"]["field_path"] = {
        "enum": sorted(allowed_fields),
        "type": "string",
    }
    return schema
