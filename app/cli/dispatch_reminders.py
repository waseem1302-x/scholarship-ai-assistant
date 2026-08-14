"""Claim and deliver due in-app reminders exactly once per scheduled record."""

from collections.abc import Callable
from datetime import UTC, datetime

from app.db.session import SystemSessionLocal
from app.modules.applications.models import (
    Application,
    ApplicationNotificationPreference,
    ApplicationReminder,
    ReminderStatus,
    ReminderWorkerHealth,
)
from app.modules.operations.service import OperationalJobService
from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session


def dispatch_due_reminders(
    *,
    now: datetime | None = None,
    session_factory: Callable[[], Session] = SystemSessionLocal,
) -> int:
    """Atomically claim all currently due, opted-in reminders.

    A single UPDATE changes each eligible record from scheduled/snoozed to delivered.
    Competing workers can only claim rows still in their pre-delivery state, so retries
    and concurrent workers cannot duplicate a notification.
    """
    current_time = now or datetime.now(UTC)
    with session_factory() as session:
        operational_health = OperationalJobService(session)
        operational_health.started("reminder_dispatch")
        health = session.get(ReminderWorkerHealth, "default")
        if health is None:
            health = ReminderWorkerHealth(id="default")
            session.add(health)
        health.last_started_at = current_time
        session.commit()
        try:
            opted_out = exists(
                select(ApplicationNotificationPreference.user_id).where(
                    ApplicationNotificationPreference.user_id == Application.user_id,
                    ApplicationNotificationPreference.in_app_enabled.is_(False),
                )
            )
            eligible_applications = select(Application.id).where(~opted_out)
            claimed = session.scalars(
                update(ApplicationReminder)
                .where(
                    ApplicationReminder.application_id.in_(eligible_applications),
                    ApplicationReminder.status.in_(
                        (ReminderStatus.SCHEDULED, ReminderStatus.SNOOZED)
                    ),
                    ApplicationReminder.scheduled_at <= current_time,
                )
                .values(
                    status=ReminderStatus.DELIVERED,
                    delivered_at=current_time,
                    failure_reason=None,
                )
                .returning(ApplicationReminder.id)
            ).all()
            health.last_completed_at = current_time
            health.processed_count += len(claimed)
            health.last_error = None
            session.commit()
            operational_health.completed("reminder_dispatch", len(claimed))
            return len(claimed)
        except Exception as exc:
            session.rollback()
            health = session.get(ReminderWorkerHealth, "default")
            if health is None:
                health = ReminderWorkerHealth(id="default")
                session.add(health)
            health.failed_count += 1
            health.last_error = type(exc).__name__[:500]
            session.commit()
            operational_health.failed("reminder_dispatch", exc)
            raise


if __name__ == "__main__":
    print(dispatch_due_reminders())
