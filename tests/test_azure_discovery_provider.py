import json
import urllib.error
from collections import deque
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.catalogue_ingestion.azure_discovery_provider import (
    AzureResponsesWebSearchProvider,
    DiscoveryProviderRetryPolicy,
    UnavailableDiscoveryProvider,
    get_discovery_provider,
)
from app.modules.catalogue_ingestion.discovery_provider import (
    DiscoveryProviderError,
    DiscoveryProviderRequest,
)

FIXTURES = Path(__file__).parent / "fixtures" / "catalogue_discovery"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "sqlite+pysqlite:///:memory:",
        "jwt_secret": "azure-discovery-provider-test-secret-at-least-32-characters",
        "catalogue_web_discovery_enabled": True,
        "catalogue_web_discovery_provider": "azure_responses_web_search",
        "catalogue_web_discovery_endpoint": "https://scholarship.openai.azure.com",
        "catalogue_web_discovery_model": "gpt-5-mini",
        "catalogue_discovery_max_estimated_cost_per_run": Decimal("1.00"),
        "catalogue_discovery_max_estimated_cost_per_provider_request": Decimal("0.10"),
    }
    values.update(changes)
    return Settings(**values)


def _request(**changes: object) -> DiscoveryProviderRequest:
    values: dict[str, object] = {
        "query_hash": "a" * 64,
        "query_text": "MEXT Scholarship official source",
        "allowed_domains": ("mext.go.jp", "studyinjapan.go.jp"),
        "max_urls": 5,
        "max_response_bytes": 50_000,
        "max_tool_calls": 1,
    }
    values.update(changes)
    return DiscoveryProviderRequest(**values)


class Credential:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.scopes: list[str] = []

    def get_token(self, scope: str):
        self.scopes.append(scope)
        if self.error is not None:
            raise self.error
        return type("Token", (), {"token": "managed-identity-token"})()


class FrozenResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_length: str | None = None,
    ) -> None:
        self.body = body
        self.headers = {} if content_length is None else {"Content-Length": content_length}
        self.read_limits: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        self.read_limits.append(limit)
        return self.body


class QueueOpener:
    def __init__(self, *outcomes: FrozenResponse | BaseException) -> None:
        self.outcomes = deque(outcomes)
        self.requests = []
        self.timeouts: list[int] = []

    def open(self, request, timeout: int):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _provider(
    opener: QueueOpener,
    *,
    credential: Credential | None = None,
    settings: Settings | None = None,
) -> AzureResponsesWebSearchProvider:
    ticks = iter((10.0, 10.125))
    return AzureResponsesWebSearchProvider(
        settings or _settings(),
        credential=credential or Credential(),
        opener=opener,
        clock=lambda: next(ticks),
    )


def test_successful_web_search_uses_managed_identity_and_source_only_contract() -> None:
    body = _fixture("azure_web_search_success.json")
    response = FrozenResponse(body, content_length=str(len(body)))
    opener = QueueOpener(response)
    credential = Credential()

    result = _provider(opener, credential=credential).search(_request())

    assert credential.scopes == ["https://ai.azure.com/.default"]
    assert len(opener.requests) == 1
    assert opener.timeouts == [30]
    outbound = opener.requests[0]
    assert outbound.full_url == ("https://scholarship.openai.azure.com/openai/v1/responses")
    assert outbound.get_header("Authorization") == "Bearer managed-identity-token"
    sent = json.loads(outbound.data)
    assert sent["model"] == "gpt-5-mini"
    assert sent["tools"] == [
        {
            "type": "web_search",
            "search_context_size": "low",
            "filters": {"allowed_domains": ["mext.go.jp", "studyinjapan.go.jp"]},
        }
    ]
    assert sent["tool_choice"] == "auto"
    assert sent["include"] == ["web_search_call.action.sources"]
    assert sent["max_tool_calls"] == 1
    assert sent["store"] is False
    assert "web_search_preview" not in outbound.data.decode()
    assert response.read_limits == [50_001]
    assert result.web_search_executed is True
    assert result.tool_call_count == 1
    assert result.urls == (
        "https://www.mext.go.jp/en/policy/education/highered/title02/detail02/1373809.htm",
        "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/",
        "https://www.mext.go.jp/en/policy/education/highered/",
    )
    assert result.input_tokens == 42
    assert result.output_tokens == 18
    assert result.response_bytes == len(body)
    assert result.latency_ms == 125
    assert "Official MEXT sources were found" not in result.model_dump_json()


def test_configured_v1_endpoint_is_not_duplicated() -> None:
    body = _fixture("azure_web_search_not_executed.json")
    opener = QueueOpener(FrozenResponse(body))
    settings = _settings(
        catalogue_web_discovery_endpoint=("https://scholarship.openai.azure.com/openai/v1/")
    )

    _provider(opener, settings=settings).search(_request())

    assert opener.requests[0].full_url == (
        "https://scholarship.openai.azure.com/openai/v1/responses"
    )


def test_http_success_without_tool_execution_ignores_prose_and_citations() -> None:
    body = _fixture("azure_web_search_not_executed.json")

    result = _provider(QueueOpener(FrozenResponse(body))).search(_request())

    assert result.web_search_executed is False
    assert result.tool_call_count == 0
    assert result.urls == ()
    assert result.provider_response_id == "resp_without_search_001"


