import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.cli.create_admin import upsert_admin
from app.core.security import hash_password
from app.modules.auth.models import User, UserRole

ADMIN_EMAIL = "admin@example.com"
STUDENT_EMAIL = "student-catalog@example.com"
PASSWORD = "AdminPassword123"


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


def login(client: TestClient, *, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def admin_headers(client: TestClient, db_session: Session) -> dict[str, str]:
    create_user(db_session, email=ADMIN_EMAIL, role=UserRole.ADMIN)
    token = login(client, email=ADMIN_EMAIL)
    return {"Authorization": f"Bearer {token}"}


def opportunity_payload(**overrides: object) -> dict:
    payload = {
        "name": "Malaysia International Scholarship",
        "provider_name": "Ministry of Higher Education Malaysia",
        "provider_website_url": "https://www.mohe.gov.my/",
        "university_name": "Universiti Teknologi Malaysia",
        "university_website_url": "https://www.utm.my/",
        "country": "Malaysia",
        "degree_level": "masters",
        "field_eligibility": "Computer Science and related disciplines",
        "nationality_eligibility": "International applicants",
        "application_opening_date": "2026-03-01T00:00:00Z",
        "application_deadline": "2026-05-30T23:59:59Z",
        "intake_year": 2026,
        "funding_type": "full",
        "tuition_coverage": "Tuition fees covered according to the official call",
        "monthly_stipend_amount": "1500.00",
        "monthly_stipend_currency": "myr",
        "accommodation_coverage": "Not clearly stated",
        "travel_allowance": "Return airfare mentioned in the official benefits section",
        "health_insurance": "Health insurance mentioned",
        "application_fee_info": "No application fee stated in source excerpt",
        "english_language_requirement": "English language proof may be required",
        "standardized_test_requirement": "GRE not stated",
        "minimum_academic_requirement": "Strong academic record required",
        "required_documents": ["Transcript", "Passport", "Recommendation letters"],
        "application_method": "Apply through official online portal",
        "application_url": "https://biasiswa.mohe.gov.my/",
        "status": "draft",
        "data_confidence": "medium",
        "eligibility_warnings": ["Verify exact English requirement before applying"],
        "source": {
            "url": "https://biasiswa.mohe.gov.my/INTER/index.php",
            "source_type": "official",
            "title": "Malaysia International Scholarship official application page",
            "relevant_excerpt": (
                "Official scholarship page states the application portal, deadline, "
                "general eligibility, funding benefits, and required application route."
            ),
            "verification_status": "needs_review",
        },
    }
    payload.update(overrides)
    return payload


def create_opportunity(client: TestClient, headers: dict[str, str], **overrides: object) -> dict:
    response = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_student_cannot_create_opportunity(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email=STUDENT_EMAIL, role=UserRole.STUDENT)
    student_token = login(client, email=STUDENT_EMAIL)

    response = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(),
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_bootstrap_promotes_existing_user(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email=STUDENT_EMAIL, role=UserRole.STUDENT)

    user = upsert_admin(db_session, email=STUDENT_EMAIL.upper(), password="NewPassword123")
    token_response = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT_EMAIL, "password": "NewPassword123"},
    )

    assert user.role is UserRole.ADMIN
    assert token_response.status_code == 200
    assert token_response.json()["user"]["role"] == "admin"


