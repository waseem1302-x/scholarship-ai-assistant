"""Scholarship Benefits & Funding Comparator Engine."""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.opportunities.evidence_models import FundingComponent
from app.modules.opportunities.models import FundingType, Opportunity

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


class ScholarshipFundingCard(BaseModel):
    opportunity_id: str
    name: str
    provider: str
    country: str
    degree_level: str
    funding_type: str
    tuition_coverage: str
    monthly_stipend_text: str | None = None
    monthly_stipend_usd: float | None = None
    annual_stipend_usd: float | None = None
    travel_airfare_covered: bool = False
    health_insurance_covered: bool = False
    housing_covered: bool = False
    visa_allowance_covered: bool = False
    total_estimated_annual_value_usd: float = 0.0
    benefits_list: list[str] = []


class ComparisonMatrixResponse(BaseModel):
    total_compared: int
    scholarships: list[ScholarshipFundingCard]
    highest_value_scholarship_id: str | None = None
    fully_funded_count: int = 0
    financial_comparison_notes: list[str] = []


def build_funding_comparison(
    opportunities_data: list[tuple[Opportunity, list[FundingComponent]]],
) -> ComparisonMatrixResponse:
    """Build a side-by-side normalized financial comparison matrix."""
    cards: list[ScholarshipFundingCard] = []

    for opp, components in opportunities_data:
        tuition_desc = "Not Specified"
        monthly_stipend_text = None
        monthly_usd = None
        annual_stipend_usd = None
        airfare = False
        health = False
        housing = False
        visa = False
        benefits: list[str] = []
        estimated_annual = 0.0

        for fc in components:
            comp_type = (fc.component_type or "").lower()
            amount = float(fc.amount) if fc.amount is not None else None
            curr = (fc.currency or "USD").upper()
            rate = _USD_RATES.get(curr, 1.0)

            # Tuition Check
            if "tuition" in comp_type or "fee" in comp_type:
                tuition_desc = (
                    "100% Full Tuition Covered"
                    if fc.coverage_status in ("full", "confirmed")
                    else (fc.description or "Tuition Assistance")
                )
                benefits.append("Full Tuition Waiver" if "100%" in tuition_desc else tuition_desc)
                estimated_annual += 20_000.0  # Average benchmark annual tuition value

            # Stipend Check
            elif "stipend" in comp_type or "living" in comp_type or "allowance" in comp_type:
                freq = (fc.frequency or "month").lower()
                if amount:
                    monthly_stipend_text = f"{curr} {amount:,.0f} / {freq}"
                    monthly_val = amount * rate if "month" in freq else (amount * rate / 12)
                    monthly_usd = round(monthly_val, 2)
                    annual_stipend_usd = round(monthly_val * 12, 2)
                    estimated_annual += annual_stipend_usd
                    benefits.append(f"Living Allowance: {monthly_stipend_text}")
                else:
                    monthly_stipend_text = fc.description or "Living Stipend Included"
                    benefits.append(monthly_stipend_text)
                    estimated_annual += 12_000.0

            # Travel / Airfare
            elif "travel" in comp_type or "airfare" in comp_type or "flight" in comp_type:
                airfare = True
                benefits.append("Round-trip International Airfare")
                estimated_annual += 1_500.0

            # Health Insurance
            elif "health" in comp_type or "insurance" in comp_type or "medical" in comp_type:
                health = True
                benefits.append("Comprehensive Health & Accident Insurance")
                estimated_annual += 1_200.0

            # Housing / Accommodation
            elif "housing" in comp_type or "dormitory" in comp_type or "accommodation" in comp_type:
                housing = True
                benefits.append("Free University Accommodation / Housing Subsidy")
                estimated_annual += 4_000.0

            # Visa / Settlement
            elif "visa" in comp_type or "settlement" in comp_type:
                visa = True
                benefits.append("Visa Application & Arrival Allowance")
                estimated_annual += 500.0

        if not benefits:
            if opp.funding_type == FundingType.FULL:
                tuition_desc = "100% Tuition Covered"
                benefits = [
                    "Full Tuition Exemption",
                    "Monthly Living Stipend",
                    "Airfare & Insurance",
                ]
                estimated_annual = 35_000.0
            else:
                benefits = [f"Funding Type: {opp.funding_type.value.title()}"]
                estimated_annual = 10_000.0

        cards.append(
            ScholarshipFundingCard(
                opportunity_id=str(opp.id),
                name=opp.name,
                provider=(
                    opp.provider.name
                    if getattr(opp, "provider", None)
                    else (getattr(opp, "provider_name", None) or "Official Provider")
                ),
                country=opp.country or "International",
                degree_level=opp.degree_level.value.upper(),
                funding_type=opp.funding_type.value.upper(),
                tuition_coverage=tuition_desc,
                monthly_stipend_text=monthly_stipend_text,
                monthly_stipend_usd=monthly_usd,
                annual_stipend_usd=annual_stipend_usd,
                travel_airfare_covered=airfare,
                health_insurance_covered=health,
                housing_covered=housing,
                visa_allowance_covered=visa,
                total_estimated_annual_value_usd=round(estimated_annual, 2),
                benefits_list=benefits,
            )
        )

    # Sort cards by estimated annual value descending
    cards.sort(key=lambda c: c.total_estimated_annual_value_usd, reverse=True)
    highest_id = cards[0].opportunity_id if cards else None
    fully_funded = sum(1 for c in cards if c.funding_type == "FULL")

    notes = []
    if cards:
        notes.append(
            "Top funded option is "
            f"'{cards[0].name}' with ~${cards[0].total_estimated_annual_value_usd:,.0f} "
            "USD annual estimated benefit."
        )
    if fully_funded > 0:
        notes.append(
            f"{fully_funded} of {len(cards)} scholarships provide comprehensive 100% full coverage."
        )

    return ComparisonMatrixResponse(
        total_compared=len(cards),
        scholarships=cards,
        highest_value_scholarship_id=highest_id,
        fully_funded_count=fully_funded,
        financial_comparison_notes=notes,
    )
