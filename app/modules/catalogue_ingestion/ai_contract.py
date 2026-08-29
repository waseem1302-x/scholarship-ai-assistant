"""Canonical Azure OpenAI route shared by providers and capability validation."""

from __future__ import annotations

from urllib.parse import urlsplit

AZURE_OPENAI_PROVIDER = "azure_openai"
AZURE_OPENAI_API_MODE = "azure_openai_v1_chat_completions"
AZURE_OPENAI_REQUEST_PATH = "/openai/v1/chat/completions"
CAPABILITY_RECEIPT_SCHEMA_VERSION = 2


def normalize_azure_openai_endpoint(endpoint: str) -> str:
    """Return a canonical HTTPS origin suitable for exact receipt matching."""

    parsed = urlsplit(endpoint.strip())
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid_azure_openai_endpoint_port") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("azure_openai_endpoint_must_be_https_origin")

    hostname = parsed.hostname.lower().rstrip(".")
    if not hostname:
        raise ValueError("azure_openai_endpoint_host_required")
    if ":" in hostname:
        hostname = f"[{hostname}]"
    authority = hostname if port in {None, 443} else f"{hostname}:{port}"
    return f"https://{authority}"


def azure_openai_request_url(endpoint: str) -> str:
    """Build the only Azure OpenAI data-plane route supported by this worker."""

    return f"{normalize_azure_openai_endpoint(endpoint)}{AZURE_OPENAI_REQUEST_PATH}"


def azure_openai_runtime_contract(endpoint: str, deployment: str) -> dict[str, object]:
    """Return the receipt fields that exactly describe provider request routing."""

    return {
        "provider": AZURE_OPENAI_PROVIDER,
        "endpoint": normalize_azure_openai_endpoint(endpoint),
        "deployment": deployment,
        "api_mode": AZURE_OPENAI_API_MODE,
        "request_path": AZURE_OPENAI_REQUEST_PATH,
        "strict_json_schema": True,
    }
