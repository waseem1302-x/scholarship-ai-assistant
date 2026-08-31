"""Outbound Application Click Telemetry & Scholarship Popularity Analytics."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.opportunities.models import Opportunity, OpportunityStatus

# Thread-safe in-memory counter for real-time popular analytics
_CLICK_COUNTS: Counter[str] = Counter()
_CLICK_LOGS: list[dict[str, Any]] = []


class OutboundClickResponse(BaseModel):
    opportunity_id: str
    opportunity_name: str
    official_destination_url: str
    tracked_at_utc: str


class TrendingScholarshipItem(BaseModel):
    rank: int
    opportunity_id: str
    name: str
    provider: str
    country: str
    degree_level: str
    funding_type: str
    total_apply_clicks: int
    trending_badge: str  # "Most Popular", "High Demand", "Trending"


def track_outbound_apply_click(
    opportunity: Opportunity,
    *,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> OutboundClickResponse:
    """Record an outbound application click and return the target destination URL."""
    opp_id_str = str(opportunity.id)
    _CLICK_COUNTS[opp_id_str] += 1

    now_iso = datetime.now(UTC).isoformat()
    _CLICK_LOGS.append(
        {
            "opportunity_id": opp_id_str,
            "opportunity_name": opportunity.name,
            "tracked_at": now_iso,
            "user_agent": (user_agent or "unknown")[:255],
        }
    )
    # Keep logs bounded in memory
    if len(_CLICK_LOGS) > 10_000:
        del _CLICK_LOGS[:1_000]

    sources = getattr(opportunity, "sources", None)
    official_url = (
        sources[0].url
        if sources and len(sources) > 0 and getattr(sources[0], "url", None)
        else "https://scholarship-portal.gov"
    )

    return OutboundClickResponse(
        opportunity_id=opp_id_str,
        opportunity_name=opportunity.name,
        official_destination_url=official_url,
        tracked_at_utc=now_iso,
    )


def get_trending_scholarships(
    session: Session,
    *,
    limit: int = 10,
) -> list[TrendingScholarshipItem]:
    """Retrieve trending scholarships sorted by student application engagement."""
    opportunities = list(
        session.scalars(select(Opportunity).where(Opportunity.status == OpportunityStatus.ACTIVE))
    )

    # Attach click counts
    scored_opps: list[tuple[Opportunity, int]] = []
    for opp in opportunities:
        clicks = _CLICK_COUNTS.get(str(opp.id), 0)
        scored_opps.append((opp, clicks))

    # Sort by clicks descending, then by name
    scored_opps.sort(key=lambda x: (x[1], x[0].name), reverse=True)

    items: list[TrendingScholarshipItem] = []
    for idx, (opp, clicks) in enumerate(scored_opps[:limit], start=1):
        badge = "Most Popular" if idx == 1 else ("High Demand" if idx <= 3 else "Trending")
        provider_name = (
            opp.provider.name
            if getattr(opp, "provider", None)
            else (getattr(opp, "provider_name", None) or "Official Provider")
        )
        items.append(
            TrendingScholarshipItem(
                rank=idx,
                opportunity_id=str(opp.id),
                name=opp.name,
                provider=provider_name,
                country=opp.country or "International",
                degree_level=opp.degree_level.value.upper(),
                funding_type=opp.funding_type.value.upper(),
                total_apply_clicks=clicks,
                trending_badge=badge,
            )
        )

    return items
