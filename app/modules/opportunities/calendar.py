"""RFC 5545 iCalendar (.ics) and deadline radar generator for scholarships."""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.modules.opportunities.evidence_models import ScopedDeadline
from app.modules.opportunities.materialization_models import OpportunityEvent
from app.modules.opportunities.models import Opportunity, OpportunityCycle


class CalendarLinkResponse(BaseModel):
    google_calendar_url: str
    outlook_web_url: str
    yahoo_calendar_url: str
    ics_download_url: str


class DeadlineMilestone(BaseModel):
    title: str
    date_iso: str
    days_remaining: int
    milestone_type: str  # e.g., "application_deadline", "interview", "announcement"
    urgency_badge: str  # "critical", "soon", "upcoming", "closed"
    notes: str | None = None


class OpportunityTimelineResponse(BaseModel):
    opportunity_id: str
    opportunity_name: str
    country: str
    intake_year: int | None = None
    milestones: list[DeadlineMilestone]
    status: str
    google_calendar_url: str


def _format_ics_timestamp(dt: datetime) -> str:
    utc_dt = dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def _sanitize_ics_text(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def generate_opportunity_ics(
    opportunity: Opportunity,
    cycle: OpportunityCycle | None = None,
    deadlines: list[ScopedDeadline] | None = None,
    events: list[OpportunityEvent] | None = None,
) -> str:
    """Generate an RFC 5545 .ics calendar payload for a scholarship opportunity."""
    now_str = _format_ics_timestamp(datetime.now(UTC))
    cycle_year = cycle.intake_year if cycle else opportunity.intake_year
    opp_name = opportunity.name
    country = opportunity.country or "International"
    official_url = (
        opportunity.sources[0].url if opportunity.sources else "https://scholarship-portal.gov"
    )

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Scholarship AI Assistant//Scholarship Calendar 1.0//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    # Main Application Deadline Event
    deadline_dt = cycle.application_deadline if cycle else None
    if not deadline_dt and deadlines:
        for d in deadlines:
            if d.deadline_at:
                deadline_dt = d.deadline_at
                break

    if deadline_dt:
        dtstart = _format_ics_timestamp(deadline_dt - timedelta(hours=2))
        dtend = _format_ics_timestamp(deadline_dt)
        uid = f"deadline-{opportunity.id}-{cycle_year}@scholarshipai.app"
        summary = _sanitize_ics_text(f"DEADLINE: {opp_name} ({cycle_year})")
        description = _sanitize_ics_text(
            f"Official Application Deadline for {opp_name} in {country}.\n"
            f"Official Portal: {official_url}\n"
            f"Degree Level: {opportunity.degree_level.value.upper()}\n"
            f"Funding: {opportunity.funding_type.value.upper()}"
        )
        location = _sanitize_ics_text(country)

        ics_lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_str}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"LOCATION:{location}",
                f"URL:{official_url}",
                "STATUS:CONFIRMED",
                "BEGIN:VALARM",
                "TRIGGER:-P7D",
                "ACTION:DISPLAY",
                f"DESCRIPTION:Reminder: {summary} is in 7 days!",
                "END:VALARM",
                "BEGIN:VALARM",
                "TRIGGER:-P1D",
                "ACTION:DISPLAY",
                f"DESCRIPTION:URGENT: {summary} is tomorrow!",
                "END:VALARM",
                "END:VEVENT",
            ]
        )

    # Supplementary Events (Interviews, Exams, Announcements)
    if events:
        for idx, ev in enumerate(events):
            if ev.starts_at:
                ev_start = _format_ics_timestamp(ev.starts_at)
                ev_end = _format_ics_timestamp(ev.ends_at or (ev.starts_at + timedelta(hours=1)))
                ev_uid = f"event-{opportunity.id}-{idx}@scholarshipai.app"
                ev_summary = _sanitize_ics_text(f"{opp_name}: {ev.label or ev.event_type.title()}")
                ev_desc = _sanitize_ics_text(ev.notes or f"{ev.event_type.title()} for {opp_name}")
                ics_lines.extend(
                    [
                        "BEGIN:VEVENT",
                        f"UID:{ev_uid}",
                        f"DTSTAMP:{now_str}",
                        f"DTSTART:{ev_start}",
                        f"DTEND:{ev_end}",
                        f"SUMMARY:{ev_summary}",
                        f"DESCRIPTION:{ev_desc}",
                        "STATUS:CONFIRMED",
                        "END:VEVENT",
                    ]
                )

    ics_lines.append("END:VCALENDAR")
    return "\r\n".join(ics_lines) + "\r\n"


def generate_google_calendar_url(
    title: str,
    start_dt: datetime,
    end_dt: datetime,
    details: str,
    location: str = "",
) -> str:
    """Generate a 1-click Google Calendar web creation URL."""
    base = "https://calendar.google.com/calendar/render"
    start_str = start_dt.strftime("%Y%m%dT%H%M%SZ")
    end_str = end_dt.strftime("%Y%m%dT%H%M%SZ")
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_str}/{end_str}",
        "details": details,
        "location": location,
    }
    return f"{base}?{urllib.parse.urlencode(params)}"
