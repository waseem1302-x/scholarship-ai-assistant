"""Azure Responses Web Search adapter with strict source-only acceptance."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings
from app.modules.catalogue_ingestion.discovery_provider import (
    DiscoveryProvider,
    DiscoveryProviderError,
    DiscoveryProviderRequest,
    DiscoveryProviderResult,
)
from app.modules.catalogue_ingestion.url_policy import MAX_CATALOGUE_URL_LENGTH

AZURE_RESPONSES_WEB_SEARCH_PROVIDER = "azure_responses_web_search"
STABLE_WEB_SEARCH_TOOL = "web_search"
WEB_SEARCH_SOURCE_INCLUDE = "web_search_call.action.sources"
RETRYABLE_DISCOVERY_PROVIDER_ERRORS = frozenset(
    {
        "provider_rate_limited",
        "provider_request_failed",
        "provider_timeout",
    }
)


@dataclass(frozen=True, slots=True)
class DiscoveryProviderRetryPolicy:
    """Bound retries without hiding provider calls from the durable attempt ledger."""

    max_attempts: int

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("discovery provider max_attempts must be positive")

    def allows_retry(self, error_code: str, *, completed_attempts: int) -> bool:
        if completed_attempts < 1:
            raise ValueError("completed_attempts must be positive")
        return (
            error_code in RETRYABLE_DISCOVERY_PROVIDER_ERRORS
            and completed_attempts < self.max_attempts
        )


class UnavailableDiscoveryProvider:
    """Non-network provider used while the discovery kill switch is disabled."""

    name = "unavailable"

    def search(self, request: DiscoveryProviderRequest) -> DiscoveryProviderResult:
        del request
        raise DiscoveryProviderError("provider_capability_unavailable")


class AzureResponsesWebSearchProvider:
    """Perform one ledger-backed Azure Responses request and parse only source metadata."""

    name = AZURE_RESPONSES_WEB_SEARCH_PROVIDER

    def __init__(
        self,
        settings: Settings,
        *,
        credential: Any | None = None,
        opener: Any | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if (
            not settings.catalogue_web_discovery_enabled
            or settings.catalogue_web_discovery_provider != self.name
            or settings.catalogue_web_discovery_endpoint is None
        ):
            raise ValueError("Azure Responses Web Search requires enabled, validated settings")
        self.settings = settings
        self.model = settings.catalogue_web_discovery_model
        self.credential = credential or self._default_credential()
        self.opener = opener or urllib.request.build_opener()
        self.clock = clock
        self.endpoint = _responses_endpoint(settings.catalogue_web_discovery_endpoint)
        self.retry_policy = DiscoveryProviderRetryPolicy(
            max_attempts=settings.catalogue_web_discovery_max_retries + 1
        )

    @staticmethod
    def _default_credential() -> Any:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise ValueError("Azure Identity dependency is unavailable") from exc
        return DefaultAzureCredential()

    def search(self, request: DiscoveryProviderRequest) -> DiscoveryProviderResult:
        """Make exactly one provider call; orchestration owns durable retries."""

        started = self.clock()
        payload = json.dumps(
            _request_payload(request, model=self.model),
            separators=(",", ":"),
        ).encode()
        try:
            token = self.credential.get_token(
                self.settings.catalogue_web_discovery_token_scope
            ).token
        except Exception as exc:
            raise DiscoveryProviderError("provider_authentication_failed") from exc

        outbound = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "ScholarshipAI-CatalogueDiscovery/0.1",
            },
        )
        response_limit = min(
            request.max_response_bytes,
            self.settings.catalogue_web_discovery_max_response_bytes,
        )
        try:
            with self.opener.open(
                outbound,
                timeout=self.settings.catalogue_web_discovery_timeout_seconds,
            ) as response:
                _reject_oversized_content_length(response, response_limit)
                raw = response.read(response_limit + 1)
        except urllib.error.HTTPError as exc:
            raise DiscoveryProviderError(_http_error_code(exc.code)) from exc
        except TimeoutError as exc:
            raise DiscoveryProviderError("provider_timeout") from exc
        except urllib.error.URLError as exc:
            code = (
                "provider_timeout"
                if isinstance(exc.reason, TimeoutError)
                else "provider_request_failed"
            )
            raise DiscoveryProviderError(code) from exc
        except OSError as exc:
            raise DiscoveryProviderError("provider_request_failed") from exc

        if len(raw) > response_limit:
            raise DiscoveryProviderError("provider_response_invalid")
        latency_ms = max(0, min(300_000, int((self.clock() - started) * 1000)))
        return _parse_response(
            raw,
            request=request,
            response_bytes=len(raw),
            latency_ms=latency_ms,
        )


def get_discovery_provider(settings: Settings) -> DiscoveryProvider:
    if not settings.catalogue_web_discovery_enabled:
        return UnavailableDiscoveryProvider()
    if settings.catalogue_web_discovery_provider == AZURE_RESPONSES_WEB_SEARCH_PROVIDER:
        return AzureResponsesWebSearchProvider(settings)
    return UnavailableDiscoveryProvider()


def _request_payload(request: DiscoveryProviderRequest, *, model: str) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "type": STABLE_WEB_SEARCH_TOOL,
        "search_context_size": "low",
    }
    if request.allowed_domains:
        tool["filters"] = {"allowed_domains": list(request.allowed_domains)}
    return {
        "model": model,
        "input": (
            "Perform a web search for this public scholarship-source query. "
            "Use web results and include source citations.\n\n"
            f"Query: {request.query_text}"
        ),
        "tools": [tool],
        "tool_choice": "auto",
        "include": [WEB_SEARCH_SOURCE_INCLUDE],
        "max_tool_calls": request.max_tool_calls,
        "store": False,
    }


def _parse_response(
    raw: bytes,
    *,
    request: DiscoveryProviderRequest,
    response_bytes: int,
    latency_ms: int,
) -> DiscoveryProviderResult:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DiscoveryProviderError("provider_response_invalid") from exc
    if not isinstance(payload, dict):
        raise DiscoveryProviderError("provider_response_invalid")

    response_id = payload.get("id")
    output = payload.get("output")
    response_status = payload.get("status")
    if (
        not isinstance(response_id, str)
        or not response_id
        or len(response_id) > 255
        or not isinstance(output, list)
        or (response_status is not None and response_status != "completed")
    ):
        raise DiscoveryProviderError("provider_response_invalid")
    if any(not isinstance(item, dict) or not isinstance(item.get("type"), str) for item in output):
        raise DiscoveryProviderError("provider_response_invalid")

    web_search_calls = [item for item in output if item.get("type") == "web_search_call"]
    if len(web_search_calls) > request.max_tool_calls:
        raise DiscoveryProviderError("provider_response_invalid")

    input_tokens, output_tokens = _parse_usage(payload.get("usage"))
    if not web_search_calls:
        return DiscoveryProviderResult(
            provider_response_id=response_id,
            web_search_executed=False,
            urls=(),
            tool_call_count=0,
            response_bytes=response_bytes,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    collected: list[str] = []
    for call in web_search_calls:
        if call.get("status") not in {None, "completed"}:
            raise DiscoveryProviderError("provider_response_invalid")
        action = call.get("action")
        if not isinstance(action, dict) or not isinstance(action.get("sources"), list):
            raise DiscoveryProviderError("provider_response_invalid")
        for source in action["sources"]:
            if not isinstance(source, dict):
                raise DiscoveryProviderError("provider_response_invalid")
            collected.append(_validated_url(source.get("url")))

    collected.extend(_citation_urls(output))
    urls = tuple(_deduplicate(collected)[: request.max_urls])
    return DiscoveryProviderResult(
        provider_response_id=response_id,
        web_search_executed=True,
        urls=urls,
        tool_call_count=len(web_search_calls),
        response_bytes=response_bytes,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _citation_urls(output: list[Any]) -> list[str]:
    urls: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            raise DiscoveryProviderError("provider_response_invalid")
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            annotations = part.get("annotations", [])
            if not isinstance(annotations, list):
                raise DiscoveryProviderError("provider_response_invalid")
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    raise DiscoveryProviderError("provider_response_invalid")
                if annotation.get("type") == "url_citation":
                    urls.append(_validated_url(annotation.get("url")))
    return urls


def _validated_url(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_CATALOGUE_URL_LENGTH
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise DiscoveryProviderError("provider_response_invalid")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        _ = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise DiscoveryProviderError("provider_response_invalid") from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not host:
        raise DiscoveryProviderError("provider_response_invalid")
    return value


def _parse_usage(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise DiscoveryProviderError("provider_response_invalid")
    input_tokens = value.get("input_tokens")
    output_tokens = value.get("output_tokens")
    if (
        not isinstance(input_tokens, int)
        or isinstance(input_tokens, bool)
        or input_tokens < 0
        or not isinstance(output_tokens, int)
        or isinstance(output_tokens, bool)
        or output_tokens < 0
    ):
        raise DiscoveryProviderError("provider_response_invalid")
    return input_tokens, output_tokens


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _responses_endpoint(configured_endpoint: str) -> str:
    endpoint = configured_endpoint.rstrip("/")
    if endpoint.endswith("/openai/v1/responses"):
        return endpoint
    if endpoint.endswith("/openai/v1"):
        return f"{endpoint}/responses"
    return f"{endpoint}/openai/v1/responses"


def _reject_oversized_content_length(response: Any, limit: int) -> None:
    headers = getattr(response, "headers", None)
    raw_length = headers.get("Content-Length") if headers is not None else None
    if raw_length is None:
        return
    try:
        content_length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise DiscoveryProviderError("provider_response_invalid") from exc
    if content_length < 0 or content_length > limit:
        raise DiscoveryProviderError("provider_response_invalid")


def _http_error_code(status: int) -> str:
    if status == 429:
        return "provider_rate_limited"
    if status in {408, 504}:
        return "provider_timeout"
    if status == 404:
        return "provider_capability_unavailable"
    if status in {401, 403}:
        return "provider_authentication_failed"
    if 400 <= status < 500:
        return "provider_request_rejected"
    return "provider_request_failed"


__all__ = [
    "AZURE_RESPONSES_WEB_SEARCH_PROVIDER",
    "RETRYABLE_DISCOVERY_PROVIDER_ERRORS",
    "AzureResponsesWebSearchProvider",
    "DiscoveryProviderRetryPolicy",
    "UnavailableDiscoveryProvider",
    "get_discovery_provider",
]
