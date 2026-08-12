"""Provider boundary for Phase 6.

The product logic never asks a provider to supply facts. Providers receive only a
validated evidence packet and must return the constrained response shape. The
included provider is deterministic so local development has no key or network
dependency and cannot leak private data.
"""

from typing import Protocol

from app.core.config import Settings
from app.modules.assistant.schemas import AssistantStructuredResponse


class AssistantProviderError(Exception):
    """A provider failure that must never trigger an unsupported fallback."""


class AssistantProviderUnavailable(AssistantProviderError):
    pass


class EvidenceOnlyProvider(Protocol):
    name: str
    model_version: str

    def generate(self, response: AssistantStructuredResponse) -> AssistantStructuredResponse: ...


class EvidenceTemplateProvider:
    name = "evidence-template"

    def __init__(self, model_version: str = "evidence-template-v1") -> None:
        self.model_version = model_version

    def generate(self, response: AssistantStructuredResponse) -> AssistantStructuredResponse:
        """Return server-composed, schema-validated evidence without model inference."""
        return response


class UnavailableProvider:
    """Safe placeholder for an unconfigured or unavailable remote provider."""

    def __init__(self, name: str, model_version: str) -> None:
        self.name = name
        self.model_version = model_version

    def generate(self, response: AssistantStructuredResponse) -> AssistantStructuredResponse:
        raise AssistantProviderUnavailable("The configured assistant provider is unavailable")


def get_provider(settings: Settings) -> EvidenceOnlyProvider:
    """Return a server-side provider implementation without exposing credentials.

    Remote providers deliberately remain unavailable until a reviewed adapter is
    added. This makes an accidental configuration change degrade safely rather
    than transmitting student data to an unknown service.
    """
    if settings.assistant_provider == "evidence-template":
        return EvidenceTemplateProvider(settings.assistant_model)
    return UnavailableProvider(settings.assistant_provider, settings.assistant_model)
