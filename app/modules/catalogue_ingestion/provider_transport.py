"""Single-attempt transport primitives for paid catalogue provider calls.

Retry ownership deliberately lives above this module.  A call through ``send_json_request`` either
performs at most one HTTP request or fails before dispatch while acquiring credentials.  The
result/error carries enough non-secret metadata for orchestration to persist a durable accounting
record for that exact attempt.
"""

from __future__ import annotations

import http.client
import math
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from app.modules.catalogue_ingestion.schemas import ExtractionUsage


class ExtractionProviderError(RuntimeError):
    code = "ai_extraction_failed"
    failure_class = "unknown_potentially_billable_failure"
    retryable = True
    potentially_billable = True
    dispatch_occurred = True

    def __init__(
        self,
        message: str,
        *,
        usage: ExtractionUsage | None = None,
        provider_request_id: str | None = None,
        retry_after_seconds: float | None = None,
        failure_class: str | None = None,
        retryable: bool | None = None,
        potentially_billable: bool | None = None,
        dispatch_occurred: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.provider_request_id = provider_request_id
        self.retry_after_seconds = retry_after_seconds
        if failure_class is not None:
            self.failure_class = failure_class
        if retryable is not None:
            self.retryable = retryable
        if potentially_billable is not None:
            self.potentially_billable = potentially_billable
        if dispatch_occurred is not None:
            self.dispatch_occurred = dispatch_occurred


class ExtractionProviderRateLimited(ExtractionProviderError):
    code = "ai_rate_limited"
    failure_class = "rate_limit"
    retryable = True
    potentially_billable = False


class ExtractionProviderUnavailable(ExtractionProviderError):
    code = "ai_provider_unavailable"
    failure_class = "authentication_configuration_error"
    retryable = False
    potentially_billable = False
    dispatch_occurred = False


class ExtractionProviderTimeout(ExtractionProviderError):
    code = "ai_provider_timeout"
    failure_class = "timeout"
    retryable = True
    potentially_billable = True


class ExtractionProviderServerError(ExtractionProviderError):
    code = "ai_provider_server_error"
    failure_class = "provider_server_error"
    retryable = True
    potentially_billable = True


class ExtractionProviderConnectionError(ExtractionProviderError):
    code = "ai_provider_connection_failed"
    failure_class = "connection_establishment_failure"
    retryable = True
    potentially_billable = False


class ExtractionProviderResponseInterrupted(ExtractionProviderError):
    code = "ai_provider_response_interrupted"
    failure_class = "post_dispatch_response_interruption"
    retryable = True
    potentially_billable = True


class ExtractionSchemaError(ExtractionProviderError):
    code = "ai_schema_failed"
    failure_class = "schema_validation_failure"
    retryable = False
    potentially_billable = True


@dataclass(frozen=True)
class ProviderHttpResponse:
    raw: bytes
    provider_request_id: str | None
    latency_ms: int


def send_json_request(
    *,
    credential: Any,
    token_scope: str,
    url: str,
    payload: bytes,
    timeout_seconds: int,
    max_response_bytes: int,
    opener: Any,
    user_agent: str,
) -> ProviderHttpResponse:
    """Execute at most one provider request.

    Credential acquisition happens before the request object is handed to the HTTP opener.  Any
    failure there is therefore classified as pre-dispatch/non-billable.  Once ``opener.open`` is
    invoked, ambiguous transport failures are conservatively treated as potentially billable unless
    the underlying exception proves that connection establishment itself failed.
    """

    try:
        token = credential.get_token(token_scope).token
    except Exception as exc:
        raise ExtractionProviderUnavailable(
            "Catalogue provider credential acquisition failed",
            failure_class="pre_dispatch_failure",
            dispatch_occurred=False,
        ) from exc

    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
    )
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            request_id = provider_request_id(response.headers)
            raw = response.read(max_response_bytes + 1)
    except urllib.error.HTTPError as exc:
        request_id = provider_request_id(exc.headers)
        retry_after = retry_after_seconds(exc.headers)
        if exc.code == 429:
            raise ExtractionProviderRateLimited(
                "Catalogue provider rate limit was exhausted",
                provider_request_id=request_id,
                retry_after_seconds=retry_after,
                dispatch_occurred=True,
            ) from exc
        if exc.code in {401, 403}:
            raise ExtractionProviderUnavailable(
                "Catalogue provider authentication or authorization failed",
                provider_request_id=request_id,
                failure_class="authentication_configuration_error",
                dispatch_occurred=True,
            ) from exc
        if exc.code >= 500:
            raise ExtractionProviderServerError(
                "Catalogue provider returned a server error",
                provider_request_id=request_id,
                retry_after_seconds=retry_after,
                dispatch_occurred=True,
            ) from exc
        raise ExtractionProviderError(
            "Catalogue provider rejected the request",
            provider_request_id=request_id,
            failure_class="authentication_configuration_error" if exc.code == 404 else "unknown_potentially_billable_failure",
            retryable=False,
            potentially_billable=False,
            dispatch_occurred=True,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ExtractionProviderTimeout(
            "Catalogue provider request timed out",
            dispatch_occurred=True,
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.gaierror, ConnectionRefusedError)):
            raise ExtractionProviderConnectionError(
                "Catalogue provider connection could not be established",
                dispatch_occurred=True,
            ) from exc
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise ExtractionProviderTimeout(
                "Catalogue provider request timed out",
                dispatch_occurred=True,
            ) from exc
        if isinstance(
            reason,
            (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError),
        ):
            raise ExtractionProviderResponseInterrupted(
                "Catalogue provider response was interrupted after dispatch",
                dispatch_occurred=True,
            ) from exc
        raise ExtractionProviderError(
            "Catalogue provider transport failed after dispatch",
            failure_class="unknown_potentially_billable_failure",
            retryable=True,
            potentially_billable=True,
            dispatch_occurred=True,
        ) from exc
    except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError) as exc:
        raise ExtractionProviderResponseInterrupted(
            "Catalogue provider response was interrupted after dispatch",
            dispatch_occurred=True,
        ) from exc
    except OSError as exc:
        raise ExtractionProviderError(
            "Catalogue provider transport failed after dispatch",
            failure_class="unknown_potentially_billable_failure",
            retryable=True,
            potentially_billable=True,
            dispatch_occurred=True,
        ) from exc

    if len(raw) > max_response_bytes:
        raise ExtractionSchemaError(
            "AI response exceeded the configured byte limit",
            provider_request_id=request_id,
        )
    return ProviderHttpResponse(
        raw=raw,
        provider_request_id=request_id,
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def provider_request_id(headers: Any | None) -> str | None:
    if headers is None:
        return None
    for name in ("x-request-id", "apim-request-id", "request-id", "x-ms-request-id"):
        value = headers.get(name)
        if value:
            return str(value)[:255]
    return None


def retry_after_seconds(headers: Any | None) -> float | None:
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        delay = float(raw)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            delay = (retry_at - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(delay):
        return None
    return max(delay, 0.0)


def extraction_retry_delay(
    error: BaseException | None,
    *,
    attempt: int,
    maximum: float,
) -> float:
    """Return a bounded orchestration retry delay for one completed attempt."""

    fallback = min(2**attempt, 4)
    if isinstance(error, ExtractionProviderError) and error.retry_after_seconds is not None:
        return min(max(error.retry_after_seconds, 0.0), maximum)
    return min(float(fallback), maximum)
