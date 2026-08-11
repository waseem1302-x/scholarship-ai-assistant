from datetime import UTC, datetime, timedelta

import pytest

from app.modules.opportunities.lifecycle import effective_application_window, is_open_now
from app.modules.opportunities.models import (
    ApplicationWindowState,
    DegreeLevel,
    Opportunity,
    OpportunityCycle,
    OpportunityStatus,
    Source,
    SourceType,
    VerificationStatus,
)

NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)


def opportunity(**changes: object) -> Opportunity:
    status = changes.pop("status", OpportunityStatus.ACTIVE)
    record = Opportunity(
        name="Lifecycle Scholarship",
        country="Malaysia",
        degree_level=DegreeLevel.MASTERS,
        status=status,
        **changes,
    )
    record.sources = [
        Source(
            url="https://example.edu/lifecycle",
            source_type=SourceType.OFFICIAL,
            title="Official lifecycle source",
            relevant_excerpt="Official source describes this scholarship application window.",
            verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
            last_verified_at=NOW,
        )
    ]
    return record


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"application_deadline": NOW - timedelta(seconds=1)}, ApplicationWindowState.CLOSED),
        ({"application_opening_date": NOW + timedelta(seconds=1)}, ApplicationWindowState.UPCOMING),
        ({"application_deadline": NOW + timedelta(days=2)}, ApplicationWindowState.OPEN),
        ({}, ApplicationWindowState.DEADLINE_UNKNOWN),
        ({"status": OpportunityStatus.ARCHIVED}, ApplicationWindowState.ARCHIVED),
    ],
)
def test_effective_window_handles_past_current_future_unknown_and_archived(
    changes: dict[str, object], expected: ApplicationWindowState
) -> None:
    record = opportunity(**changes)

    assert effective_application_window(record, record.sources[0], now=NOW).state is expected


def test_rolling_cycle_is_open_but_unknown_deadline_is_not() -> None:
    rolling = opportunity()
    rolling.cycles = [
        OpportunityCycle(is_rolling=True, application_opening_date=NOW - timedelta(days=1))
    ]
    unknown = opportunity()

    assert is_open_now(rolling, rolling.sources[0], now=NOW)
    assert not is_open_now(unknown, unknown.sources[0], now=NOW)


def test_open_now_requires_a_fresh_official_source() -> None:
    record = opportunity(application_deadline=NOW + timedelta(days=1))
    record.sources[0].last_verified_at = NOW - timedelta(days=91)

    assert not is_open_now(record, record.sources[0], now=NOW)
