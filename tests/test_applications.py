import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import User, UserRole
from tests.test_opportunities import publish_opportunity

PASSWORD = "ApplicationsPassword123"


def create_user(db_session: Session, *, email: str, role: UserRole) -> None:
    db_session.add(
        User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            is_active=True,
        )
    )
    db_session.commit()


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def opportunity_payload(**overrides: object) -> dict:
    payload = {
        "name": "Application Tracker Scholarship",
        "provider_name": "Official Tracker Provider",
        "country": "Malaysia",
        "degree_level": "masters",
        "field_eligibility": "Computer Science and Artificial Intelligence",
        "nationality_eligibility": "Pakistani and international applicants",
        "application_deadline": "2027-05-30T23:59:59Z",
        "intake_year": 2027,
        "funding_type": "full",
        "funding_policy": (
            "The official award policy confirms tuition, living stipend, accommodation, travel, "
            "insurance, and mandatory fee coverage for the full study period."
        ),
        "tuition_coverage_status": "confirmed",
        "stipend_coverage_status": "confirmed",
        "accommodation_coverage_status": "confirmed",
        "travel_coverage_status": "confirmed",
        "insurance_coverage_status": "confirmed",
        "fees_coverage_status": "confirmed",
        "tuition_coverage": "Full tuition coverage stated by the official source",
        "monthly_stipend_amount": "1200.00",
        "monthly_stipend_currency": "MYR",
        "required_documents": ["Transcript", "Passport"],
        "status": "draft",
        "data_confidence": "medium",
        "source": {
            "url": "https://example.edu/tracker-scholarship",
            "source_type": "official",
            "title": "Official tracker scholarship page",
            "relevant_excerpt": (
                "Official source lists application deadline, required documents, "
                "eligibility criteria, and funding package."
            ),
            "verification_status": "needs_review",
        },
    }
    payload.update(overrides)
    return payload


def create_verified_opportunity(
    client: TestClient, admin_headers: dict[str, str], **overrides: object
) -> dict:
    created = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(**overrides),
        headers=admin_headers,
    )
    assert created.status_code == 201
    return publish_opportunity(client, admin_headers, created.json())


def test_student_can_save_verified_opportunity_and_track_documents(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-applications@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-applications@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-applications@example.com"))
    student_headers = headers(login(client, "student-applications@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)

    response = client.post(
        "/api/v1/saved-opportunities",
        json={
            "opportunity_id": opportunity["id"],
            "personal_notes": "Strong fit; confirm IELTS waiver.",
            "personal_deadline": "2027-05-15T23:59:59Z",
            "document_checklist": [
                {"name": "Transcript", "is_complete": True},
                {"name": "Passport", "is_complete": False, "notes": "Renew before applying"},
            ],
            "recommendation_letters": [{"name": "Academic referee", "is_complete": False}],
            "test_requirements": [{"name": "IELTS", "is_complete": False}],
        },
        headers=student_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "interested"
    assert body["opportunity"]["id"] == opportunity["id"]
    assert body["opportunity"]["official_source_url"] == "https://example.edu/tracker-scholarship"
    assert body["document_checklist"][0]["name"] == "Transcript"
    assert body["document_checklist"][0]["is_complete"] is True


def test_student_can_update_application_status_and_filter_tracker(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-status@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-status@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-status@example.com"))
    student_headers = headers(login(client, "student-status@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    saved = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": opportunity["id"]},
        headers=student_headers,
    )
    assert saved.status_code == 201

    updated = client.patch(
        f"/api/v1/saved-opportunities/{saved.json()['id']}",
        json={
            "status": "submitted",
            "submitted_at": "2027-05-10T10:00:00Z",
            "outcome_notes": "Submitted before deadline.",
            "document_checklist": [{"name": "Transcript", "is_complete": True}],
        },
        headers=student_headers,
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "submitted"
    assert updated.json()["submitted_at"].startswith("2027-05-10T10:00:00")
    listing = client.get(
        "/api/v1/saved-opportunities?status_filter=submitted",
        headers=student_headers,
    )
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [saved.json()["id"]]


def test_student_cannot_save_same_opportunity_twice(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-duplicate-save@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-duplicate-save@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-duplicate-save@example.com"))
    student_headers = headers(login(client, "student-duplicate-save@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)

    first = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": opportunity["id"]},
        headers=student_headers,
    )
    second = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": opportunity["id"]},
        headers=student_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "opportunity_already_saved"


def test_tracker_rejects_submission_date_before_submitted_status(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-invalid-state@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-invalid-state@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-invalid-state@example.com"))
    student_headers = headers(login(client, "student-invalid-state@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    saved = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": opportunity["id"]},
        headers=student_headers,
    )
    assert saved.status_code == 201

    response = client.patch(
        f"/api/v1/saved-opportunities/{saved.json()['id']}",
        json={"submitted_at": "2027-05-10T10:00:00Z"},
        headers=student_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_application_state"


def test_student_cannot_save_unverified_opportunity(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-unverified-save@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-unverified-save@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-unverified-save@example.com"))
    student_headers = headers(login(client, "student-unverified-save@example.com"))
    created = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(),
        headers=admin_headers,
    )
    assert created.status_code == 201

    response = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": created.json()["id"]},
        headers=student_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "opportunity_not_available"


def test_saved_opportunities_are_isolated_between_students(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-isolation@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-one-save@example.com", role=UserRole.STUDENT)
    create_user(db_session, email="student-two-save@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-isolation@example.com"))
    student_one_headers = headers(login(client, "student-one-save@example.com"))
    student_two_headers = headers(login(client, "student-two-save@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    saved = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": opportunity["id"]},
        headers=student_one_headers,
    )
    assert saved.status_code == 201

    other_get = client.get(
        f"/api/v1/saved-opportunities/{saved.json()['id']}",
        headers=student_two_headers,
    )
    other_list = client.get("/api/v1/saved-opportunities", headers=student_two_headers)

    assert other_get.status_code == 404
    assert other_list.status_code == 200
    assert other_list.json() == []


def test_student_can_unsave_opportunity(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="admin-delete-save@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-delete-save@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-delete-save@example.com"))
    student_headers = headers(login(client, "student-delete-save@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    saved = client.post(
        "/api/v1/saved-opportunities",
        json={"opportunity_id": opportunity["id"]},
        headers=student_headers,
    )
    assert saved.status_code == 201

    deleted = client.delete(
        f"/api/v1/saved-opportunities/{saved.json()['id']}",
        headers=student_headers,
    )
    listing = client.get("/api/v1/saved-opportunities", headers=student_headers)

    assert deleted.status_code == 204
    assert listing.status_code == 200
    assert listing.json() == []
