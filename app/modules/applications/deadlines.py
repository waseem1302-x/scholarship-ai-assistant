from datetime import UTC, datetime, timedelta
from enum import StrEnum


class DeadlineUrgency(StrEnum):
    UPCOMING = "upcoming"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    DEADLINE_CHANGED = "deadline_changed"
    DEADLINE_UNCERTAIN = "deadline_uncertain"


def urgency_for_deadline(
    deadline: datetime | None,
    *,
    deadline_changed: bool = False,
    deadline_uncertain: bool = False,
    now: datetime | None = None,
    due_soon_days: int = 14,
) -> DeadlineUrgency:
    """Return a deterministic student-facing deadline state."""
    if deadline_uncertain or deadline is None:
        return DeadlineUrgency.DEADLINE_UNCERTAIN
    if deadline_changed:
        return DeadlineUrgency.DEADLINE_CHANGED
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    value = deadline.replace(tzinfo=UTC) if deadline.tzinfo is None else deadline.astimezone(UTC)
    if value < current_time:
        return DeadlineUrgency.OVERDUE
    if value <= current_time + timedelta(days=due_soon_days):
        return DeadlineUrgency.DUE_SOON
    return DeadlineUrgency.UPCOMING
