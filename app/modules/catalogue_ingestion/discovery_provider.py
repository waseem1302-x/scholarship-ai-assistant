"""Bounded provider protocol and deterministic fake for discovery CI."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiscoveryProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_text: str = Field(min_length=1, max_length=1000)
    allowed_domains: tuple[str, ...] = Field(default=(), max_length=20)
    max_urls: int = Field(ge=1, le=50)
    max_response_bytes: int = Field(ge=1, le=5_000_000)
    max_tool_calls: int = Field(ge=1, le=5)


class DiscoveryProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_response_id: str | None = Field(default=None, max_length=255)
    web_search_executed: bool
    urls: tuple[str, ...] = Field(default=(), max_length=50)
    provider_call_count: int = Field(default=1, ge=1, le=1)
    tool_call_count: int = Field(ge=0, le=5)
    response_bytes: int = Field(ge=0, le=5_000_000)
    latency_ms: int = Field(ge=0, le=300_000)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_model_cost: Decimal = Field(default=Decimal("0"), ge=0)
    estimated_tool_cost: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def require_executed_search_for_urls(self) -> DiscoveryProviderResult:
        if self.urls and not self.web_search_executed:
            raise ValueError("URLs require an executed web-search tool call")
        if self.web_search_executed and self.tool_call_count < 1:
            raise ValueError("executed web search requires a positive tool-call count")
        return self

    @property
    def estimated_total_cost(self) -> Decimal:
        return self.estimated_model_cost + self.estimated_tool_cost


class DiscoveryProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DiscoveryProvider(Protocol):
    def search(self, request: DiscoveryProviderRequest) -> DiscoveryProviderResult: ...


class FakeDiscoveryProvider:
    """Return reviewed fixtures by query hash without any network access."""

    def __init__(
        self,
        responses: Mapping[str, DiscoveryProviderResult | DiscoveryProviderError],
    ) -> None:
        self._responses = dict(responses)
        self.requests: list[DiscoveryProviderRequest] = []

    def search(self, request: DiscoveryProviderRequest) -> DiscoveryProviderResult:
        self.requests.append(request)
        response = self._responses.get(request.query_hash)
        if response is None:
            raise DiscoveryProviderError("fake_response_not_configured")
        if isinstance(response, DiscoveryProviderError):
            raise response
        if len(response.urls) > request.max_urls:
            raise DiscoveryProviderError("provider_url_limit_exceeded")
        if response.response_bytes > request.max_response_bytes:
            raise DiscoveryProviderError("provider_response_too_large")
        if response.tool_call_count > request.max_tool_calls:
            raise DiscoveryProviderError("provider_tool_call_limit_exceeded")
        return response
