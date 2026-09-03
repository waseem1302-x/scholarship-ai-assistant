"""Scholarship Benefits & Funding Comparator Engine."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.opportunities.evidence_models import FundingComponent
from app.modules.opportunities.models import Opportunity
from app.modules.opportunities.schemas import PublicFundingResponse

# Approximate USD conversion rates for comparison benchmark
_USD_RATES: dict[str, float] = {
    "USD": 1.0,
    "GBP": 1.28,
    "EUR": 1.08,
    "JPY": 0.0067,
    "AUD": 0.66,
    "CAD": 0.74,
    "SGD": 0.75,
    "CHF": 1.13,
    "CNY": 0.14,
    "SEK": 0.095,
    "KRW": 0.00075,
    "TRY": 0.031,
    "INR": 0.012,
    "PKR": 0.0036,
}

_ANNUAL_MULTIPLIERS: dict[str, float] = {
    "month": 12.0,
    "monthly": 12.0,
    "year": 1.0,
    "yearly": 1.0,
    "annual": 1.0,
    "annually": 1.0,
}
_POSITIVE_COVERAGE = {"full", "confirmed", "partial"}
_NEGATIVE_COVERAGE = {"not_covered", "none"}
_COMPARABLE_BENEFIT_TYPES = {
    "accommodation",
    "airfare",
    "book_allowance",
    "flight",
    "health_insurance",
    "housing",
    "living_allowance",
    "medical_insurance",
    "monthly_stipend",
    "research_allowance",
    "settlement_allowance",
    "stipend",
    "travel",
    "tuition",
    "tuition_fee",
    "tuition_fees",
    "visa_allowance",
}


class ScholarshipFundingCard(BaseModel):
    opportunity_id: str
    name: str
    provider: str
    country: str
    degree_level: str
    funding_type: str
    tuition_coverage: str | None = None
    monthly_stipend_text: str | None = None
    monthly_stipend_usd: float | None = None
    annual_stipend_usd: float | None = None
    travel_airfare_covered: bool | None = None
    health_insurance_covered: bool | None = None
    housing_covered: bool | None = None
    visa_allowance_covered: bool | None = None
    total_estimated_annual_value_usd: float | None = None
    benefits_list: list[str] = Field(default_factory=list)


class ComparisonMatrixResponse(BaseModel):
    total_compared: int
    scholarships: list[ScholarshipFundingCard]
    highest_value_scholarship_id: str | None = None
    fully_funded_count: int | None = None
    financial_comparison_notes: list[str] = Field(default_factory=list)


def build_funding_comparison(
    opportunities_data: list[
        tuple[Opportunity, list[FundingComponent | PublicFundingResponse]]
    ],
) -> ComparisonMatrixResponse:
    """Compare only explicit monetary components and stated benefits."""
    cards: list[ScholarshipFundingCard] = []

    for opp, components in opportunities_data:
        tuition_desc = None
        monthly_stipend_text = None
        monthly_usd = None
        annual_stipend_usd = None
        airfare = None
        health = None
        housing = None
        visa = None
        benefits: list[str] = []
        annual_values: list[float] = []

        for fc in components:
            if not _is_comparable_component(fc):
                continue
            comp_type = (fc.component_type or "").lower()
            coverage = (fc.coverage_status or "").lower()
            coverage_indicator = _coverage_indicator(coverage)
            annual_value = _annual_value_usd(fc)
            if annual_value is not None:
                annual_values.append(annual_value)
            benefit = _benefit_label(fc)
            if benefit:
                benefits.append(benefit)

            if "tuition" in comp_type or "fee" in comp_type:
                tuition_desc = fc.description or _coverage_label(coverage)
            elif "stipend" in comp_type or "living" in comp_type or "allowance" in comp_type:
                if fc.amount is not None and fc.currency and fc.frequency:
                    monthly_stipend_text = (
                        f"{fc.currency.upper()} {float(fc.amount):,.0f} / {fc.frequency.lower()}"
                    )
                if annual_value is not None:
                    annual_stipend_usd = round(annual_value, 2)
                    monthly_usd = round(annual_value / 12, 2)
            elif "travel" in comp_type or "airfare" in comp_type or "flight" in comp_type:
                airfare = _merge_coverage(airfare, coverage_indicator)
            elif "health" in comp_type or "insurance" in comp_type or "medical" in comp_type:
                health = _merge_coverage(health, coverage_indicator)
            elif "housing" in comp_type or "dormitory" in comp_type or "accommodation" in comp_type:
                housing = _merge_coverage(housing, coverage_indicator)
            elif "visa" in comp_type or "settlement" in comp_type:
                visa = _merge_coverage(visa, coverage_indicator)

        estimated_annual = round(sum(annual_values), 2) if annual_values else None

        cards.append(
            ScholarshipFundingCard(
                opportunity_id=str(opp.id),
                name=opp.name,
                provider=(
                    opp.provider.name
                    if getattr(opp, "provider", None)
                    else (getattr(opp, "provider_name", None) or "Provider not stated")
                ),
                country=opp.country or "Not stated",
                degree_level=opp.degree_level.value.upper(),
                funding_type="UNKNOWN",
                tuition_coverage=tuition_desc,
                monthly_stipend_text=monthly_stipend_text,
                monthly_stipend_usd=monthly_usd,
                annual_stipend_usd=annual_stipend_usd,
                travel_airfare_covered=airfare,
                health_insurance_covered=health,
                housing_covered=housing,
                visa_allowance_covered=visa,
                total_estimated_annual_value_usd=estimated_annual,
                benefits_list=benefits,
            )
        )

    cards.sort(
        key=lambda card: (
            card.total_estimated_annual_value_usd is None,
            -(card.total_estimated_annual_value_usd or 0),
            card.name.casefold(),
        )
    )
    valued_cards = [card for card in cards if card.total_estimated_annual_value_usd is not None]
    highest_id = valued_cards[0].opportunity_id if valued_cards else None
    notes = []
    if valued_cards:
        notes.append(
            "Highest stated annualized value is "
            f"'{valued_cards[0].name}' at "
            f"${valued_cards[0].total_estimated_annual_value_usd:,.0f} USD, calculated only "
            "from components with an amount, currency, and supported frequency."
        )
    return ComparisonMatrixResponse(
        total_compared=len(cards),
        scholarships=cards,
        highest_value_scholarship_id=highest_id,
        fully_funded_count=None,
        financial_comparison_notes=notes,
    )


def _annual_value_usd(component: FundingComponent | PublicFundingResponse) -> float | None:
    if component.amount is None or not component.currency or not component.frequency:
        return None
    rate = _USD_RATES.get(component.currency.upper())
    multiplier = _ANNUAL_MULTIPLIERS.get(component.frequency.strip().casefold())
    if rate is None or multiplier is None:
        return None
    return float(component.amount) * rate * multiplier


def _is_comparable_component(
    component: FundingComponent | PublicFundingResponse,
) -> bool:
    """Keep flattened comparisons to scholarship-wide benefits, never costs or exclusions."""
    coverage = (component.coverage_status or "").strip().casefold()
    if coverage not in _POSITIVE_COVERAGE:
        return False

    component_type = (component.component_type or "").strip().casefold()
    if component_type not in _COMPARABLE_BENEFIT_TYPES:
        return False

    scope = getattr(component, "scope", None)
    scoped_ids = (
        getattr(scope, "track_id", None)
        if scope is not None
        else getattr(component, "track_id", None),
        getattr(scope, "institution_id", None)
        if scope is not None
        else getattr(component, "institution_id", None),
        getattr(scope, "programme_id", None)
        if scope is not None
        else getattr(component, "programme_id", None),
        getattr(scope, "scholarship_programme_id", None)
        if scope is not None
        else getattr(component, "scholarship_programme_id", None),
    )
    return not any(scoped_ids)


def _coverage_indicator(coverage: str) -> bool | None:
    if coverage in _POSITIVE_COVERAGE:
        return True
    if coverage in _NEGATIVE_COVERAGE:
        return False
    return None


def _merge_coverage(current: bool | None, candidate: bool | None) -> bool | None:
    if current is True or candidate is True:
        return True
    if current is False or candidate is False:
        return False
    return None


def _coverage_label(coverage: str) -> str | None:
    if not coverage or coverage == "unknown":
        return None
    return coverage.replace("_", " ").capitalize()


def _benefit_label(component: FundingComponent | PublicFundingResponse) -> str | None:
    coverage = (component.coverage_status or "").lower()
    if coverage in _NEGATIVE_COVERAGE or coverage == "unknown":
        return None
    if component.description and component.description.strip():
        return component.description.strip()
    component_label = (component.component_type or "").replace("_", " ").strip().title()
    coverage_label = _coverage_label(coverage)
    amount_label = None
    if component.amount is not None and component.currency:
        frequency = f" / {component.frequency}" if component.frequency else ""
        amount_label = f"{component.currency.upper()} {float(component.amount):,.0f}{frequency}"
    details = [detail for detail in (coverage_label, amount_label) if detail]
    if not component_label or not details:
        return None
    return f"{component_label}: {', '.join(details)}"
