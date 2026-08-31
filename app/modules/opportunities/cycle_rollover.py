"""Annual Cycle Auto-Rollover & Lifecycle State Machine for scholarships."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel

from app.modules.opportunities.models import ApplicationWindowState, Opportunity, OpportunityCycle


class CycleUrgencyBadge(StrEnum):
    OPEN = "open"
    CLOSING_SOON = "closing_soon"
    CLOSED = "closed"
    UPCOMING_ESTIMATED = "upcoming_estimated"
    ROLLING = "rolling"


class CycleStateInfo(BaseModel):
    state: ApplicationWindowState
    badge_label: str
    badge_color: str  # "emerald", "amber", "rose", "blue", "gray"
    days_remaining: int | None
    is_open: bool
    deadline_iso: str | None
    next_cycle_estimated_open: str | None
    public_status_message: str


def determine_cycle_state(
    opportunity: Opportunity,
    cycle: OpportunityCycle | None = None,
    reference_dt: datetime | None = None,
) -> CycleStateInfo:
    """Compute the real-time annual cycle state and next intake estimations."""
    now = reference_dt or datetime.now(UTC)

    # Check if explicitly rolling
    is_rolling = getattr(opportunity, "catalogue_is_rolling", False) or (cycle and cycle.is_rolling)
    if is_rolling:
        return CycleStateInfo(
            state=ApplicationWindowState.ROLLING,
            badge_label="Rolling Admissions",
            badge_color="blue",
            days_remaining=None,
            is_open=True,
            deadline_iso=None,
            next_cycle_estimated_open=None,
            public_status_message="Applications are accepted on a continuous rolling basis.",
        )

    # Resolve deadline
    deadline_dt = cycle.application_deadline if cycle else None
    if not deadline_dt and getattr(opportunity, "application_deadline", None):
        deadline_dt = opportunity.application_deadline

    if not deadline_dt:
        return CycleStateInfo(
            state=ApplicationWindowState.OPEN,
            badge_label="Open for Application",
            badge_color="emerald",
            days_remaining=None,
            is_open=True,
            deadline_iso=None,
            next_cycle_estimated_open=None,
            public_status_message="Open for applications. Check official portal for exact dates.",
        )

    deadline_utc = (
        deadline_dt.astimezone(UTC) if deadline_dt.tzinfo else deadline_dt.replace(tzinfo=UTC)
    )
    diff = deadline_utc - now
    days_left = int(diff.total_seconds() / 86400)

    # 1. Past Deadline -> Closed with Next Cycle Estimation
    if days_left < 0:
        # Estimate next intake year
        current_year = (
            cycle.intake_year
            if (cycle and cycle.intake_year)
            else (opportunity.intake_year or now.year)
        )
        next_intake_year = current_year + 1

        # Estimate opening month (typically 3-6 months prior to deadline)
        est_month_name = deadline_utc.strftime("%B")
        next_open_str = f"{est_month_name} {next_intake_year - 1}"

        return CycleStateInfo(
            state=ApplicationWindowState.CLOSED,
            badge_label=f"Closed for {current_year}",
            badge_color="rose",
            days_remaining=None,
            is_open=False,
            deadline_iso=deadline_utc.isoformat(),
            next_cycle_estimated_open=f"{next_open_str} (for {next_intake_year} intake)",
            public_status_message=(
                f"The {current_year} application cycle is currently closed. "
                f"The next cycle ({next_intake_year}) is estimated to open around "
                f"{est_month_name} {next_intake_year - 1}. "
                "Set a deadline alert to be notified when submissions reopen."
            ),
        )

    # 2. Closing soon (within 14 days)
    elif days_left <= 14:
        return CycleStateInfo(
            state=ApplicationWindowState.OPEN,
            badge_label=f"Closing in {days_left}d",
            badge_color="amber",
            days_remaining=days_left,
            is_open=True,
            deadline_iso=deadline_utc.isoformat(),
            next_cycle_estimated_open=None,
            public_status_message=(
                f"Urgent: Application portal closes in {days_left} "
                f"day{'s' if days_left != 1 else ''} on "
                f"{deadline_utc.strftime('%B %d, %Y')}."
            ),
        )

    # 3. Open and active
    else:
        return CycleStateInfo(
            state=ApplicationWindowState.OPEN,
            badge_label="Open Now",
            badge_color="emerald",
            days_remaining=days_left,
            is_open=True,
            deadline_iso=deadline_utc.isoformat(),
            next_cycle_estimated_open=None,
            public_status_message=(
                "Currently accepting applications until "
                f"{deadline_utc.strftime('%B %d, %Y')} ({days_left} days remaining)."
            ),
        )
