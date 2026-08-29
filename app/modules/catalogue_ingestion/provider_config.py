"""Non-secret effective provider configuration for catalogue ingestion.

The application ``Settings`` object remains the environment/config injection boundary.  This
module translates the legacy catalogue AI settings into a typed capability profile so provider
identity, deployment selection, retry behaviour, pricing, and safety limits have one normalized
representation.  The profile deliberately contains no credentials and never exposes the endpoint
value through API serializers; only its hash participates in the effective configuration
fingerprint.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings

CATALOGUE_CONFIGURATION_REVISION = "catalogue-provider-profile.v1"


class CatalogueDeploymentMap(BaseModel):
    model_config = ConfigDict(frozen=True)

    extraction: str | None
    classification: str | None = None
    embeddings: str | None = None
    vision_ocr: str | None = None


class CatalogueRetryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_retries: int
    max_retry_delay_seconds: int


class CataloguePricingProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_cost_per_million: Decimal
    output_cost_per_million: Decimal


class CatalogueProviderProfile(BaseModel):
    """Normalized, non-secret provider capability configuration."""

    model_config = ConfigDict(frozen=True)

    provider: str
    endpoint: str | None
    endpoint_fingerprint: str | None
    api_version: str
    credential_reference: str
    deployments: CatalogueDeploymentMap
    timeout_seconds: int
    retry_policy: CatalogueRetryPolicy
    pricing: CataloguePricingProfile

    @property
    def extraction_deployment(self) -> str | None:
        return self.deployments.extraction


def catalogue_provider_profile(settings: Settings) -> CatalogueProviderProfile:
    """Build the effective profile without reading or materializing credential values."""

    endpoint = settings.catalogue_ai_endpoint.strip().rstrip("/") if settings.catalogue_ai_endpoint else None
    deployment = settings.catalogue_ai_model.strip()
    if not deployment or deployment.casefold() == "unconfigured":
        deployment = ""
    return CatalogueProviderProfile(
        provider=settings.catalogue_ai_provider,
        endpoint=endpoint,
        endpoint_fingerprint=(
            hashlib.sha256(endpoint.encode()).hexdigest() if endpoint is not None else None
        ),
        api_version=settings.catalogue_ai_api_version.strip(),
        credential_reference="default_azure_credential",
        deployments=CatalogueDeploymentMap(extraction=deployment or None),
        timeout_seconds=settings.catalogue_ai_timeout_seconds,
        retry_policy=CatalogueRetryPolicy(
            max_retries=settings.catalogue_ai_max_retries,
            max_retry_delay_seconds=settings.catalogue_ai_max_retry_delay_seconds,
        ),
        pricing=CataloguePricingProfile(
            input_cost_per_million=settings.catalogue_ai_input_cost_per_million,
            output_cost_per_million=settings.catalogue_ai_output_cost_per_million,
        ),
    )


def catalogue_configuration_fingerprint(settings: Settings) -> str:
    """Hash normalized, non-secret settings that authorize paid catalogue work.

    The endpoint itself is intentionally excluded.  Its SHA-256 digest makes account/endpoint drift
    detectable without surfacing the hostname to administrator API responses.
    """

    profile = catalogue_provider_profile(settings)
    payload = {
        "revision": CATALOGUE_CONFIGURATION_REVISION,
        "provider": profile.provider,
        "endpoint_fingerprint": profile.endpoint_fingerprint,
        "api_version": profile.api_version,
        "credential_reference": profile.credential_reference,
        "deployments": profile.deployments.model_dump(mode="json"),
        "timeout_seconds": profile.timeout_seconds,
        "retry_policy": profile.retry_policy.model_dump(mode="json"),
        "pricing": {
            "input_cost_per_million": str(profile.pricing.input_cost_per_million),
            "output_cost_per_million": str(profile.pricing.output_cost_per_million),
        },
        "safety": {
            "ai_ingestion_enabled": settings.catalogue_ai_ingestion_enabled,
            "bounded_crawling_enabled": settings.catalogue_bounded_crawling_enabled,
            "browser_fetching_enabled": settings.catalogue_browser_fetching_enabled,
            "document_intelligence_enabled": settings.catalogue_document_intelligence_enabled,
        },
        "limits": {
            "max_candidates_per_run": settings.catalogue_ai_max_candidates_per_run,
            "max_pages_per_candidate": settings.catalogue_ai_max_pages_per_candidate,
            "max_calls_per_run": settings.catalogue_ai_max_calls_per_run,
            "max_input_characters": settings.catalogue_ai_max_input_characters,
            "max_output_tokens": settings.catalogue_ai_max_output_tokens,
            "max_estimated_cost_per_run": str(settings.catalogue_ai_max_estimated_cost_per_run),
            "source_max_bytes_per_page": settings.catalogue_source_max_bytes_per_page,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
