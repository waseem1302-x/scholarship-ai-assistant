"""Automated Deadline Watchdog Notification & Digest Engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class AlertUrgency(StrEnum):
    CRITICAL = "critical"  # <= 3 days
    HIGH = "high"  # 4 - 7 days
    MEDIUM = "medium"  # 8 - 14 days
    INFO = "info"  # 15 - 30 days


class WatchdogAlert(BaseModel):
    user_id: str
    user_email: str | None = None
    opportunity_id: str
    opportunity_name: str
    country: str
    deadline_at: datetime
    deadline_text: str
    days_remaining: int
    urgency: AlertUrgency
    subject_line: str
    email_body_preview: str
    action_url: str


class WatchdogDigestSummary(BaseModel):
    scanned_at_utc: str
    total_applications_scanned: int
    critical_alerts_count: int
    high_alerts_count: int
    medium_alerts_count: int
    total_alerts_generated: int
    alerts: list[WatchdogAlert]


def evaluate_deadline_alert(
    *,
    user_id: str,
    user_email: str | None,
    opportunity_id: str,
    opportunity_name: str,
    country: str,
    deadline_at: datetime,
    reference_dt: datetime | None = None,
    portal_base_url: str = "https://scholarshipai.app",
) -> WatchdogAlert | None:
    """Evaluate whether a specific deadline requires a notification trigger."""
    now = reference_dt or datetime.now(UTC)
    deadline_utc = (
        deadline_at.astimezone(UTC) if deadline_at.tzinfo else deadline_at.replace(tzinfo=UTC)
    )

    diff = deadline_utc - now
    total_seconds = diff.total_seconds()
    days_remaining = int(diff.days)

    if total_seconds < 0:
        return None  # Already closed

    urgency: AlertUrgency | None = None
    subject: str = ""

    if days_remaining <= 1:
        urgency = AlertUrgency.CRITICAL
        subject = f"🚨 URGENT: {opportunity_name} closes tomorrow!"
    elif days_remaining <= 3:
        urgency = AlertUrgency.CRITICAL
        subject = f"⚠️ Only {days_remaining} days left for {opportunity_name}"
    elif days_remaining <= 7:
        urgency = AlertUrgency.HIGH
        subject = f"📅 1 Week Reminder: {opportunity_name} deadline approaching"
    elif days_remaining <= 14:
        urgency = AlertUrgency.MEDIUM
        subject = f"⏰ 2 Weeks Notice: Complete your {opportunity_name} application"
    elif days_remaining <= 30:
        urgency = AlertUrgency.INFO
        subject = f"📌 30-Day Reminder: {opportunity_name} in {country}"
    else:
        return None  # More than 30 days away, no immediate alert

    deadline_formatted = deadline_utc.strftime("%B %d, %Y at %H:%M UTC")
    action_url = f"{portal_base_url}/scholarships/{opportunity_id}"

    body_preview = (
        f"The application deadline for {opportunity_name} ({country}) is on {deadline_formatted}. "
        f"You have {days_remaining} day{'s' if days_remaining != 1 else ''} remaining "
        "to finalize and submit your application."
    )

    return WatchdogAlert(
        user_id=str(user_id),
        user_email=user_email,
        opportunity_id=str(opportunity_id),
        opportunity_name=opportunity_name,
        country=country,
        deadline_at=deadline_utc,
        deadline_text=deadline_formatted,
        days_remaining=days_remaining,
        urgency=urgency,
        subject_line=subject,
        email_body_preview=body_preview,
        action_url=action_url,
    )


def generate_watchdog_digest(
    items: list[dict[str, Any]],
    *,
    reference_dt: datetime | None = None,
) -> WatchdogDigestSummary:
    """Scan multiple application deadlines and compile a structured watchdog digest."""
    now = reference_dt or datetime.now(UTC)
    alerts: list[WatchdogAlert] = []

    for item in items:
        alert = evaluate_deadline_alert(
            user_id=item["user_id"],
            user_email=item.get("user_email"),
            opportunity_id=item["opportunity_id"],
            opportunity_name=item["opportunity_name"],
            country=item.get("country", "International"),
            deadline_at=item["deadline_at"],
            reference_dt=now,
        )
        if alert is not None:
            alerts.append(alert)

    # Sort alerts by days remaining ascending (most urgent first)
    alerts.sort(key=lambda a: (a.days_remaining, a.opportunity_name))

    crit = sum(1 for a in alerts if a.urgency == AlertUrgency.CRITICAL)
    high = sum(1 for a in alerts if a.urgency == AlertUrgency.HIGH)
    med = sum(1 for a in alerts if a.urgency == AlertUrgency.MEDIUM)

    return WatchdogDigestSummary(
        scanned_at_utc=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        total_applications_scanned=len(items),
        critical_alerts_count=crit,
        high_alerts_count=high,
        medium_alerts_count=med,
        total_alerts_generated=len(alerts),
        alerts=alerts,
    )
