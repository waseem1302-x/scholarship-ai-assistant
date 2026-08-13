"""Application-window state is derived at read time so history is never lost."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.modules.opportunities.models import (
    ApplicationWindowState,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Source,
)

SOURCE_FRESHNESS_DAYS = 90


@dataclass(frozen=True)
class EffectiveApplicationWindow:
    state: ApplicationWindowState
    source_is_fresh: bool
    cycle: OpportunityCycle | None


def effective_application_window(
    opportunity: Opportunity,
    source: Source | None,
    *,
    now: datetime | None = None,
) -> EffectiveApplicationWindow:
    current_time = _as_utc(now or datetime.now(UTC))
    if opportunity.status in {
        OpportunityStatus.EXPIRED,
        OpportunityStatus.ARCHIVED,
    }:
        return EffectiveApplicationWindow(ApplicationWindowState.ARCHIVED, False, None)

    cycle = _current_cycle(opportunity, current_time)
    opening = cycle.application_opening_date if cycle else opportunity.application_opening_date
    deadline = cycle.application_deadline if cycle else opportunity.application_deadline
    rolling = cycle.is_rolling if cycle else False
    source_is_fresh = bool(
        source
        and source.last_verified_at
        and _as_utc(source.last_verified_at) >= current_time - timedelta(days=SOURCE_FRESHNESS_DAYS)
    )

    if cycle and cycle.is_archived:
        return EffectiveApplicationWindow(ApplicationWindowState.ARCHIVED, source_is_fresh, cycle)
    if deadline and _as_utc(deadline) < current_time:
        return EffectiveApplicationWindow(ApplicationWindowState.CLOSED, source_is_fresh, cycle)
    if opening and _as_utc(opening) > current_time:
        return EffectiveApplicationWindow(ApplicationWindowState.UPCOMING, source_is_fresh, cycle)
    if rolling:
        return EffectiveApplicationWindow(ApplicationWindowState.ROLLING, source_is_fresh, cycle)
    if deadline is None:
        return EffectiveApplicationWindow(
            ApplicationWindowState.DEADLINE_UNKNOWN, source_is_fresh, cycle
        )
    return EffectiveApplicationWindow(ApplicationWindowState.OPEN, source_is_fresh, cycle)


def is_open_now(
    opportunity: Opportunity,
    source: Source | None,
    *,
    now: datetime | None = None,
) -> bool:
    window = effective_application_window(opportunity, source, now=now)
    return window.source_is_fresh and window.state in {
        ApplicationWindowState.OPEN,
        ApplicationWindowState.ROLLING,
    }


def _current_cycle(opportunity: Opportunity, now: datetime) -> OpportunityCycle | None:
    if not opportunity.cycles:
        return None
    eligible = [cycle for cycle in opportunity.cycles if not cycle.is_archived]
    if not eligible:
        return max(opportunity.cycles, key=lambda item: item.created_at)
    return max(
        eligible,
        key=lambda item: (
            _as_utc(item.application_deadline)
            if item.application_deadline
            else datetime.max.replace(tzinfo=UTC),
            item.created_at,
        ),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
