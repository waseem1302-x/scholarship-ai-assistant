"""Durable orchestration for one logical catalogue extraction job.

Provider adapters are single-attempt transports.  This module owns retries and ensures every
physical attempt has a committed ledger identity before network I/O begins.  Cost reservations use
an upper bound and are reconciled to exact usage when available; ambiguous post-dispatch failures
retain their reservation as an unknown-potentially-billable upper bound.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypeVar

from app.core.config import Settings
from app.modules.catalogue_ingestion.models import (
    CatalogueCandidate,
    CatalogueCandidateSource,
    CatalogueIngestionRun,
    CatalogueSourceArtifact,
)
from app.modules.catalogue_ingestion.provider import estimate_cost
from app.modules.catalogue_ingestion.provider_attempts import ProviderFailureClass
from app.modules.catalogue_ingestion.provider_config import (
    CATALOGUE_CONFIGURATION_REVISION,
    catalogue_configuration_fingerprint,
    catalogue_provider_profile,
)
from app.modules.catalogue_ingestion.provider_transport import (
    ExtractionProviderError,
    extraction_retry_delay,
)
from app.modules.catalogue_ingestion.repository import (
    CatalogueIngestionRepository,
    ProviderBudgetReservationError,
)

T = TypeVar("T")

CATALOGUE_PROVIDER_PARSER_VERSION = "catalogue-provider-parser.v1"
CATALOGUE_PROVIDER_NORMALIZER_VERSION = "catalogue-provider-normalizer.v1"


class ProviderExecutionBudgetExhausted(RuntimeError):
    pass


class ProviderConfigurationDrift(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderExecutionResult:
    result: Any
    provider_attempt_id: uuid.UUID


class CatalogueProviderExecutor:
    def __init__(
        self,
        repository: CatalogueIngestionRepository,
        settings: Settings,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.sleeper = sleeper

    def execute(
        self,
        *,
        run: CatalogueIngestionRun,
        candidate: CatalogueCandidate,
        source: CatalogueCandidateSource,
        artifact: CatalogueSourceArtifact | None,
        provider: Any,
        schema_version: str,
        prompt_hash: str,
        content_hash: str,
        source_text: str,
        invoke: Callable[[], T],
        objective: str | None = None,
        objective_bundle: list[str] | None = None,
        evidence_block_keys: list[str] | None = None,
        parser_version: str = CATALOGUE_PROVIDER_PARSER_VERSION,
        normalizer_version: str = CATALOGUE_PROVIDER_NORMALIZER_VERSION,
    ) -> ProviderExecutionResult:
        """Execute a logical job with orchestration-owned retries and durable accounting."""

        if provider.name == "azure_openai":
            self._require_approved_configuration(run)

        job_key = provider_job_key(
            candidate_id=candidate.id,
            source_id=source.id,
            source_artifact_id=artifact.id if artifact is not None else None,
            content_hash=content_hash,
            schema_version=schema_version,
            prompt_hash=prompt_hash,
            objective=objective,
        )
        max_retries = self.settings.catalogue_ai_max_retries if provider.name == "azure_openai" else 0
        profile = catalogue_provider_profile(self.settings)
        projected_input_tokens = max(1, min(len(source_text), run.max_input_characters) // 4)
        reserved_cost_upper = estimate_cost(
            projected_input_tokens,
            run.max_output_tokens,
            input_per_million=self.settings.catalogue_ai_input_cost_per_million,
            output_per_million=self.settings.catalogue_ai_output_cost_per_million,
        )

        last_error: ExtractionProviderError | None = None
        for orchestration_attempt in range(max_retries + 1):
            try:
                ledger = self.repository.reserve_provider_attempt(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    source_id=source.id,
                    source_artifact_id=artifact.id if artifact is not None else None,
                    extraction_job_key=job_key,
                    objective=objective,
                    objective_bundle=list(objective_bundle or ([objective] if objective else [])),
                    evidence_block_keys=list(evidence_block_keys or []),
                    provider=provider.name,
                    deployment=profile.extraction_deployment,
                    model=provider.model,
                    prompt_hash=prompt_hash,
                    schema_version=schema_version,
                    parser_version=parser_version,
                    normalizer_version=normalizer_version,
                    worker_id=candidate.claimed_by,
                    lease_token=_lease_fingerprint(candidate),
                    reserved_cost_upper=reserved_cost_upper,
                )
            except ProviderBudgetReservationError as exc:
                raise ProviderExecutionBudgetExhausted(str(exc)) from exc

            # This commit is the durable pre-I/O boundary.  If the worker disappears after this
            # point, the ledger still proves that dispatch had begun and the reservation remains.
            self.repository.mark_provider_attempt_dispatching(ledger)
            try:
                result = invoke()
            except ExtractionProviderError as exc:
                last_error = exc
                usage = exc.usage
                exact_cost = (
                    Decimal(str(usage.estimated_cost)) if usage is not None else None
                )
                self.repository.fail_provider_attempt(
                    ledger,
                    failure_class=_failure_class(exc.failure_class),
                    error_code=exc.code,
                    safe_error_detail=f"{type(exc).__name__}:{exc.code}",
                    provider_request_id=exc.provider_request_id,
                    dispatch_occurred=bool(exc.dispatch_occurred),
                    potentially_billable=bool(exc.potentially_billable),
                    input_tokens=(int(usage.input_tokens) if usage is not None else None),
                    output_tokens=(int(usage.output_tokens) if usage is not None else None),
                    exact_cost=exact_cost,
                )
                setattr(exc, "provider_attempt_id", ledger.id)
                if not exc.retryable or orchestration_attempt >= max_retries:
                    raise
                self.sleeper(
                    extraction_retry_delay(
                        exc,
                        attempt=orchestration_attempt,
                        maximum=self.settings.catalogue_ai_max_retry_delay_seconds,
                    )
                )
                continue
            except Exception as exc:
                wrapped = ExtractionProviderError(
                    "Catalogue provider call failed unexpectedly",
                    failure_class="unknown_potentially_billable_failure",
                    retryable=False,
                    potentially_billable=True,
                    dispatch_occurred=True,
                )
                self.repository.fail_provider_attempt(
                    ledger,
                    failure_class=ProviderFailureClass.UNKNOWN_POTENTIALLY_BILLABLE_FAILURE,
                    error_code=wrapped.code,
                    safe_error_detail=f"{type(exc).__name__}:unexpected_provider_failure",
                    provider_request_id=None,
                    dispatch_occurred=True,
                    potentially_billable=True,
                )
                setattr(wrapped, "provider_attempt_id", ledger.id)
                raise wrapped from exc

            usage = getattr(result, "usage", None)
            if usage is None:
                wrapped = ExtractionProviderError(
                    "Catalogue provider result omitted usage accounting",
                    failure_class="malformed_provider_response",
                    retryable=False,
                    potentially_billable=True,
                    dispatch_occurred=True,
                )
                self.repository.fail_provider_attempt(
                    ledger,
                    failure_class=ProviderFailureClass.MALFORMED_PROVIDER_RESPONSE,
                    error_code=wrapped.code,
                    safe_error_detail="provider_result:missing_usage",
                    provider_request_id=None,
                    dispatch_occurred=True,
                    potentially_billable=True,
                )
                setattr(wrapped, "provider_attempt_id", ledger.id)
                raise wrapped

            self.repository.complete_provider_attempt(
                ledger,
                input_tokens=int(usage.input_tokens),
                output_tokens=int(usage.output_tokens),
                exact_cost=Decimal(str(usage.estimated_cost)),
                provider_request_id=getattr(usage, "provider_request_id", None),
            )
            return ProviderExecutionResult(result=result, provider_attempt_id=ledger.id)

        assert last_error is not None
        raise last_error

    def _require_approved_configuration(self, run: CatalogueIngestionRun) -> None:
        effective = catalogue_configuration_fingerprint(self.settings)
        if (
            run.configuration_revision != CATALOGUE_CONFIGURATION_REVISION
            or run.configuration_fingerprint != effective
        ):
            raise ProviderConfigurationDrift(
                "catalogue provider configuration does not match the run receipt"
            )


def provider_job_key(
    *,
    candidate_id: uuid.UUID,
    source_id: uuid.UUID,
    source_artifact_id: uuid.UUID | None,
    content_hash: str,
    schema_version: str,
    prompt_hash: str,
    objective: str | None,
) -> str:
    payload = "|".join(
        (
            str(candidate_id),
            str(source_id),
            str(source_artifact_id or ""),
            content_hash,
            schema_version,
            prompt_hash,
            objective or "",
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _lease_fingerprint(candidate: CatalogueCandidate) -> str | None:
    if candidate.claimed_by is None or candidate.claimed_until is None:
        return None
    payload = f"{candidate.claimed_by}|{candidate.claimed_until.isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _failure_class(value: str) -> ProviderFailureClass:
    try:
        return ProviderFailureClass(value)
    except ValueError:
        return ProviderFailureClass.UNKNOWN_POTENTIALLY_BILLABLE_FAILURE
