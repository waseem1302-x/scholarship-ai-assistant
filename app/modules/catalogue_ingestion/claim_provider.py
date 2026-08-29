"""Strict-output provider for one source at a time in direct URL acquisition."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.modules.catalogue_ingestion.ai_contract import azure_openai_request_url
from app.modules.catalogue_ingestion.claim_schemas import (
    SUPPORTED_CLAIM_FIELDS,
    ClaimEntityType,
    ClaimExtractionOutput,
    ClaimObjective,
    ClaimValue,
    ExtractedClaim,
    ObjectiveCoverageState,
)
from app.modules.catalogue_ingestion.provider import (
    ExtractionProviderError,
    ExtractionProviderRateLimited,
    ExtractionProviderTimeout,
    ExtractionProviderUnavailable,
    ExtractionSchemaError,
    estimate_cost,
    extraction_retry_delay,
)
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

Return every fact requested by OBJECTIVE, up to 48 claims. Do not stop after one document, funding
component, eligibility rule, programme, route, deadline, event, step, or resource. Set
coverage_state=complete only when every requested item stated in this source has been emitted;
partial when output limits or ambiguity prevented exhaustive extraction; not_stated when the source
contains none of the requested facts; not_applicable only when the source explicitly establishes
that the objective does not apply. Put absent or unresolved requested facts in unknown_objectives.
Coverage measures extraction of facts actually stated in THIS source. Missing optional fields,
links to other programme pages, or facts that the source never states are not reasons to mark an
otherwise exhaustive extraction partial. Keep claims scoped to the scholarship named in the page's
primary title; navigation, related-scholarship links, and examples of other awards are not target
programmes.
Report real contradictions; do not silently reconcile them."""

CLAIM_SOURCE_SELECTION_VERSION = "objective-evidence-mask.v6"

OBJECTIVE_SOURCE_TERMS: dict[ClaimObjective, tuple[str, ...]] = {
    ClaimObjective.IDENTITY: (
        "scholarship",
        "fellowship",
        "funded by",
        "administered by",
        "academic year",
        "intake",
        "japanese government (mext) scholarship",
        "mext scholarship",
        "ministry of education",
        "academic year 2027",
        "2027 scholarship",
    ),
    ClaimObjective.PROGRAMMES: (
        "programme",
        "program",
        "master",
        "doctoral",
        "phd",
        "undergraduate",
        "degree",
        "types of japanese government (mext) scholarships",
        "categories of students",
        "scholarship period",
        "fields of study",
        "academic level",
        "degree course",
        "research students",
        "undergraduate students",
    ),
    ClaimObjective.PROGRAMME_DETAILS: (
        "programme",
        "program",
        "duration",
        "full-time",
        "field of study",
        "course of study",
        "development themes",
        "types of japanese government (mext) scholarships",
        "categories of students",
        "scholarship period",
        "fields of study",
        "academic level",
        "degree course",
        "research students",
        "undergraduate students",
    ),
    ClaimObjective.ROUTES: (
        "how to apply",
        "nominator",
        "nominating agencies",
        "application route",
        "direct applications",
        "application system",
        "application process",
        "embassy recommendation",
        "university recommendation",
        "direct placement",
        "japanese diplomatic mission",
    ),
    ClaimObjective.ELIGIBILITY: (
        "applicant eligibility",
        "eligible countries",
        "eligible",
        "must",
        "citizen",
        "permanently resident",
        "first degree",
        "work experience",
        "language requirement",
        "qualifications and conditions",
        "nationality",
        "academic background",
        "arrival in japan",
        "student visa",
        "health",
        "age",
    ),
    ClaimObjective.ELIGIBILITY_CONTEXT: (
        "applicant eligibility",
        "eligible countries",
        "eligible",
        "must",
        "citizen",
        "permanently resident",
        "first degree",
        "work experience",
        "language requirement",
        "qualifications and conditions",
        "nationality",
        "academic background",
        "arrival in japan",
        "student visa",
        "health",
        "age",
    ),
    ClaimObjective.DOCUMENTS_CORE: (
        "supporting documentation",
        "supporting documents",
        "applications must include",
        "applicants must upload",
        "transcripts",
        "references",
        "passport",
        "national id",
        "documents to be submitted",
        "application documents",
        "academic transcript",
        "graduation certificate",
        "recommendation letter",
        "recommendation form",
        "medical certificate",
        "language proficiency",
    ),
    ClaimObjective.DOCUMENTS_REQUIREMENTS: (
        "supporting documentation",
        "supporting documents",
        "applications must include",
        "applicants must upload",
        "transcripts",
        "references",
        "passport",
        "national id",
        "documents to be submitted",
        "application documents",
        "academic transcript",
        "graduation certificate",
        "recommendation letter",
        "recommendation form",
        "medical certificate",
        "language proficiency",
    ),
    ClaimObjective.DOCUMENTS_COUNTS: (
        "supporting documentation",
        "supporting documents",
        "copies",
        "copy",
        "original",
        "references",
        "documents to be submitted",
        "application documents",
        "academic transcript",
        "graduation certificate",
        "recommendation letter",
        "recommendation form",
        "medical certificate",
        "language proficiency",
    ),
    ClaimObjective.DOCUMENTS_FORMAT: (
        "supporting documentation",
        "supporting documents",
        "pdf format",
        "certified translation",
        "letterhead",
        "signed",
        "transcripts",
        "references",
        "documents to be submitted",
        "application documents",
        "academic transcript",
        "graduation certificate",
        "recommendation letter",
        "recommendation form",
        "medical certificate",
        "language proficiency",
    ),
    ClaimObjective.FUNDING: (
        "financial assistance",
        "tuition fees",
        "living allowance",
        "airfare",
        "travel grant",
        "accommodation",
        "insurance",
        "child allowance",
        "thesis grant",
        "scholarship benefits",
        "allowance",
        "education fees",
        "traveling costs",
        "transportation to japan",
        "transportation from japan",
    ),
    ClaimObjective.APPLICATION_TIMELINE: (
        "how to apply",
        "applications for",
        "will open",
        "closing date",
        "academic year",
        "application system",
        "nominator",
        "expect to hear",
        "application deadline",
        "application period",
        "deadline for submission",
        "contact the japanese diplomatic mission",
        "application form",
        "documents to be submitted",
        "submission of application documents",
        "selection schedule",
        "first screening",
        "second screening",
        "provisional acceptance",
        "notification of results",
        "selection",
    ),
}


