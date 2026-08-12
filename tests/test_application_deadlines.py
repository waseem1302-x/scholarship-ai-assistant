from datetime import UTC, datetime, timedelta

import pytest

from app.modules.applications.deadlines import DeadlineUrgency, urgency_for_deadline

NOW = datetime(2027, 5, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("deadline", "changed", "uncertain", "expected"),
    [
        (NOW + timedelta(days=20), False, False, DeadlineUrgency.UPCOMING),
        (NOW + timedelta(days=14), False, False, DeadlineUrgency.DUE_SOON),
        (NOW - timedelta(seconds=1), False, False, DeadlineUrgency.OVERDUE),
        (NOW + timedelta(days=30), True, False, DeadlineUrgency.DEADLINE_CHANGED),
        (NOW + timedelta(days=30), False, True, DeadlineUrgency.DEADLINE_UNCERTAIN),
        (None, False, False, DeadlineUrgency.DEADLINE_UNCERTAIN),
    ],
)
def test_deadline_urgency_is_deterministic(
    deadline: datetime | None,
    changed: bool,
    uncertain: bool,
    expected: DeadlineUrgency,
) -> None:
    assert (
        urgency_for_deadline(
            deadline,
            deadline_changed=changed,
            deadline_uncertain=uncertain,
            now=NOW,
        )
        is expected
    )
