"""Deterministic claim extraction for structured public-source formats."""

from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimEntityType,
    ClaimExtractionOutput,
    ClaimObjective,
    ClaimScope,
    ClaimValue,
    ExtractedClaim,
    ObjectiveCoverageState,
)


@dataclass(frozen=True, slots=True)
class _CalendarProperty:
    name: str
    parameters: dict[str, str]
    value: str
    excerpt: str
    start: int
    end: int


def extract_calendar_claims(text: str) -> ClaimExtractionOutput | None:
    """Convert public iCalendar events to exact-span timeline claims without AI."""

    events = _calendar_events(text)
    if not events:
        return None
    claims: list[ExtractedClaim] = []
    for order, event in enumerate(events):
        values = {item.name: item for item in event}
        summary = values.get("SUMMARY")
        start = values.get("DTSTART")
        if summary is None or start is None:
            continue
        uid = values.get("UID")
        entity_seed = uid.value if uid else f"{summary.value}|{start.value}"
        entity_key = "calendar_" + hashlib.sha256(entity_seed.encode()).hexdigest()[:24]
        label = _unescape_calendar_text(summary.value)
        claims.extend(
            (
                _calendar_claim(
                    entity_key,
                    "event_type",
                    "schedule_event",
                    summary,
                ),
                _calendar_claim(entity_key, "label", label, summary),
                _calendar_claim(
                    entity_key,
                    "starts_at",
                    _calendar_datetime(start),
                    start,
                ),
            )
        )
        timezone = start.parameters.get("TZID")
        if timezone:
            claims.append(_calendar_claim(entity_key, "timezone", timezone, start))
        description = values.get("DESCRIPTION")
        if description is not None and description.value.strip():
            claims.append(
                _calendar_claim(
                    entity_key,
                    "notes",
                    _unescape_calendar_text(description.value),
                    description,
                )
            )
        claims.append(_calendar_claim(entity_key, "display_order", order, summary))
    if not claims:
        return None
    return ClaimExtractionOutput(
        objective=ClaimObjective.APPLICATION_TIMELINE,
        coverage_state=ObjectiveCoverageState.COMPLETE,
        claims=claims,
        unknown_objectives=[],
        conflicts=[],
        warnings=[],
    )


def _calendar_events(text: str) -> list[list[_CalendarProperty]]:
    events: list[list[_CalendarProperty]] = []
    current: list[_CalendarProperty] | None = None
    for item in _calendar_properties(text):
        if item.name == "BEGIN" and item.value.casefold() == "vevent":
            current = []
        elif item.name == "END" and item.value.casefold() == "vevent":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None:
            current.append(item)
    return events


def _calendar_properties(text: str) -> list[_CalendarProperty]:
    logical: list[tuple[str, int, int]] = []
    offset = 0
    for raw in text.splitlines(keepends=True):
        line_end = offset + len(raw.rstrip("\r\n"))
        content = raw.rstrip("\r\n")
        if content.startswith((" ", "\t")) and logical:
            previous, start, _end = logical[-1]
            logical[-1] = (previous + content[1:], start, line_end)
        else:
            logical.append((content, offset, line_end))
        offset += len(raw)
    properties: list[_CalendarProperty] = []
    for line, start, end in logical:
        if ":" not in line:
            continue
        descriptor, value = line.split(":", 1)
        parts = descriptor.split(";")
        parameters = {
            key.upper(): parameter
            for item in parts[1:]
            if "=" in item
            for key, parameter in (item.split("=", 1),)
        }
        properties.append(
            _CalendarProperty(
                name=parts[0].upper(),
                parameters=parameters,
                value=value,
                excerpt=text[start:end],
                start=start,
                end=end,
            )
        )
    return properties


def _calendar_datetime(item: _CalendarProperty) -> str:
    value = item.value.strip()
    formats = (
        (r"^\d{8}$", "%Y%m%d"),
        (r"^\d{8}T\d{6}Z$", "%Y%m%dT%H%M%SZ"),
        (r"^\d{8}T\d{6}$", "%Y%m%dT%H%M%S"),
    )
    for pattern, date_format in formats:
        if not re.match(pattern, value):
            continue
        parsed = datetime.strptime(value, date_format)
        if value.endswith("Z"):
            parsed = parsed.replace(tzinfo=UTC)
        elif timezone := item.parameters.get("TZID"):
            with suppress(ZoneInfoNotFoundError):
                parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
        return parsed.isoformat()
    return value


def _calendar_claim(
    entity_key: str,
    field_path: str,
    value: str | int,
    evidence: _CalendarProperty,
) -> ExtractedClaim:
    return ExtractedClaim(
        entity_type=ClaimEntityType.EVENT,
        entity_key=entity_key,
        field_path=field_path,
        value=ClaimValue(
            string_value=value if isinstance(value, str) else None,
            decimal_value=None,
            integer_value=value if isinstance(value, int) else None,
            boolean_value=None,
            string_list_value=None,
        ),
        scope=ClaimScope(),
        excerpt=evidence.excerpt,
        excerpt_start=evidence.start,
        excerpt_end=evidence.end,
        basis="normalized",
    )


def _unescape_calendar_text(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


__all__ = ["extract_calendar_claims"]