OBJECTIVE_INSTRUCTIONS: dict[ClaimObjective, str] = {
    ClaimObjective.IDENTITY: """OBJECTIVE: identity.
Extract only scholarship name, provider_name, destination country_code, aliases, intake_year, and
named administering institutions. Do not enumerate programmes, routes, requirements, or benefits
in this pass. The scholarship title may contain a programme qualifier; preserve that qualifier only
when this official source is programme-specific. Use scholarship.country_code and scholarship.alias;
emit intake_year as cycle.intake_year and each administering body as its own institution entity.""",
    ClaimObjective.PROGRAMMES: """OBJECTIVE: programmes.
Extract every explicitly named scholarship programme/category. Emit name and degree_levels for
every programme; emit programme_type and display_order when stated. A programme-specific guideline
normally describes one programme: use the programme named in the official title and attach every
supported degree level to that programme. Exception: when an official table or list gives distinct
degree/category rows with different durations or requirements (for example Undergraduate, Masters,
and Doctoral), create one programme entity per row and give each row its own name, a degree_levels
list containing exactly that row's applicable level, and a stable key. Even one degree level must
use string_list_value, for example ["bachelors"], never string_value. Do not emit only an umbrella
programme in that case. Do not turn
enrollment statuses (regular/non-regular), definitions, explanatory notes, degree-course names,
majors, universities, or application routes into additional scholarship programmes. Use
unknown_objectives and partial coverage when the programme-to-degree mapping cannot be established.
Do not extract fields_of_study, duration, description, or application_route_keys in this pass.""",
    ClaimObjective.PROGRAMME_DETAILS: """OBJECTIVE: programme_details.
For every scholarship programme/category whose details are stated, emit only fields_of_study,
duration, description, and application_route_keys. Use the same stable programme entity keys and
supported scopes. For tables, keep each row atomic: attach the main study duration only to the
programme/category named in that row. Never combine durations from different rows or different
columns into one value. A preparatory/language-study duration is not an academic field of study and
must not replace the main programme duration. fields_of_study means actual academic disciplines,
not language-test requirements, degree labels, universities, or explanatory prose. Use a
string_list_value for fields_of_study and application_route_keys, and a single string_value for
duration. Do not repeat programme names or core degree/type fields.""",
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
For rule_type, operator, and unit use string_value exclusively. For value choose exactly one typed
value that matches the source; never populate two value slots in one atomic claim. Give each
separate requirement or exception its own stable eligibility entity_key; never reuse the programme
key as the entity_key for multiple rules.
For the required field use boolean_value only, never copy requirement prose into string_value.
Preserve programme, route, cycle, and institution scope. Do not extract documents in this pass.""",
    ClaimObjective.ELIGIBILITY_CONTEXT: """OBJECTIVE: eligibility_context.
For every eligibility rule whose context is stated, emit only condition, is_exclusion, and notes.
Use the same stable eligibility entity keys and programme/route/cycle/institution scopes supported
by the source. Do not repeat core rule fields or invent exclusions and conditions.""",
    ClaimObjective.DOCUMENTS_CORE: """OBJECTIVE: documents_core.
Extract the complete required-document table/list, including conditional documents. For each
document emit only name and display_order when stated. Preserve programme, route, cycle, and
institution scope. Do not summarize a multi-item list into one document.""",
    ClaimObjective.DOCUMENTS_REQUIREMENTS: """OBJECTIVE: documents_requirements.
For every document whose requirement semantics are stated, emit only required, condition, and
submission_stage. Use the same stable document entity keys and programme/route/cycle/institution
scopes supported by the source. An if-applicable item is conditional, not universally required.
For required use boolean_value only: true for a mandatory document and false for an explicitly
optional or conditional document. Put the condition itself in condition using string_value. Never
copy a document name or sentence into the required value. Do not repeat document names.""",
    ClaimObjective.DOCUMENTS_COUNTS: """OBJECTIVE: documents_counts.
For every document whose copy or version details are stated, emit only original_count, copy_count,
and form_year. Use the same stable document entity keys and programme/route/cycle/institution scopes
supported by the source. These three fields use integer_value only. If an explicit numeric count or
four-digit form year is absent, emit no claim for that field; never copy document prose into a count
value. Do not repeat document names or invent zero counts and form years.""",
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
Extract application or document submission cutoffs as deadline entities. Every deadline must have
deadline_type plus deadline_at or deadline_text. Arrival windows,
screening periods, result dates, study periods, and other milestones are event entities, never
application deadlines. When the source delegates the exact deadline to an embassy, university,
national agency, or programme, emit that official rule as deadline_text, set deadline_type to
application_submission, and set varies_by to the stated authority or route. For deadlines emit
deadline_at or deadline_text, deadline_type, precision, timezone, varies_by, label, and notes. For
events emit event_type, starts_at, ends_at or date_text, precision, timezone, label, notes, and
display_order. Extract the complete ordered application process as step entities: every step must
have title and display_order, including document submission, screening, provisional acceptance,
placement, and final selection when stated. Do not mark coverage complete when a stated deadline is
missing deadline_type or when a stated application/selection process has no step titles. Produce
the step title claims before optional event details and resource descriptions.
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
        }
    ),
    ClaimObjective.PROGRAMMES: frozenset({ClaimEntityType.PROGRAMME}),
    ClaimObjective.PROGRAMME_DETAILS: frozenset({ClaimEntityType.PROGRAMME}),
    ClaimObjective.ROUTES: frozenset({ClaimEntityType.TRACK, ClaimEntityType.INSTITUTION}),
    ClaimObjective.ELIGIBILITY: frozenset({ClaimEntityType.ELIGIBILITY}),
    ClaimObjective.ELIGIBILITY_CONTEXT: frozenset({ClaimEntityType.ELIGIBILITY}),
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
    ClaimObjective.ELIGIBILITY_CONTEXT: frozenset({"condition", "is_exclusion", "notes"}),
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
    name = "azure_openai"

    def __init__(
        self,
        settings: Settings,
        *,
        credential: Any | None = None,
        opener: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        endpoint = settings.catalogue_ai_endpoint
        if not endpoint or not settings.catalogue_ai_model:
            raise ExtractionProviderUnavailable("Azure catalogue extraction is not configured")
        self.settings = settings
        self.model = settings.catalogue_ai_model
        self.request_url = azure_openai_request_url(endpoint)
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
        bounded = source_text[: self.settings.catalogue_ai_max_input_characters]
        prompt_text = _objective_source_text(bounded, objective)
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
        started = time.perf_counter()
        last_error: BaseException | None = None
        for attempt in range(self.settings.catalogue_ai_max_retries + 1):
            try:
                token = self.credential.get_token(self.settings.catalogue_ai_token_scope).token
                request = urllib.request.Request(
                    self.request_url,
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
                result = self._parse(raw, started)
                result.output = _normalize_claim_output(result.output, bounded, objective=objective)
                return result
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = exc
            if attempt < self.settings.catalogue_ai_max_retries:
                self.sleeper(
                    extraction_retry_delay(
                        last_error,
                        attempt=attempt,
                        maximum=self.settings.catalogue_ai_max_retry_delay_seconds,
                    )
                )
        if isinstance(last_error, TimeoutError):
            raise ExtractionProviderTimeout("Azure claim extraction timed out") from last_error
        if isinstance(last_error, urllib.error.HTTPError) and last_error.code == 429:
            raise ExtractionProviderRateLimited(
                "Azure claim extraction rate limit was exhausted"
            ) from last_error
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
            choice = response["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                raise ClaimOutputTruncated(
                    "Model output reached the configured token limit", usage=usage
                )
            if finish_reason != "stop":
                raise ExtractionSchemaError(
                    "Model claim extraction did not complete normally", usage=usage
                )
            if message.get("refusal"):
                raise ExtractionSchemaError("Model refused the claim extraction", usage=usage)
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
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExtractionSchemaError(
                "Azure claim response did not match the strict schema", usage=usage
            ) from exc
        return ClaimExtractionResult(output=output, usage=usage)


def _drop_invalid_atomic_claims(payload: object) -> tuple[object, list[str], int]:
    if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
        return payload, [], 0
    valid: list[object] = []
    invalid: list[str] = []
    placeholders = 0
    for raw_claim in payload["claims"]:
        _coerce_typed_claim_value(raw_claim)
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


def _coerce_typed_claim_value(raw_claim: object) -> None:
    """Resolve harmless structured-output type duplication by field semantics."""

    if not isinstance(raw_claim, dict) or not isinstance(raw_claim.get("value"), dict):
        return
    field_path = str(raw_claim.get("field_path", "")).strip().casefold()
    value = raw_claim["value"]
    preferred: str | None = None
    if field_path in {
        "copy_count",
        "display_order",
        "form_year",
        "intake_year",
        "original_count",
    }:
        preferred = "integer_value"
        if value.get(preferred) is None:
            raw = value.get("string_value")
            if isinstance(raw, str):
                normalized = raw.strip()
                if normalized.isdigit():
                    value[preferred] = int(normalized)
                elif field_path == "intake_year":
                    cycle_match = re.fullmatch(
                        r"((?:19|20)\d{2})\s*[-/]\s*(?:\d{2}|(?:19|20)\d{2})",
                        normalized,
                    )
                    if cycle_match is not None:
                        value[preferred] = int(cycle_match.group(1))
    elif field_path in {"is_exclusion", "required"}:
        preferred = "boolean_value"
    elif field_path == "amount":
        preferred = "decimal_value"
    elif field_path in {"application_route_keys", "degree_levels", "fields_of_study"}:
        preferred = "string_list_value"
        if value.get(preferred) is None:
            raw = value.get("string_value")
            if isinstance(raw, str) and raw.strip():
                value[preferred] = [raw.strip()]
    elif field_path != "value" and value.get("string_value") is not None:
        preferred = "string_value"
    if preferred is None or value.get(preferred) is None:
        return
    for key in (
        "string_value",
        "decimal_value",
        "integer_value",
        "boolean_value",
        "string_list_value",
    ):
        if key != preferred:
            value[key] = None


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
    passthrough_characters: int = 40_000,
    target_evidence_characters: int = 60_000,
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
    normalized_claims = [
        _normalize_claim_shape(item, objective=objective) for item in output.claims
    ]
    normalized_claims = _normalize_timeline_entity_groups(normalized_claims)
    if objective is ClaimObjective.PROGRAMMES:
        normalized_claims = _complete_programme_degree_levels(normalized_claims)
    if objective is ClaimObjective.PROGRAMME_DETAILS:
        normalized_claims = _normalize_programme_duration_units(
            normalized_claims,
            source_text,
        )
    normalized_claims = _disambiguate_eligibility_keys(normalized_claims)
    normalized_claims = _disambiguate_funding_keys(normalized_claims)
    if objective is ClaimObjective.ELIGIBILITY:
        normalized_claims = _complete_eligibility_values(normalized_claims)
    if objective is ClaimObjective.APPLICATION_TIMELINE:
        normalized_claims = _complete_application_deadline_claims(normalized_claims)
    claims = [
        _bind_unique_evidence_span(item, source_text)
        for item in normalized_claims
        if item.entity_type in allowed
        and (allowed_fields is None or item.field_path in allowed_fields)
    ]
    claims = [_repair_numeric_evidence(item, source_text) for item in claims]
    claims = claims[:48]
    warnings = list(output.warnings)
    allowed_count = sum(
        item.entity_type in allowed
        and (allowed_fields is None or item.field_path in allowed_fields)
        for item in normalized_claims
    )
    if allowed_count > len(claims):
        warnings.append(f"claim_limit_applied:{allowed_count}:48")
    return output.model_copy(
        update={
            "objective": objective,
            "claims": claims,
            "warnings": warnings,
        }
    )


def _normalize_claim_shape(
    claim: ExtractedClaim,
    *,
    objective: ClaimObjective,
) -> ExtractedClaim:
    if claim.field_path in {"application_route_keys", "degree_levels", "fields_of_study"}:
        primitive = claim.value.primitive()
        if isinstance(primitive, str) and primitive.strip():
            claim = claim.model_copy(
                update={
                    "value": ClaimValue(
                        string_value=None,
                        decimal_value=None,
                        integer_value=None,
                        boolean_value=None,
                        string_list_value=[primitive.strip()],
                    )
                }
            )
    if claim.entity_type is ClaimEntityType.PROGRAMME and claim.field_path == "degree_levels":
        key_levels = _programme_degree_signals(claim.entity_key)
        if len(key_levels) == 1:
            claim = claim.model_copy(
                update={
                    "value": ClaimValue(
                        string_value=None,
                        decimal_value=None,
                        integer_value=None,
                        boolean_value=None,
                        string_list_value=sorted(key_levels),
                    ),
                    "basis": "normalized",
                }
            )
    if claim.entity_type is ClaimEntityType.CYCLE and claim.field_path == "intake_year":
        value = claim.value.primitive()
        if isinstance(value, str):
            cycle_match = re.fullmatch(
                r"\s*((?:19|20)\d{2})\s*[-/]\s*(?:\d{2}|(?:19|20)\d{2})\s*",
                value,
            )
            if cycle_match is not None:
                claim = claim.model_copy(
                    update={
                        "value": ClaimValue(
                            string_value=None,
                            decimal_value=None,
                            integer_value=int(cycle_match.group(1)),
                            boolean_value=None,
                            string_list_value=None,
                        )
                    }
                )
    if (
        claim.field_path == "required"
        and isinstance(claim.value.primitive(), str)
        and objective in {
            ClaimObjective.ELIGIBILITY,
            ClaimObjective.DOCUMENTS_REQUIREMENTS,
        }
    ):
        requirement_text = f"{claim.value.primitive()} {claim.excerpt}".casefold()
        explicitly_conditional = bool(
            re.search(
                r"\b(?:if|when|where) applicable\b|\boptional\b|\bnot required\b",
                requirement_text,
            )
        )
        claim = claim.model_copy(
            update={
                "value": ClaimValue(
                    string_value=None,
                    decimal_value=None,
                    integer_value=None,
                    boolean_value=not explicitly_conditional,
                    string_list_value=None,
                )
            }
        )
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
    if claim.entity_type is ClaimEntityType.DEADLINE and claim.field_path == "date_text":
        if _scheduled_event_evidence(claim.excerpt):
            return claim.model_copy(update={"entity_type": ClaimEntityType.EVENT})
        if re.search(
            r"\b(?:deadline|cutoff|cut-off|submit by|no later than|until\s+"
            r"(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            claim.excerpt,
            re.I,
        ):
            return claim.model_copy(update={"field_path": "deadline_text"})
        return claim.model_copy(update={"field_path": "deadline_text"})
    if (
        claim.entity_type is ClaimEntityType.DEADLINE
        and claim.field_path == "deadline_text"
        and (
            re.search(
                r"\b(?:arriv\w*|depart\w*|screening|notification of result|"
                r"scholarship period|study period)\b",
                claim.excerpt,
                re.I,
            )
            or _scheduled_event_evidence(claim.excerpt)
        )
        and not re.search(
            r"\b(?:deadline|cutoff|cut-off|submit by|no later than)\b",
            claim.excerpt,
            re.I,
        )
    ):
        return claim.model_copy(
            update={"entity_type": ClaimEntityType.EVENT, "field_path": "date_text"}
        )
    if claim.entity_type is ClaimEntityType.FUNDING and claim.scope.programme_key:
        programme_levels = _programme_degree_signals(claim.scope.programme_key)
        evidence_levels = _programme_degree_signals(claim.excerpt)
        if programme_levels and not programme_levels.intersection(evidence_levels):
            claim = claim.model_copy(
                update={
                    "scope": claim.scope.model_copy(update={"programme_key": None})
                }
            )
    return claim


def _programme_degree_signals(value: str) -> set[str]:
    value = re.sub(r"[_-]+", " ", value)
    signals: set[str] = set()
    if re.search(r"\b(?:bachelor(?:'?s)?|undergraduate)\b", value, re.I):
        signals.add("bachelors")
    if re.search(r"\b(?:master(?:'?s)?|postgraduate)\b", value, re.I):
        signals.add("masters")
    if re.search(r"\b(?:ph\.?d\.?|doctoral|doctorate)\b", value, re.I):
        signals.add("phd")
    if re.search(r"\b(?:general|senior) scholars?\b|\bnon[ -]?degree\b", value, re.I):
        signals.add("non_degree")
    return signals


def _complete_programme_degree_levels(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    """Fill an explicit degree/category mapping omitted by structured output."""

    result = list(claims)
    grouped: dict[str, list[ExtractedClaim]] = defaultdict(list)
    for claim in claims:
        if claim.entity_type is ClaimEntityType.PROGRAMME:
            grouped[claim.entity_key].append(claim)
    for items in grouped.values():
        if any(item.field_path == "degree_levels" for item in items):
            continue
        name_claim = next((item for item in items if item.field_path == "name"), None)
        if name_claim is None:
            continue
        degree_levels = sorted(
            _programme_degree_signals(
                f"{name_claim.entity_key} {name_claim.value.primitive()} {name_claim.excerpt}"
            )
        )
        if not degree_levels:
            continue
        result.append(
            name_claim.model_copy(
                update={
                    "field_path": "degree_levels",
                    "value": ClaimValue(
                        string_value=None,
                        decimal_value=None,
                        integer_value=None,
                        boolean_value=None,
                        string_list_value=degree_levels,
                    ),
                    "basis": "normalized",
                }
            )
        )
    return result


def _normalize_programme_duration_units(
    claims: list[ExtractedClaim], source_text: str
) -> list[ExtractedClaim]:
    """Retain a table-header year unit when a row contains only a numeric range."""

    if re.search(r"\b(?:study|duration)\s*\(years?\)", source_text, re.I) is None:
        return claims
    result: list[ExtractedClaim] = []
    for claim in claims:
        primitive = claim.value.primitive()
        if (
            claim.entity_type is ClaimEntityType.PROGRAMME
            and claim.field_path == "duration"
            and isinstance(primitive, str)
            and re.fullmatch(
                r"\s*\d+(?:\.\d+)?\s*[-\u2013\u2014]\s*\d+(?:\.\d+)?\s*",
                primitive,
            )
        ):
            claim = claim.model_copy(
                update={
                    "value": ClaimValue(
                        string_value=f"{primitive.strip()} years",
                        decimal_value=None,
                        integer_value=None,
                        boolean_value=None,
                        string_list_value=None,
                    ),
                    "basis": "normalized",
                }
            )
        result.append(claim)
    return result


def _scheduled_event_evidence(excerpt: str) -> bool:
    if re.search(
        r"\b(?:test|exam(?:ination)?|assessment|csca)\b.{0,35}\bdeadline\b|"
        r"\bdeadline\b.{0,35}\b(?:test|exam(?:ination)?|assessment|csca)\b",
        excerpt,
        re.I,
    ):
        return False
    return bool(
        re.search(r"\b(?:test|exam(?:ination)?|assessment|csca)\b", excerpt, re.I)
        and re.search(
            r"\b(?:date|dates|held|scheduled|announced|"
            r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
            r"dec(?:ember)?|(?:19|20)\d{2})\b",
            excerpt,
            re.I,
        )
    )


def _normalize_timeline_entity_groups(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    """Move every field for a scheduled event out of the deadline namespace."""

    event_keys = {
        claim.entity_key
        for claim in claims
        if claim.entity_type is ClaimEntityType.EVENT
        or (
            claim.entity_type is ClaimEntityType.DEADLINE
            and _scheduled_event_evidence(claim.excerpt)
        )
    }
    result: list[ExtractedClaim] = []
    for claim in claims:
        if claim.entity_type is not ClaimEntityType.DEADLINE or claim.entity_key not in event_keys:
            result.append(claim)
            continue
        field_path = {
            "deadline_at": "starts_at",
            "deadline_text": "date_text",
            "deadline_type": "event_type",
            "varies_by": "notes",
        }.get(claim.field_path, claim.field_path)
        value = claim.value
        basis = claim.basis
        if field_path == "event_type":
            value = ClaimValue(
                string_value="assessment",
                decimal_value=None,
                integer_value=None,
                boolean_value=None,
                string_list_value=None,
            )
            basis = "normalized"
        result.append(
            claim.model_copy(
                update={
                    "entity_type": ClaimEntityType.EVENT,
                    "field_path": field_path,
                    "value": value,
                    "basis": basis,
                }
            )
        )
    return result


def _disambiguate_eligibility_keys(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    """Split a reused generic key when its evidence clearly describes distinct rules."""

    grouped: dict[str, list[ExtractedClaim]] = {}
    for claim in claims:
        if claim.entity_type is ClaimEntityType.ELIGIBILITY:
            grouped.setdefault(claim.entity_key, []).append(claim)
    ambiguous_keys: set[str] = set()
    for entity_key, items in grouped.items():
        for field_path in ("rule_type", "operator", "value"):
            values = {
                json.dumps(item.value.model_dump(mode="json"), sort_keys=True)
                for item in items
                if item.field_path == field_path
            }
            if len(values) > 1:
                ambiguous_keys.add(entity_key)
                break
    if not ambiguous_keys:
        return claims
    result: list[ExtractedClaim] = []
    for claim in claims:
        if claim.entity_type is ClaimEntityType.ELIGIBILITY and claim.entity_key in ambiguous_keys:
            evidence_key = re.sub(r"\s+", " ", claim.excerpt).strip().casefold()
            suffix = hashlib.sha256(evidence_key.encode()).hexdigest()[:12]
            prefix = claim.entity_key[: 120 - len(suffix) - 1]
            claim = claim.model_copy(update={"entity_key": f"{prefix}_{suffix}"})
        result.append(claim)
    return result


def _complete_eligibility_values(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    """Use the exact cited requirement when a typed rule omitted its value field."""

    result = list(claims)
    grouped: dict[tuple[str, str], list[ExtractedClaim]] = {}
    for claim in claims:
        if claim.entity_type is ClaimEntityType.ELIGIBILITY:
            scope_key = json.dumps(claim.scope.model_dump(), sort_keys=True)
            grouped.setdefault((claim.entity_key, scope_key), []).append(claim)
    for items in grouped.values():
        fields = {item.field_path for item in items}
        if "rule_type" not in fields or "value" in fields:
            continue
        supporting = next(item for item in items if item.field_path == "rule_type")
        result.append(
            supporting.model_copy(
                update={
                    "field_path": "value",
                    "value": supporting.value.model_copy(
                        update={
                            "string_value": supporting.excerpt.strip(),
                            "decimal_value": None,
                            "integer_value": None,
                            "boolean_value": None,
                            "string_list_value": None,
                        }
                    ),
                    "basis": "normalized",
                }
            )
        )
    return result


def _disambiguate_funding_keys(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    """Keep all fields for one benefit together while splitting distinct benefits."""

    generic_keys = {"award", "benefit", "benefits", "funding", "scholarship"}

    def is_generic_key(entity_key: str) -> bool:
        lowered = entity_key.casefold()
        return lowered in generic_keys or bool(
            re.fullmatch(
                r"funding_(?:component_type|coverage_status|amount|currency|frequency|"
                r"description)_[0-9a-f]{12}",
                lowered,
            )
        )

    component_types: dict[tuple[str, str], set[str]] = {}
    for claim in claims:
        if (
            claim.entity_type is not ClaimEntityType.FUNDING
            or not is_generic_key(claim.entity_key)
            or claim.field_path != "component_type"
        ):
            continue
        scope_key = json.dumps(claim.scope.model_dump(), sort_keys=True)
        evidence_key = re.sub(r"\s+", " ", claim.excerpt).strip().casefold()
        component_types.setdefault((scope_key, evidence_key), set()).add(
            str(claim.value.primitive()).strip().casefold()
        )

    identities: dict[int, str] = {}
    groups: dict[tuple[str, str], set[str]] = {}
    for index, claim in enumerate(claims):
        if (
            claim.entity_type is not ClaimEntityType.FUNDING
            or not is_generic_key(claim.entity_key)
        ):
            continue
        scope_key = json.dumps(claim.scope.model_dump(), sort_keys=True)
        evidence_key = re.sub(r"\s+", " ", claim.excerpt).strip().casefold()
        evidence_components = component_types.get((scope_key, evidence_key), set())
        if len(evidence_components) == 1:
            identity = next(iter(evidence_components))
        elif claim.field_path == "component_type":
            identity = str(claim.value.primitive()).strip().casefold()
        else:
            identity = evidence_key
        identities[index] = identity
        groups.setdefault(("generic", scope_key), set()).add(identity)

    result: list[ExtractedClaim] = []
    for index, claim in enumerate(claims):
        scope_key = json.dumps(claim.scope.model_dump(), sort_keys=True)
        should_split = (
            claim.entity_type is ClaimEntityType.FUNDING
            and is_generic_key(claim.entity_key)
            and len(groups.get(("generic", scope_key), set())) > 1
        )
        if not should_split:
            result.append(claim)
            continue
        identity = identities[index]
        suffix = hashlib.sha256(identity.encode()).hexdigest()[:12]
        component_slug = re.sub(r"[^a-z0-9]+", "_", identity).strip("_")[:40]
        prefix = f"funding_{component_slug or 'component'}"
        result.append(
            claim.model_copy(update={"entity_key": f"{prefix}_{suffix}"})
        )
    return result


def _repair_numeric_evidence(claim: ExtractedClaim, source_text: str) -> ExtractedClaim:
    """Re-anchor a truncated numeric citation to the exact nearby source sentence."""

    raw_value = claim.value.primitive()
    if claim.entity_type is ClaimEntityType.CYCLE and claim.field_path == "intake_year":
        digits = str(raw_value)
    elif claim.entity_type is ClaimEntityType.FUNDING and claim.field_path == "amount":
        digits = format(raw_value, "f")
        if "." in digits:
            digits = digits.rstrip("0").rstrip(".")
    else:
        return claim
    compact_excerpt = claim.excerpt.replace(",", "").replace(" ", "")
    if digits.replace(".", "") in compact_excerpt:
        return claim

    integer, dot, fraction = digits.partition(".")
    integer_pattern = r"[\s,]?".join(re.escape(character) for character in integer)
    number_pattern = rf"(?<!\d){integer_pattern}"
    if dot:
        number_pattern += rf"\.{re.escape(fraction)}"
    number_pattern += r"(?!\d)"
    matches = list(re.finditer(number_pattern, source_text))
    if not matches:
        return claim
    center = (claim.excerpt_start + claim.excerpt_end) // 2
    match = min(matches, key=lambda item: abs(item.start() - center))
    if abs(match.start() - center) > 1_000:
        return claim
    start = max(
        source_text.rfind(". ", max(0, match.start() - 500), match.start()) + 2,
        0,
    )
    sentence_end = source_text.find(". ", match.end(), min(len(source_text), match.end() + 500))
    end = sentence_end + 1 if sentence_end >= 0 else min(len(source_text), match.end() + 220)
    excerpt = source_text[start:end].strip()
    exact_start = source_text.find(excerpt, start, end + 1)
    if not excerpt or exact_start < 0:
        return claim
    return claim.model_copy(
        update={
            "excerpt": excerpt,
            "excerpt_start": exact_start,
            "excerpt_end": exact_start + len(excerpt),
        }
    )


def _complete_application_deadline_claims(
    claims: list[ExtractedClaim],
) -> list[ExtractedClaim]:
    """Add deterministic required fields for explicit application-deadline statements."""

    result = list(claims)
    deadlines: dict[str, list[ExtractedClaim]] = {}
    for claim in claims:
        if claim.entity_type is ClaimEntityType.DEADLINE:
            deadlines.setdefault(claim.entity_key, []).append(claim)
    for items in deadlines.values():
        supporting = next(
            (
                item
                for item in items
                if re.search(
                    r"\b(?:deadline|cutoff|cut-off|submit by|no later than|until\s+"
                    r"(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
                    item.excerpt,
                    re.I,
                )
            ),
            None,
        )
        if supporting is None:
            continue
        fields = {item.field_path for item in items}
        if not {"deadline_at", "deadline_text"} & fields:
            result.append(
                supporting.model_copy(
                    update={
                        "field_path": "deadline_text",
                        "value": supporting.value.model_copy(
                            update={
                                "string_value": supporting.excerpt.strip(),
                                "decimal_value": None,
                                "integer_value": None,
                                "boolean_value": None,
                                "string_list_value": None,
                            }
                        ),
                        "basis": "normalized",
                    }
                )
            )
        if "deadline_type" not in fields:
            deadline_type = (
                "application_submission"
                if re.search(
                    r"\b(?:application|document|form|submit|submission)\b",
                    supporting.excerpt,
                    re.I,
                )
                else "other"
            )
            result.append(
                supporting.model_copy(
                    update={
                        "field_path": "deadline_type",
                        "value": supporting.value.model_copy(
                            update={
                                "string_value": deadline_type,
                                "decimal_value": None,
                                "integer_value": None,
                                "boolean_value": None,
                                "string_list_value": None,
                            }
                        ),
                        "basis": "normalized",
                    }
                )
            )
    return result


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
        normalized_source, source_positions = _collapse_evidence_whitespace(source_text)
        normalized_excerpt, _ = _collapse_evidence_whitespace(claim.excerpt)
        normalized_starts: list[int] = []
        position = normalized_source.find(normalized_excerpt)
        while position >= 0 and len(normalized_starts) < 100:
            normalized_starts.append(position)
            position = normalized_source.find(normalized_excerpt, position + 1)
        if not normalized_starts or not normalized_excerpt:
            canonical_source, canonical_positions = _canonicalize_evidence_text(source_text)
            canonical_excerpt, _ = _canonicalize_evidence_text(claim.excerpt)
            canonical_starts = _all_occurrences(canonical_source, canonical_excerpt)
            if canonical_starts and canonical_excerpt:
                distance = min(
                    abs(canonical_positions[start] - claim.excerpt_start)
                    for start in canonical_starts
                )
                nearest = [
                    start
                    for start in canonical_starts
                    if abs(canonical_positions[start] - claim.excerpt_start) == distance
                ]
                if len(nearest) == 1:
                    canonical_start = nearest[0]
                    start = canonical_positions[canonical_start]
                    final_index = canonical_start + len(canonical_excerpt) - 1
                    end = canonical_positions[final_index] + 1
                    return claim.model_copy(
                        update={
                            "excerpt": source_text[start:end],
                            "excerpt_start": start,
                            "excerpt_end": end,
                        }
                    )
            anchor = _unique_evidence_anchor(normalized_source, normalized_excerpt)
            if anchor is None:
                return claim
            anchor_start, anchor_end = anchor
            start = source_positions[anchor_start]
            end = source_positions[anchor_end - 1] + 1
            return claim.model_copy(
                update={
                    "excerpt": source_text[start:end],
                    "excerpt_start": start,
                    "excerpt_end": end,
                }
            )
        distance = min(
            abs(source_positions[start] - claim.excerpt_start)
            for start in normalized_starts
        )
        nearest = [
            start
            for start in normalized_starts
            if abs(source_positions[start] - claim.excerpt_start) == distance
        ]
        if len(nearest) != 1:
            return claim
        nearest_normalized = nearest[0]
        start = source_positions[nearest_normalized]
        final_index = nearest_normalized + len(normalized_excerpt) - 1
        end = source_positions[final_index] + 1
        return claim.model_copy(
            update={
                "excerpt": source_text[start:end],
                "excerpt_start": start,
                "excerpt_end": end,
            }
        )
    distance = min(abs(start - claim.excerpt_start) for start in starts)
    nearest = [start for start in starts if abs(start - claim.excerpt_start) == distance]
    if len(nearest) != 1:
        return claim
    start = nearest[0]
    return claim.model_copy(
        update={"excerpt_start": start, "excerpt_end": start + len(claim.excerpt)}
    )


def _collapse_evidence_whitespace(value: str) -> tuple[str, list[int]]:
    collapsed: list[str] = []
    positions: list[int] = []
    in_whitespace = False
    for index, character in enumerate(value):
        if character.isspace():
            if collapsed and not in_whitespace:
                collapsed.append(" ")
                positions.append(index)
            in_whitespace = True
            continue
        collapsed.append(character)
        positions.append(index)
        in_whitespace = False
    if collapsed and collapsed[-1] == " ":
        collapsed.pop()
        positions.pop()
    return "".join(collapsed), positions


def _canonicalize_evidence_text(value: str) -> tuple[str, list[int]]:
    """Normalize model/PDF punctuation while retaining original source offsets."""

    canonical: list[str] = []
    positions: list[int] = []
    in_whitespace = False
    apostrophes = {"'", "\u2019", "\u2018", "`", "\x02", "\x19"}
    hyphens = {"-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014"}
    for index, character in enumerate(value):
        if character.isspace():
            if canonical and not in_whitespace:
                canonical.append(" ")
                positions.append(index)
            in_whitespace = True
            continue
        in_whitespace = False
        normalized = "'" if character in apostrophes else "-" if character in hyphens else character
        canonical.append(normalized)
        positions.append(index)
    if canonical and canonical[-1] == " ":
        canonical.pop()
        positions.pop()
    return "".join(canonical), positions


def _all_occurrences(source: str, excerpt: str) -> list[int]:
    if not excerpt:
        return []
    starts: list[int] = []
    position = source.find(excerpt)
    while position >= 0 and len(starts) < 100:
        starts.append(position)
        position = source.find(excerpt, position + 1)
    return starts


def _unique_evidence_anchor(source: str, excerpt: str) -> tuple[int, int] | None:
    """Find a substantial verbatim fragment when a PDF extractor changed separators."""

    for size in (240, 180, 120, 80, 60, 40):
        if len(excerpt) < size:
            continue
        starts = sorted(
            {
                0,
                len(excerpt) - size,
                *range(0, len(excerpt) - size + 1, max(40, size // 2)),
            }
        )
        for excerpt_start in starts:
            fragment = excerpt[excerpt_start : excerpt_start + size]
            source_start = source.find(fragment)
            if source_start < 0:
                continue
            if source.find(fragment, source_start + 1) >= 0:
                continue
            return source_start, source_start + size
    return None


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
