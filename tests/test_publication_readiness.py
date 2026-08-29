import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import support_opportunity_for_publication
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import User, UserRole
from app.modules.opportunities.evidence_models import FieldEvidence
from app.modules.opportunities.models import (
    DuplicateSuggestion,
    DuplicateSuggestionStatus,
    Opportunity,
    OpportunityStatus,
    VerificationStatus,
)
from app.modules.opportunities.publication_readiness import (
    PUBLICATION_READINESS_POLICY_VERSION,
    PublicationReadinessPolicy,
)

PASSWORD = "PublicationPassword123"


def _headers(client: TestClient, db_session: Session) -> dict[str, str]:
    db_session.add(
        User(
            id=uuid.uuid4(),
            email="publication-admin@example.com",
            password_hash=hash_password(PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    db_session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "publication-admin@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Synthetic Publication Scholarship",
        "provider_name": "Synthetic Official Provider",
        "country": "Malaysia",
        "degree_level": "masters",
        "field_eligibility": "Computer science",
        "nationality_eligibility": "International applicants",
        "application_deadline": "2027-05-30T23:59:59Z",
        "intake_year": 2027,
        "funding_type": "full",
        "funding_policy": "Official policy confirms full tuition and a monthly stipend.",
        "tuition_coverage_status": "confirmed",
        "stipend_coverage_status": "confirmed",
        "accommodation_coverage_status": "not_covered",
        "travel_coverage_status": "not_covered",
        "insurance_coverage_status": "not_covered",
        "fees_coverage_status": "not_covered",
        "tuition_coverage": "Full tuition is covered.",
        "monthly_stipend_amount": "1200.00",
        "monthly_stipend_currency": "EUR",
        "english_language_requirement": "English proof is required unless waived.",
        "standardized_test_requirement": "No standardized test is required.",
        "minimum_academic_requirement": "A relevant bachelor's degree is required.",
        "required_documents": ["Transcript", "Passport"],
        "application_method": "Apply through the official portal.",
        "application_url": "https://official.example/apply",
        "status": "draft",
        "data_confidence": "high",
        "source": {
            "url": "https://official.example/scholarship",
            "source_type": "official",
            "title": "Synthetic official scholarship page",
            "relevant_excerpt": "Synthetic source used only for deterministic readiness tests.",
            "verification_status": "needs_review",
        },
    }
    payload.update(overrides)
    return payload


def _create(
    client: TestClient,
    db_session: Session,
    headers: dict[str, str],
    **overrides: object,
) -> tuple[dict, Opportunity]:
    response = client.post(
        "/api/v1/admin/opportunities", json=_payload(**overrides), headers=headers
    )
    assert response.status_code == 201, response.text
    body = response.json()
    support_opportunity_for_publication(body["id"], fill_missing_values=False)
    db_session.expire_all()
    opportunity = db_session.get(Opportunity, uuid.UUID(body["id"]))
    assert opportunity is not None
    return body, opportunity


@pytest.mark.parametrize(
    ("overrides", "reason_code"),
    [
        ({"application_deadline": None}, "deadline_unknown"),
        (
            {"funding_type": "partial", "tuition_coverage_status": "unknown"},
            "tuition_unknown",
        ),
        (
            {"funding_type": "partial", "stipend_coverage_status": "unknown"},
            "stipend_unknown",
        ),
        ({"application_url": None}, "application_url_missing"),
        ({"nationality_eligibility": None}, "nationality_missing"),
        ({"minimum_academic_requirement": None}, "academic_requirement_missing"),
        ({"required_documents": []}, "documents_missing"),
    ],
)
def test_mandatory_unknown_or_missing_fact_blocks_publication(
    client: TestClient,
    db_session: Session,
    overrides: dict[str, object],
    reason_code: str,
) -> None:
    headers = _headers(client, db_session)
    body, opportunity = _create(client, db_session, headers, **overrides)

    readiness = PublicationReadinessPolicy(db_session).evaluate(opportunity)

    assert readiness.ready is False
    assert reason_code in {reason.reason_code for reason in readiness.blocking_reasons}
    response = client.post(
        f"/api/v1/admin/opportunities/{body['id']}/review-actions",
        json={"action": "publish", "source_id": body["sources"][0]["id"]},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "publication_readiness_blocked"


def test_mismatched_evidence_excerpt_blocks_publication(
    client: TestClient, db_session: Session
) -> None:
    headers = _headers(client, db_session)
    _, opportunity = _create(client, db_session, headers)
    evidence = db_session.scalar(
        select(FieldEvidence).where(
            FieldEvidence.entity_id == opportunity.id,
            FieldEvidence.field_path == "application_url",
        )
    )
    assert evidence is not None
    evidence.excerpt = "This excerpt does not match the immutable snapshot."
    db_session.commit()

    readiness = PublicationReadinessPolicy(db_session).evaluate(opportunity)

    assert readiness.ready is False
    assert any(
        reason.field_path == "application" and reason.reason_code == "evidence_invalid"
        for reason in readiness.blocking_reasons
    )


def test_conflicting_and_stale_official_sources_block_readiness(
    client: TestClient, db_session: Session
) -> None:
    headers = _headers(client, db_session)
    _, opportunity = _create(client, db_session, headers)
    source = opportunity.sources[0]
    source.last_verified_at = datetime.now(UTC) - timedelta(days=91)
    db_session.commit()

    stale = PublicationReadinessPolicy(db_session).evaluate(opportunity)
    assert "source_stale" in {reason.reason_code for reason in stale.blocking_reasons}

    source.verification_status = VerificationStatus.CONFLICTING_INFORMATION
    source.last_verified_at = datetime.now(UTC)
    db_session.commit()
    conflicting = PublicationReadinessPolicy(db_session).evaluate(opportunity)
    assert "official_source_conflict" in {
        reason.reason_code for reason in conflicting.blocking_reasons
    }


def test_pending_duplicate_blocks_but_dismissed_route_variant_does_not(
    client: TestClient, db_session: Session
) -> None:
    headers = _headers(client, db_session)
    _, opportunity = _create(client, db_session, headers)
    _, variant = _create(
        client,
        db_session,
        headers,
        name="Synthetic Publication Scholarship — Country Route",
        cycle_id="2028-country-route",
        intake_year=2028,
        source={
            **_payload()["source"],
            "url": "https://official.example/scholarship/country-route",
        },
    )
    suggestion = DuplicateSuggestion(
        opportunity_id=opportunity.id,
        matched_opportunity_id=variant.id,
        score="0.9000",
        status=DuplicateSuggestionStatus.PENDING,
    )
    db_session.add(suggestion)
    db_session.commit()

    blocked = PublicationReadinessPolicy(db_session).evaluate(opportunity)
    assert "duplicate_pending" in {reason.reason_code for reason in blocked.blocking_reasons}

    suggestion.status = DuplicateSuggestionStatus.DISMISSED
    db_session.commit()
    ready = PublicationReadinessPolicy(db_session).evaluate(opportunity)
    assert ready.ready is True
    assert ready.supported_required_count == ready.required_count == 15


def test_direct_api_publish_cannot_bypass_readiness(
    client: TestClient, db_session: Session
) -> None:
    headers = _headers(client, db_session)
    response = client.post("/api/v1/admin/opportunities", json=_payload(), headers=headers)
    assert response.status_code == 201
    created = response.json()

    publish = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={"action": "publish", "source_id": created["sources"][0]["id"]},
        headers=headers,
    )

    assert publish.status_code == 409
    db_session.expire_all()
    opportunity = db_session.get(Opportunity, uuid.UUID(created["id"]))
    assert opportunity is not None
    assert opportunity.status is OpportunityStatus.DRAFT
    assert opportunity.publication_completeness == "incomplete"


def test_admin_only_unknown_placeholder_cannot_reach_public_serializer(
    client: TestClient, db_session: Session
) -> None:
    headers = _headers(client, db_session)
    body, opportunity = _create(
        client,
        db_session,
        headers,
        accommodation_coverage="Unknown — verify from official source",
    )
    readiness = PublicationReadinessPolicy(db_session).evaluate(opportunity)
    assert "admin_only_unknown_placeholder" in {
        reason.reason_code for reason in readiness.blocking_reasons
    }

    opportunity.status = OpportunityStatus.ACTIVE
    opportunity.publication_completeness = "complete_core"
    opportunity.publication_readiness_policy_version = PUBLICATION_READINESS_POLICY_VERSION
    opportunity.publication_readiness_evaluated_at = datetime.now(UTC)
    opportunity.next_review_at = datetime.now(UTC) + timedelta(days=30)
    db_session.commit()

    assert client.get(f"/api/v1/opportunities/{body['id']}").status_code == 404


def test_ready_publish_persists_policy_and_expiry(client: TestClient, db_session: Session) -> None:
    headers = _headers(client, db_session)
    body, _ = _create(client, db_session, headers)

    publish = client.post(
        f"/api/v1/admin/opportunities/{body['id']}/review-actions",
        json={"action": "publish", "source_id": body["sources"][0]["id"]},
        headers=headers,
    )

    assert publish.status_code == 200, publish.text
    readiness_response = client.get(
        f"/api/v1/admin/opportunities/{body['id']}/publication-readiness",
        headers=headers,
    )
    assert readiness_response.status_code == 200
    assert readiness_response.json()["ready"] is True
    assert readiness_response.json()["required_count"] == 15
    db_session.expire_all()
    opportunity = db_session.get(Opportunity, uuid.UUID(body["id"]))
    assert opportunity is not None
    assert opportunity.publication_completeness == "complete_core"
    assert opportunity.publication_readiness_policy_version == PUBLICATION_READINESS_POLICY_VERSION
    assert opportunity.publication_readiness_evaluated_at is not None
    assert opportunity.next_review_at is not None


def test_incomplete_active_record_is_hidden_and_enters_remediation_queue(
    client: TestClient, db_session: Session
) -> None:
    headers = _headers(client, db_session)
    body, opportunity = _create(client, db_session, headers)
    opportunity.status = OpportunityStatus.ACTIVE
    opportunity.publication_completeness = "incomplete"
    db_session.commit()

    listing = client.get("/api/v1/opportunities")
    detail = client.get(f"/api/v1/opportunities/{body['id']}")
    family = client.get(f"/api/v1/opportunities/{body['id']}/family")
    queue = client.get("/api/v1/admin/review-queue", headers=headers)

    assert listing.status_code == 200 and listing.json()["items"] == []
    assert detail.status_code == 404
    assert family.status_code == 404
    assert queue.status_code == 200
    item = next(item for item in queue.json()["items"] if item["opportunity"]["id"] == body["id"])
    assert any(reason["code"] == "publication_readiness_incomplete" for reason in item["reasons"])
    assert item["publication_readiness"]["policy_version"] == (PUBLICATION_READINESS_POLICY_VERSION)
