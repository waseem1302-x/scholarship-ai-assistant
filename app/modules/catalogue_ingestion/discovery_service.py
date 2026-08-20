"""Discovery-provider execution and policy-gated lead-ingestion boundaries."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.modules.catalogue_ingestion.discovery_models import (
    CatalogueDiscoveryAttempt,
    CatalogueDiscoveryRun,
    DiscoveryAttemptStatus,
    DiscoveryQueryStatus,
)
from app.modules.catalogue_ingestion.discovery_provider import (
    DiscoveryProvider,
    DiscoveryProviderError,
    DiscoveryProviderRequest,
    DiscoveryProviderResult,
)
from app.modules.catalogue_ingestion.discovery_repository import (
    CatalogueDiscoveryRepository,
    DiscoveryAttemptOutcome,
    DiscoveryStateError,
    DiscoveryURLRejected,
)
from app.modules.catalogue_ingestion.url_policy import URLRejectionCode


@dataclass(frozen=True)
class DiscoveryLeadIngestionResult:
    urls_seen: int
    accepted_urls: int
    rejected_urls: int
    unique_lead_ids: tuple[uuid.UUID, ...]
    rejection_counts: tuple[tuple[URLRejectionCode, int], ...]


class CatalogueDiscoveryExecutionService:
    """Execute one already-claimed query without interpreting scholarship facts."""

    def __init__(self, session: Session, provider: DiscoveryProvider) -> None:
        self.repository = CatalogueDiscoveryRepository(session)
        self.provider = provider

    def execute_claimed_query(
        self,
        *,
        query_id: uuid.UUID,
        worker_id: str,
        max_urls: int,
        max_tool_calls: int,
        max_estimated_cost: Decimal,
    ) -> DiscoveryProviderResult:
        query = self.repository.get_query(query_id)
        if query is None:
            raise DiscoveryStateError("catalogue_discovery_query_not_found")
        request = DiscoveryProviderRequest(
            query_hash=query.query_hash,
            query_text=query.query_text,
            allowed_domains=tuple(query.allowed_domains),
            max_urls=max_urls,
            max_response_bytes=self._run_response_limit(query.run_id),
            max_tool_calls=max_tool_calls,
        )
        attempt = self.repository.reserve_attempt(
            query_id=query.id,
            worker_id=worker_id,
            request_fingerprint=_request_fingerprint(request),
            reserved_tool_calls=max_tool_calls,
            reserved_estimated_cost=max_estimated_cost,
        )
        try:
            result = self.provider.search(request)
        except DiscoveryProviderError as exc:
            self.repository.settle_attempt(
                attempt.id,
                DiscoveryAttemptOutcome(
                    status=_attempt_status_for_error(exc.code),
                    error_code=exc.code,
                ),
            )
            raise

        desired_status = (
            DiscoveryAttemptStatus.SUCCEEDED
            if result.web_search_executed
            else DiscoveryAttemptStatus.TOOL_NOT_EXECUTED
        )
        settled = self.repository.settle_attempt(
            attempt.id,
            DiscoveryAttemptOutcome(
                status=desired_status,
                provider_response_id=result.provider_response_id,
                web_search_executed=result.web_search_executed,
                tool_call_count=result.tool_call_count,
                result_url_count=len(result.urls),
                response_bytes=result.response_bytes,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                estimated_model_cost=result.estimated_model_cost,
                estimated_tool_cost=result.estimated_tool_cost,
                latency_ms=result.latency_ms,
                error_code=(None if result.web_search_executed else "web_search_not_executed"),
            ),
        )
        if settled.status is not DiscoveryAttemptStatus.SUCCEEDED:
            raise DiscoveryProviderError(settled.error_code or settled.status.value)
        return result

    def _run_response_limit(self, run_id: uuid.UUID) -> int:
        run = self.repository.session.get(CatalogueDiscoveryRun, run_id)
        if run is None:
            raise DiscoveryStateError("catalogue_discovery_run_not_found")
        return run.max_response_bytes


class CatalogueDiscoveryLeadIngestionService:
    """Persist only policy-accepted provider URLs as discovery leads."""

    def __init__(self, session: Session) -> None:
        self.repository = CatalogueDiscoveryRepository(session)

    def ingest_provider_result(
        self,
        *,
        query_id: uuid.UUID,
        result: DiscoveryProviderResult,
    ) -> DiscoveryLeadIngestionResult:
        query = self.repository.get_query(query_id)
        if query is None:
            raise DiscoveryStateError("catalogue_discovery_query_not_found")
        if query.status not in {
            DiscoveryQueryStatus.RESPONSE_RECEIVED,
            DiscoveryQueryStatus.LEADS_RECORDED,
        }:
            raise DiscoveryStateError("discovery_query_has_no_accepted_response")
        attempt = self.repository.get_latest_successful_attempt(query.id)
        if attempt is None or not _provider_result_matches_attempt(result, attempt):
            raise DiscoveryStateError("provider_result_does_not_match_settled_attempt")

        accepted_urls = 0
        lead_ids: set[uuid.UUID] = set()
        rejection_counts: dict[URLRejectionCode, int] = {}
        for provider_rank, url in enumerate(result.urls, start=1):
            try:
                lead, _ = self.repository.record_lead_observation(
                    query_id=query.id,
                    url=url,
                    discovery_reason=f"{query.query_kind}:provider_url",
                    provider_rank=provider_rank,
                    provider_source_type="web_search_url",
                )
            except DiscoveryURLRejected as exc:
                rejection_counts[exc.code] = rejection_counts.get(exc.code, 0) + 1
                continue
            accepted_urls += 1
            lead_ids.add(lead.id)

        return DiscoveryLeadIngestionResult(
            urls_seen=len(result.urls),
            accepted_urls=accepted_urls,
            rejected_urls=len(result.urls) - accepted_urls,
            unique_lead_ids=tuple(sorted(lead_ids, key=str)),
            rejection_counts=tuple(
                sorted(rejection_counts.items(), key=lambda item: item[0].value)
            ),
        )


def _request_fingerprint(request: DiscoveryProviderRequest) -> str:
    payload = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _provider_result_matches_attempt(
    result: DiscoveryProviderResult,
    attempt: CatalogueDiscoveryAttempt,
) -> bool:
    return all(
        (
            attempt.provider_response_id == result.provider_response_id,
            attempt.web_search_executed == result.web_search_executed,
            attempt.tool_call_count == result.tool_call_count,
            attempt.result_url_count == len(result.urls),
            attempt.response_bytes == result.response_bytes,
            attempt.input_tokens == result.input_tokens,
            attempt.output_tokens == result.output_tokens,
            attempt.estimated_model_cost == result.estimated_model_cost,
            attempt.estimated_tool_cost == result.estimated_tool_cost,
            attempt.latency_ms == result.latency_ms,
        )
    )


def _attempt_status_for_error(code: str) -> DiscoveryAttemptStatus:
    return {
        "provider_rate_limited": DiscoveryAttemptStatus.RATE_LIMITED,
        "provider_timeout": DiscoveryAttemptStatus.TIMEOUT,
        "provider_capability_unavailable": DiscoveryAttemptStatus.CAPABILITY_UNAVAILABLE,
        "provider_response_invalid": DiscoveryAttemptStatus.RESPONSE_INVALID,
    }.get(code, DiscoveryAttemptStatus.PROVIDER_FAILED)
