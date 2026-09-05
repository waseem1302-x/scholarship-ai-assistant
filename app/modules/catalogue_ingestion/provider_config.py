"""Non-secret effective provider configuration for catalogue ingestion.

The application ``Settings`` object remains the environment/config injection boundary. This module
translates catalogue AI settings and paid-pipeline contract versions into one normalized receipt so
provider identity, retry behaviour, pricing, prompt/schema/parser drift, and safety limits can fail
closed on resume. The receipt contains no credentials; configured endpoints and reviewed domains
participate only through SHA-256 fingerprints.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings
from app.modules.catalogue_ingestion.claim_bundle_provider import bundle_claim_prompt_hash
from app.modules.catalogue_ingestion.claim_bundle_schemas import CLAIM_BUNDLE_SCHEMA_VERSION
from app.modules.catalogue_ingestion.claim_schemas import ClaimObjective
from app.modules.catalogue_ingestion.evidence_block_models import (
    EVIDENCE_BLOCK_BUILDER_VERSION,
    EVIDENCE_ROUTER_VERSION,
)
from app.modules.catalogue_ingestion.extraction_planner import EXTRACTION_JOB_PLANNER_VERSION
from app.modules.catalogue_ingestion.pipeline_versions import (
    BUNDLE_NORMALIZER_VERSION,
    BUNDLE_PROVIDER_PARSER_VERSION,
    BUNDLE_RESOLVER_VERSION,
    BUNDLE_VALIDATOR_VERSION,
)

CATALOGUE_CONFIGURATION_REVISION = "catalogue-provider-profile.v6"


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

    endpoint = (
        settings.catalogue_ai_endpoint.strip().rstrip("/")
        if settings.catalogue_ai_endpoint
        else None
    )
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
    """Hash normalized, non-secret settings and paid extraction contract versions."""

    profile = catalogue_provider_profile(settings)
    reviewed_domains = sorted(settings.catalogue_reviewed_official_domain_set)
    reviewed_domain_fingerprint = hashlib.sha256("\n".join(reviewed_domains).encode()).hexdigest()
    bundle_prompt_family_hash = bundle_claim_prompt_hash(tuple(ClaimObjective))
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
        "paid_pipeline_contract": {
            "bundle_prompt_family_hash": bundle_prompt_family_hash,
            "bundle_schema_version": CLAIM_BUNDLE_SCHEMA_VERSION,
            "evidence_block_builder_version": EVIDENCE_BLOCK_BUILDER_VERSION,
            "evidence_router_version": EVIDENCE_ROUTER_VERSION,
            "extraction_job_planner_version": EXTRACTION_JOB_PLANNER_VERSION,
            "provider_parser_version": BUNDLE_PROVIDER_PARSER_VERSION,
            "normalizer_version": BUNDLE_NORMALIZER_VERSION,
            "resolver_version": BUNDLE_RESOLVER_VERSION,
            "validator_version": BUNDLE_VALIDATOR_VERSION,
        },
        "safety": {
            "ai_ingestion_enabled": settings.catalogue_ai_ingestion_enabled,
            "bounded_crawling_enabled": settings.catalogue_bounded_crawling_enabled,
            "completeness_mode_enabled": settings.catalogue_completeness_mode_enabled,
            "browser_fetching_enabled": settings.catalogue_browser_fetching_enabled,
            "document_intelligence_enabled": settings.catalogue_document_intelligence_enabled,
            "docling_enabled": settings.catalogue_docling_enabled,
            "docling_do_ocr": settings.catalogue_docling_do_ocr,
            "docling_table_mode": settings.catalogue_docling_table_mode,
            "reviewed_official_domain_fingerprint": reviewed_domain_fingerprint,
        },
        "limits": {
            "max_candidates_per_run": settings.catalogue_ai_max_candidates_per_run,
            "max_pages_per_candidate": settings.catalogue_ai_max_pages_per_candidate,
            "max_calls_per_run": settings.catalogue_ai_max_calls_per_run,
            "max_input_characters": settings.catalogue_ai_max_input_characters,
            "max_output_tokens": settings.catalogue_ai_max_output_tokens,
            "max_estimated_cost_per_run": str(settings.catalogue_ai_max_estimated_cost_per_run),
            "completeness_max_fetch_attempts": (
                settings.catalogue_completeness_max_fetch_attempts
            ),
            "completeness_max_model_calls": settings.catalogue_completeness_max_model_calls,
            "completeness_max_estimated_cost_per_run": str(
                settings.catalogue_completeness_max_estimated_cost_per_run
            ),
            "source_max_bytes_per_page": settings.catalogue_source_max_bytes_per_page,
            "source_monitor_per_host_interval_seconds": str(
                settings.source_monitor_per_host_interval_seconds
            ),
            "provider_max_concurrency_per_deployment": (
                settings.catalogue_provider_max_concurrency_per_deployment
            ),
            "provider_circuit_failure_threshold": (
                settings.catalogue_provider_circuit_failure_threshold
            ),
            "provider_circuit_open_seconds": settings.catalogue_provider_circuit_open_seconds,
            "max_provider_calls_per_candidate_slice": (
                settings.catalogue_scheduler_max_provider_calls_per_candidate_slice
            ),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