def test_unverified_opportunity_is_hidden_until_admin_verifies_source(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    created = create_opportunity(client, headers)

    hidden = client.get("/api/v1/opportunities")
    assert hidden.status_code == 200
    assert hidden.json() == []

    verified = client.patch(
        f"/api/v1/admin/opportunities/{created['id']}/verification",
        json={
            "verification_status": "officially_verified",
            "notes": "Manual official source check",
        },
        headers=headers,
    )
    assert verified.status_code == 200
    body = verified.json()
    assert body["status"] == "active"
    assert body["verification_status"] == "officially_verified"
    assert body["last_verified_at"] is not None

    public = client.get("/api/v1/opportunities")
    assert public.status_code == 200
    assert public.json()[0]["official_source_url"] == created["official_source_url"]


def test_public_search_filters_verified_opportunities(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    malaysia = create_opportunity(client, headers)
    turkey = create_opportunity(
        client,
        headers,
        name="Turkiye Scholarships",
        provider_name="Presidency for Turks Abroad and Related Communities",
        country="Turkiye",
        degree_level="phd",
        intake_year=2027,
        source={
            **opportunity_payload()["source"],
            "url": "https://www.turkiyeburslari.gov.tr/",
            "title": "Turkiye Scholarships official page",
        },
    )
    for opportunity_id in [malaysia["id"], turkey["id"]]:
        response = client.patch(
            f"/api/v1/admin/opportunities/{opportunity_id}/verification",
            json={"verification_status": "officially_verified"},
            headers=headers,
        )
        assert response.status_code == 200

    filtered = client.get("/api/v1/opportunities?country=Malaysia&degree_level=masters")
    assert filtered.status_code == 200
    assert [item["name"] for item in filtered.json()] == ["Malaysia International Scholarship"]


def test_duplicate_opportunity_is_rejected(client: TestClient, db_session: Session) -> None:
    headers = admin_headers(client, db_session)
    create_opportunity(client, headers)

    duplicate = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(),
        headers=headers,
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_opportunity"


def test_admin_imports_opportunities_as_drafts_requiring_review(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={
            "source_format": "json",
            "rows": [
                opportunity_payload(
                    name="Imported Review Scholarship",
                    status="active",
                    source={
                        **opportunity_payload()["source"],
                        "url": "https://example.edu/imported-review",
                        "verification_status": "officially_verified",
                    },
                )
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 1
    assert body["results"][0]["status"] == "imported"
    assert any("forced to draft" in warning for warning in body["results"][0]["warnings"])
    assert any("forced to needs_review" in warning for warning in body["results"][0]["warnings"])

    admin_list = client.get("/api/v1/admin/opportunities", headers=headers)
    assert admin_list.status_code == 200
    imported = admin_list.json()[0]
    assert imported["name"] == "Imported Review Scholarship"
    assert imported["status"] == "draft"
    assert imported["verification_status"] == "needs_review"

    public = client.get("/api/v1/opportunities")
    assert public.status_code == 200
    assert public.json() == []


def test_import_dry_run_validates_without_creating_records(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={
            "source_format": "json",
            "dry_run": True,
            "rows": [
                opportunity_payload(
                    name="Dry Run Scholarship",
                    source={
                        **opportunity_payload()["source"],
                        "url": "https://example.edu/dry-run",
                    },
                )
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["imported_count"] == 0
    assert response.json()["results"][0]["status"] == "dry_run_ready"
    admin_list = client.get("/api/v1/admin/opportunities", headers=headers)
    assert admin_list.status_code == 200
    assert admin_list.json() == []


def test_import_reports_existing_duplicate_without_failing_whole_batch(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    create_opportunity(client, headers)

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={
            "source_format": "json",
            "rows": [
                opportunity_payload(),
                opportunity_payload(
                    name="Fresh Import Scholarship",
                    source={
                        **opportunity_payload()["source"],
                        "url": "https://example.edu/fresh-import",
                    },
                ),
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 2
    assert body["duplicate_count"] == 1
    assert body["imported_count"] == 1
    assert body["results"][0]["status"] == "skipped_duplicate"
    assert body["results"][1]["status"] == "imported"


def test_import_reports_validation_errors_per_row(client: TestClient, db_session: Session) -> None:
    headers = admin_headers(client, db_session)
    invalid = opportunity_payload(
        name="Invalid Import Scholarship",
        tuition_coverage=None,
        monthly_stipend_amount=None,
        accommodation_coverage=None,
        travel_allowance=None,
        health_insurance=None,
    )

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={"source_format": "json", "rows": [invalid]},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["failed_count"] == 1
    assert body["results"][0]["status"] == "failed_validation"
    assert any("Full funding requires" in error for error in body["results"][0]["errors"])


def test_import_detects_duplicate_rows_inside_same_batch(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    duplicate_row = opportunity_payload(
        name="Same File Duplicate Scholarship",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/same-file-duplicate",
        },
    )

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={"source_format": "json", "rows": [duplicate_row, duplicate_row]},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 1
    assert body["duplicate_count"] == 1
    assert body["results"][1]["status"] == "skipped_duplicate"
    assert "same import batch" in body["results"][1]["errors"][0]


def test_full_funding_requires_structured_coverage_evidence(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    invalid_payload = opportunity_payload(
        tuition_coverage=None,
        monthly_stipend_amount=None,
        accommodation_coverage=None,
        travel_allowance=None,
        health_insurance=None,
    )

    response = client.post("/api/v1/admin/opportunities", json=invalid_payload, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_deadline_cannot_be_before_opening_date(client: TestClient, db_session: Session) -> None:
    headers = admin_headers(client, db_session)

    response = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(
            application_opening_date=datetime(2026, 6, 1, tzinfo=UTC).isoformat(),
            application_deadline=datetime(2026, 5, 1, tzinfo=UTC).isoformat(),
        ),
        headers=headers,
    )

    assert response.status_code == 422