def test_missing_source_url_rejects_the_entire_provider_response() -> None:
    provider = _provider(
        QueueOpener(FrozenResponse(_fixture("azure_web_search_invalid_source.json")))
    )

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())

    assert captured.value.code == "provider_response_invalid"


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps({"id": "resp_1", "status": "completed", "output": {}}).encode(),
        json.dumps(
            {
                "id": "resp_1",
                "status": "completed",
                "output": ["not-an-output-item"],
            }
        ).encode(),
        json.dumps(
            {
                "id": "resp_1",
                "status": "completed",
                "output": [
                    {
                        "type": "web_search_call",
                        "status": "failed",
                        "action": {"sources": []},
                    }
                ],
            }
        ).encode(),
        json.dumps(
            {
                "id": "resp_1",
                "status": "completed",
                "output": [
                    {
                        "type": "web_search_call",
                        "status": "completed",
                        "action": {
                            "sources": [{"url": "javascript:alert(1)"}],
                        },
                    }
                ],
            }
        ).encode(),
    ],
)
def test_invalid_response_shapes_fail_closed(payload: bytes) -> None:
    provider = _provider(QueueOpener(FrozenResponse(payload)))

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())

    assert captured.value.code == "provider_response_invalid"


def test_duplicate_urls_are_removed_before_the_request_limit_is_applied() -> None:
    payload = json.loads(_fixture("azure_web_search_success.json"))
    payload["output"][0]["action"]["sources"].insert(
        0,
        {
            "type": "url",
            "url": (
                "https://www.mext.go.jp/en/policy/education/highered/title02/detail02/1373809.htm"
            ),
        },
    )
    provider = _provider(QueueOpener(FrozenResponse(json.dumps(payload).encode())))

    result = provider.search(_request(max_urls=2))

    assert result.urls == (
        "https://www.mext.go.jp/en/policy/education/highered/title02/detail02/1373809.htm",
        "https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/",
    )


def test_more_tool_calls_than_reserved_fails_closed() -> None:
    payload = json.loads(_fixture("azure_web_search_success.json"))
    payload["output"].insert(1, dict(payload["output"][0], id="ws_mext_002"))
    provider = _provider(QueueOpener(FrozenResponse(json.dumps(payload).encode())))

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request(max_tool_calls=1))

    assert captured.value.code == "provider_response_invalid"


@pytest.mark.parametrize("content_length", ["50001", "invalid", "-1"])
def test_oversized_or_invalid_content_length_fails_before_body_parsing(
    content_length: str,
) -> None:
    response = FrozenResponse(b"{}", content_length=content_length)
    provider = _provider(QueueOpener(response))

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())

    assert captured.value.code == "provider_response_invalid"
    assert response.read_limits == []


def test_body_read_is_bounded_even_without_content_length() -> None:
    response = FrozenResponse(b"x" * 101)
    provider = _provider(QueueOpener(response))

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request(max_response_bytes=100))

    assert captured.value.code == "provider_response_invalid"
    assert response.read_limits == [101]


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (429, "provider_rate_limited"),
        (504, "provider_timeout"),
        (404, "provider_capability_unavailable"),
        (401, "provider_authentication_failed"),
        (400, "provider_request_rejected"),
        (500, "provider_request_failed"),
    ],
)
def test_http_failures_are_classified_without_hidden_retries(
    status: int, expected_code: str
) -> None:
    error = urllib.error.HTTPError(
        "https://scholarship.openai.azure.com/openai/v1/responses",
        status,
        "provider failure",
        {},
        None,
    )
    opener = QueueOpener(error)
    provider = _provider(opener)

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())

    assert captured.value.code == expected_code
    assert len(opener.requests) == 1


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (TimeoutError("timed out"), "provider_timeout"),
        (urllib.error.URLError(TimeoutError("timed out")), "provider_timeout"),
        (urllib.error.URLError("connection reset"), "provider_request_failed"),
    ],
)
def test_transport_failures_are_classified_without_hidden_retries(
    error: BaseException, expected_code: str
) -> None:
    opener = QueueOpener(error)
    provider = _provider(opener)

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())

    assert captured.value.code == expected_code
    assert len(opener.requests) == 1


def test_authentication_failure_never_reaches_the_provider_endpoint() -> None:
    opener = QueueOpener(FrozenResponse(_fixture("azure_web_search_success.json")))
    provider = _provider(opener, credential=Credential(RuntimeError("no identity")))

    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())

    assert captured.value.code == "provider_authentication_failed"
    assert opener.requests == []


def test_retry_policy_stops_after_the_configured_attempt_ceiling() -> None:
    policy = DiscoveryProviderRetryPolicy(max_attempts=3)

    assert policy.allows_retry("provider_rate_limited", completed_attempts=1) is True
    assert policy.allows_retry("provider_timeout", completed_attempts=2) is True
    assert policy.allows_retry("provider_request_failed", completed_attempts=3) is False
    assert policy.allows_retry("provider_request_rejected", completed_attempts=1) is False


def test_provider_exposes_settings_derived_retry_ceiling_without_retrying() -> None:
    error = urllib.error.HTTPError("https://example.test", 500, "failure", {}, None)
    opener = QueueOpener(error)
    provider = _provider(opener, settings=_settings(catalogue_web_discovery_max_retries=2))

    with pytest.raises(DiscoveryProviderError):
        provider.search(_request())

    assert provider.retry_policy.max_attempts == 3
    assert len(opener.requests) == 1


def test_disabled_factory_returns_a_non_network_provider() -> None:
    settings = Settings(
        env="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="disabled-discovery-provider-test-secret-at-least-32-characters",
    )

    provider = get_discovery_provider(settings)

    assert isinstance(provider, UnavailableDiscoveryProvider)
    with pytest.raises(DiscoveryProviderError) as captured:
        provider.search(_request())
    assert captured.value.code == "provider_capability_unavailable"
