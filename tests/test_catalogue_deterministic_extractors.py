from app.modules.catalogue_ingestion.claim_schemas import ClaimEntityType, ClaimObjective
from app.modules.catalogue_ingestion.deterministic_extractors import extract_calendar_claims


def test_calendar_is_extracted_without_a_model_call_and_keeps_exact_evidence() -> None:
    text = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:stage-two@example.edu
DTSTART;TZID=Europe/Moscow:20261116T000000
DTEND;TZID=Europe/Moscow:20261117T000000
SUMMARY:Second Stage registration deadline
DESCRIPTION:Participants can no longer select a time slot after this deadline.
END:VEVENT
END:VCALENDAR"""

    output = extract_calendar_claims(text)

    assert output is not None
    assert output.objective is ClaimObjective.APPLICATION_TIMELINE
    assert {claim.field_path for claim in output.claims} >= {
        "event_type",
        "starts_at",
        "timezone",
        "label",
        "notes",
    }
    assert all(
        text[claim.excerpt_start : claim.excerpt_end] == claim.excerpt
        for claim in output.claims
    )
    assert {claim.entity_type for claim in output.claims} == {ClaimEntityType.EVENT}


def test_invalid_calendar_returns_no_deterministic_claims() -> None:
    assert extract_calendar_claims("ordinary scholarship text") is None
