"""Public Directory & Schema.org JSON-LD SEO Generator."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from app.modules.opportunities.models import Opportunity, OpportunityStatus


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", cleaned).strip("-")


def generate_schema_org_json_ld(
    opportunity: Opportunity,
    *,
    base_url: str = "https://scholarshipai.app",
) -> dict[str, Any]:
    """Generate Schema.org FinancialAid / EducationalOccupationalCredential JSON-LD metadata."""
    country_name = opportunity.country or "International"
    opp_slug = _slugify(opportunity.name)
    country_slug = _slugify(country_name)
    canonical_url = f"{base_url}/scholarships/{country_slug}/{opp_slug}"

    funding_amount = (
        "Full Tuition & Living Allowance"
        if opportunity.funding_type.value == "full"
        else opportunity.funding_type.value.title()
    )
    deadline_iso = None
    if getattr(opportunity, "active_cycle", None) and opportunity.active_cycle.application_deadline:
        deadline_iso = opportunity.active_cycle.application_deadline.isoformat()
    elif getattr(opportunity, "application_deadline", None):
        deadline_iso = opportunity.application_deadline.isoformat()

    provider_name = (
        opportunity.provider.name
        if getattr(opportunity, "provider", None)
        else (getattr(opportunity, "provider_name", None) or "Official Provider")
    )

    return {
        "@context": "https://schema.org",
        "@type": "FinancialAid",
        "name": opportunity.name,
        "description": (
            f"{opportunity.name} is an official {opportunity.degree_level.value.upper()} "
            f"scholarship offered by {provider_name} in {country_name}."
        ),
        "url": canonical_url,
        "provider": {
            "@type": "Organization",
            "name": provider_name,
        },
        "areaServed": country_name,
        "educationalLevel": opportunity.degree_level.value.upper(),
        "financialAidType": funding_amount,
        "validThrough": deadline_iso,
        "isAccessibleForFree": True,
    }


class DirectoryScholarshipCard(BaseModel):
    id: str
    name: str
    slug: str
    canonical_url: str
    provider: str
    country: str
    degree_level: str
    funding_type: str
    intake_year: int
    is_open: bool
    deadline_iso: str | None = None
    official_source_url: str | None = None
    schema_org_json_ld: dict[str, Any]


class PublicDirectoryResponse(BaseModel):
    total_count: int
    page: int
    page_size: int
    total_pages: int
    available_countries: list[str]
    available_degree_levels: list[str]
    available_funding_types: list[str]
    scholarships: list[DirectoryScholarshipCard]


def build_directory_card(
    opportunity: Opportunity,
    *,
    base_url: str = "https://scholarshipai.app",
) -> DirectoryScholarshipCard:
    """Build a public SEO card with Schema.org metadata for an opportunity."""
    country_name = opportunity.country or "International"
    opp_slug = _slugify(opportunity.name)
    country_slug = _slugify(country_name)
    canonical = f"{base_url}/scholarships/{country_slug}/{opp_slug}"

    deadline_iso = None
    if getattr(opportunity, "active_cycle", None) and opportunity.active_cycle.application_deadline:
        deadline_iso = opportunity.active_cycle.application_deadline.isoformat()
    elif getattr(opportunity, "application_deadline", None):
        deadline_iso = opportunity.application_deadline.isoformat()

    official_url = opportunity.sources[0].url if getattr(opportunity, "sources", None) else None
    provider_name = (
        opportunity.provider.name
        if getattr(opportunity, "provider", None)
        else (getattr(opportunity, "provider_name", None) or "Official Provider")
    )

    return DirectoryScholarshipCard(
        id=str(opportunity.id),
        name=opportunity.name,
        slug=opp_slug,
        canonical_url=canonical,
        provider=provider_name,
        country=country_name,
        degree_level=opportunity.degree_level.value.upper(),
        funding_type=opportunity.funding_type.value.upper(),
        intake_year=opportunity.intake_year or 2027,
        is_open=(opportunity.status == OpportunityStatus.ACTIVE),
        deadline_iso=deadline_iso,
        official_source_url=official_url,
        schema_org_json_ld=generate_schema_org_json_ld(opportunity, base_url=base_url),
    )
