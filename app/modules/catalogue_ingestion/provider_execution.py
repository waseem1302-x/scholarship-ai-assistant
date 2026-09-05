"""Durable orchestration for one logical catalogue extraction job.

Provider adapters are single-attempt transports. This module owns retries and ensures every physical
attempt has a committed ledger identity before network I/O begins. Cost reservations use an upper
bound and are reconciled to exact usage when available. Ambiguous post-dispatch failures retain
their reservation as an unknown-potentially-billable upper bound. Run and candidate fencing tokens
are validated before scheduling, dispatch transition, retry waits, and result reconciliation.
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
    CatalogueLeaseLost,
    ProviderBudgetReservationError,
)
from app.modules.catalogue_ingestion.scheduling import CatalogueProviderScheduler

T = TypeVar("T")

CATALOGUE_PROVIDER_PARSER_VERSION = "catalogue-provider-parser.v1"
CATALOGUE_PROVIDER_NORMALIZER_VERSION = "catalogue-provider-normalizer.v1"


class ProviderExecutionBudgetExhausted(RuntimeError):
    pass


class ProviderConfigurationDrift(RuntimeError):
    pass


class ProviderExecutionLeaseLost(RuntimeError):
    pass


class ProviderExecutionCancelled(RuntimeError):
    pass


class ProviderExecutionDeferred(RuntimeError):
    def __init__(self, reason: str, *, retry_after_seconds: float) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds


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
        self.scheduler = CatalogueProviderScheduler(repository.session, settings)

    def execute(
        self,
        *,
        run: CatalogueIngestionRun,
        run_lease_token: str,
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
        logical_job_key: str | None = None,
        max_output_tokens: int | None = None,
        parser_version: str = CATALOGUE_PROVIDER_PARSER_VERSION,
        normalizer_version: str = CATALOGUE_PROVIDER_NORMALIZER_VERSION,
        heartbeat: Callable[[], None] | None = None,
    ) -> ProviderExecutionResult:
        """Execute a logical job with orchestration-owned retries and fenced accounting.

        ``logical_job_key`` and ``max_output_tokens`` are optional Batch-5 planner inputs. Their
        absence preserves the historical single-objective job identity and conservative run-level
        output reservation used by older attempts and resumptions.
        """

        if provider.name == "azure_openai":
            self._require_approved_configuration(run)
        worker_id = candidate.claimed_by
        candidate_lease_token = candidate.lease_token
        if not worker_id or not candidate_lease_token:
            raise ProviderExecutionLeaseLost("candidate has no active fencing lease")

        if logical_job_key is not None:
            job_key = logical_job_key.strip()
            if not job_key or len(job_key) > 128:
                raise ValueError("logical provider job key must be 1-128 characters")
        else:
            job_key = provider_job_key(
                candidate_id=candidate.id,
                source_id=source.id,
                source_artifact_id=artifact.id if artifact is not None else None,
                content_hash=content_hash,
                schema_version=schema_version,
                prompt_hash=prompt_hash,
                objective=objective,
            )

        output_ceiling = run.max_output_tokens if max_output_tokens is None else max_output_tokens
        if output_ceiling < 1 or output_ceiling > run.max_output_tokens:
            raise ProviderExecutionBudgetExhausted("provider_output_token_budget_invalid")

        max_retries = (
            self.settings.catalogue_ai_max_retries if provider.name == "azure_openai" else 0
        )
        profile = catalogue_provider_profile(self.settings)
        projected_input_tokens = max(1, min(len(source_text), run.max_input_characters) // 4)
        reserved_cost_upper = estimate_cost(
            projected_input_tokens,
            output_ceiling,
            input_per_million=self.settings.catalogue_ai_input_cost_per_million,
            output_per_million=self.settings.catalogue_ai_output_cost_per_million,
        )

        last_error: ExtractionProviderError | None = None
        for orchestration_attempt in range(max_retries + 1):
            if provider.name == "azure_openai" and not self.settings.catalogue_ai_ingestion_enabled:
                raise ProviderExecutionCancelled("catalogue AI ingestion kill switch is disabled")
            self._heartbeat(heartbeat)
            admission = self.scheduler.admit(
                provider=provider.name,
                deployment=profile.extraction_deployment,
                endpoint_fingerprint=profile.endpoint_fingerprint,
                logical_job_key=job_key,
                run_id=run.id,
                candidate_id=candidate.id,
            )
            if not admission.allowed:
                retry_after_seconds = (
                    float(self.settings.catalogue_provider_circuit_open_seconds)
                    if admission.reason == "provider_circuit_open"
                    else 1.0
                )
                raise ProviderExecutionDeferred(
                    admission.reason,
                    retry_after_seconds=retry_after_seconds,
                )
            try:
                ledger = self.repository.reserve_provider_attempt(
                    run_id=run.id,
                    run_lease_token=run_lease_token,
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
                    worker_id=worker_id,
                    lease_token=candidate_lease_token,
                    reserved_cost_upper=reserved_cost_upper,
                )
            except ProviderBudgetReservationError as exc:
                raise ProviderExecutionBudgetExhausted(str(exc)) from exc
            except CatalogueLeaseLost as exc:
                raise ProviderExecutionLeaseLost(str(exc)) from exc

            try:
                self.repository.mark_provider_attempt_dispatching(
                    ledger,
                    worker_id=worker_id,
                    run_lease_token=run_lease_token,
                    candidate_lease_token=candidate_lease_token,
                )
            except CatalogueLeaseLost as exc:
                self.repository.record_provider_attempt_lease_loss(ledger)
                raise ProviderExecutionLeaseLost(str(exc)) from exc

            try:
                result = invoke()
            except ExtractionProviderError as exc:
                last_error = exc
                usage = exc.usage
                exact_cost = Decimal(str(usage.estimated_cost)) if usage is not None else None
                try:
                    self.repository.fail_provider_attempt(
                        ledger,
                        worker_id=worker_id,
                        run_lease_token=run_lease_token,
                        candidate_lease_token=candidate_lease_token,
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
                except CatalogueLeaseLost as lease_exc:
                    self.repository.record_provider_attempt_lease_loss(
                        ledger,
                        input_tokens=(int(usage.input_tokens) if usage is not None else None),
                        output_tokens=(int(usage.output_tokens) if usage is not None else None),
                        exact_cost=exact_cost,
                        provider_request_id=exc.provider_request_id,
                    )
                    raise ProviderExecutionLeaseLost(str(lease_exc)) from exc
                self.scheduler.record_failure(
                    provider=provider.name,
                    deployment=profile.extraction_deployment,
                    failure_class=_failure_class(exc.failure_class),
                    endpoint_fingerprint=profile.endpoint_fingerprint,
                    retry_after_seconds=exc.retry_after_seconds,
                )
                exc.provider_attempt_id = ledger.id
                if not exc.retryable or orchestration_attempt >= max_retries:
                    raise
                self._heartbeat(heartbeat)
                delay = extraction_retry_delay(
                    exc,
                    attempt=orchestration_attempt,
                    maximum=self.settings.catalogue_ai_max_retry_delay_seconds,
                )
                self.sleeper(delay)
                self._heartbeat(heartbeat)
                continue
            except Exception as exc:
                wrapped = ExtractionProviderError(
                    "Catalogue provider call failed unexpectedly",
                    failure_class="unknown_potentially_billable_failure",
                    retryable=False,
                    potentially_billable=True,
                    dispatch_occurred=True,
                )
                try:
                    self.repository.fail_provider_attempt(
                        ledger,
                        worker_id=worker_id,
                        run_lease_token=run_lease_token,
                        candidate_lease_token=candidate_lease_token,
                        failure_class=ProviderFailureClass.UNKNOWN_POTENTIALLY_BILLABLE_FAILURE,
                        error_code=wrapped.code,
                        safe_error_detail=f"{type(exc).__name__}:unexpected_provider_failure",
                        provider_request_id=None,
                        dispatch_occurred=True,
                        potentially_billable=True,
                    )
                except CatalogueLeaseLost as lease_exc:
                    self.repository.record_provider_attempt_lease_loss(ledger)
                    raise ProviderExecutionLeaseLost(str(lease_exc)) from exc
                self.scheduler.record_failure(
                    provider=provider.name,
                    deployment=profile.extraction_deployment,
                    failure_class=ProviderFailureClass.UNKNOWN_POTENTIALLY_BILLABLE_FAILURE,
                    endpoint_fingerprint=profile.endpoint_fingerprint,
                )
                wrapped.provider_attempt_id = ledger.id
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
                try:
                    self.repository.fail_provider_attempt(
                        ledger,
                        worker_id=worker_id,
                        run_lease_token=run_lease_token,
                        candidate_lease_token=candidate_lease_token,
                        failure_class=ProviderFailureClass.MALFORMED_PROVIDER_RESPONSE,
                        error_code=wrapped.code,
                        safe_error_detail="provider_result:missing_usage",
                        provider_request_id=None,
                        dispatch_occurred=True,
                        potentially_billable=True,
                    )
                except CatalogueLeaseLost as lease_exc:
                    self.repository.record_provider_attempt_lease_loss(ledger)
                    raise ProviderExecutionLeaseLost(str(lease_exc)) from wrapped
                self.scheduler.record_failure(
                    provider=provider.name,
                    deployment=profile.extraction_deployment,
                    failure_class=ProviderFailureClass.MALFORMED_PROVIDER_RESPONSE,
                    endpoint_fingerprint=profile.endpoint_fingerprint,
                )
                wrapped.provider_attempt_id = ledger.id
                raise wrapped

            try:
                self._heartbeat(heartbeat)
                self.repository.complete_provider_attempt(
                    ledger,
                    worker_id=worker_id,
                    run_lease_token=run_lease_token,
                    candidate_lease_token=candidate_lease_token,
                    input_tokens=int(usage.input_tokens),
                    output_tokens=int(usage.output_tokens),
                    exact_cost=Decimal(str(usage.estimated_cost)),
                    provider_request_id=getattr(usage, "provider_request_id", None),
                )
            except CatalogueLeaseLost as exc:
                self.repository.record_provider_attempt_lease_loss(
                    ledger,
                    input_tokens=int(usage.input_tokens),
                    output_tokens=int(usage.output_tokens),
                    exact_cost=Decimal(str(usage.estimated_cost)),
                    provider_request_id=getattr(usage, "provider_request_id", None),
                )
                raise ProviderExecutionLeaseLost(str(exc)) from exc
            self.scheduler.record_success(
                provider=provider.name,
                deployment=profile.extraction_deployment,
                endpoint_fingerprint=profile.endpoint_fingerprint,
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

    @staticmethod
    def _heartbeat(heartbeat: Callable[[], None] | None) -> None:
        if heartbeat is None:
            return
        try:
            heartbeat()
        except CatalogueLeaseLost as exc:
            raise ProviderExecutionLeaseLost(str(exc)) from exc


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


def _failure_class(value: str) -> ProviderFailureClass:
    try:
        return ProviderFailureClass(value)
    except ValueError:
        return ProviderFailureClass.UNKNOWN_POTENTIALLY_BILLABLE_FAILURE
