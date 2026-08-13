import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli.create_admin import upsert_admin
from app.core.security import hash_password
from app.modules.auth.models import AuditLog, User, UserRole
from app.modules.opportunities.models import SourceExcerpt, VerificationRecord

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


def response_items(response) -> list[dict]:
    return response.json()["items"]


def response_pagination(response) -> dict:
    return response.json()["pagination"]


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
    assert response_items(hidden) == []

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
    assert response_items(public)[0]["official_source_url"] == created["official_source_url"]
    assert response_pagination(public)["total"] == 1


def test_open_now_excludes_closed_future_and_unknown_deadline_records(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    now = datetime.now(UTC)
    records = [
        create_opportunity(
            client,
            headers,
            name="Open-now scholarship",
            application_opening_date=(now - timedelta(days=1)).isoformat(),
            application_deadline=(now + timedelta(days=1)).isoformat(),
        ),
        create_opportunity(
            client,
            headers,
            name="Closed scholarship",
            application_deadline=(now - timedelta(seconds=1)).isoformat(),
        ),
        create_opportunity(
            client,
            headers,
            name="Future scholarship",
            application_opening_date=(now + timedelta(days=1)).isoformat(),
            application_deadline=(now + timedelta(days=2)).isoformat(),
        ),
        create_opportunity(
            client,
            headers,
            name="Unknown-deadline scholarship",
            application_opening_date=None,
            application_deadline=None,
        ),
    ]
    for record in records:
        assert (
            client.patch(
                f"/api/v1/admin/opportunities/{record['id']}/verification",
                json={"verification_status": "officially_verified"},
                headers=headers,
            ).status_code
            == 200
        )

    response = client.get("/api/v1/opportunities?open_now=true")

    assert response.status_code == 200
    assert [item["name"] for item in response_items(response)] == ["Open-now scholarship"]
    assert response_items(response)[0]["application_window_state"] == "open"

    upcoming = client.get("/api/v1/opportunities?application_window_state=upcoming")

    assert upcoming.status_code == 200
    assert [item["name"] for item in response_items(upcoming)] == ["Future scholarship"]
    assert response_items(upcoming)[0]["application_window_state"] == "upcoming"

    conflicting_filters = client.get(
        "/api/v1/opportunities?open_now=true&application_window_state=upcoming"
    )

    assert conflicting_filters.status_code == 422


def test_public_window_filters_paginate_in_the_database(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    now = datetime.now(UTC)
    for name in ["A Open Scholarship", "B Open Scholarship", "C Open Scholarship"]:
        created = create_opportunity(
            client,
            headers,
            name=name,
            application_opening_date=(now - timedelta(days=1)).isoformat(),
            application_deadline=(now + timedelta(days=30)).isoformat(),
        )
        assert (
            client.patch(
                f"/api/v1/admin/opportunities/{created['id']}/verification",
                json={"verification_status": "officially_verified"},
                headers=headers,
            ).status_code
            == 200
        )

    response = client.get("/api/v1/opportunities?open_now=true&limit=1&offset=1")

    assert response.status_code == 200
    assert [item["name"] for item in response_items(response)] == ["B Open Scholarship"]
    pagination = response_pagination(response)
    assert pagination["total"] == 3
    assert pagination["limit"] == 1
    assert pagination["offset"] == 1
    assert pagination["count"] == 1
    assert pagination["has_previous"] is True
    assert pagination["has_next"] is True


def test_public_catalogue_prioritizes_open_then_upcoming_then_other_verified_records(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    now = datetime.now(UTC)
    records = [
        create_opportunity(
            client,
            headers,
            name="Closed catalogue scholarship",
            application_deadline=(now - timedelta(days=1)).isoformat(),
        ),
        create_opportunity(
            client,
            headers,
            name="Deadline-variable catalogue scholarship",
            application_opening_date=None,
            application_deadline=None,
        ),
        create_opportunity(
            client,
            headers,
            name="Upcoming catalogue scholarship",
            application_opening_date=(now + timedelta(days=3)).isoformat(),
            application_deadline=(now + timedelta(days=10)).isoformat(),
        ),
        create_opportunity(
            client,
            headers,
            name="Open catalogue scholarship",
            application_opening_date=(now - timedelta(days=1)).isoformat(),
            application_deadline=(now + timedelta(days=2)).isoformat(),
        ),
    ]
    for record in records:
        assert (
            client.patch(
                f"/api/v1/admin/opportunities/{record['id']}/verification",
                json={"verification_status": "officially_verified"},
                headers=headers,
            ).status_code
            == 200
        )

    response = client.get("/api/v1/opportunities")

    assert response.status_code == 200
    assert [item["name"] for item in response_items(response)] == [
        "Open catalogue scholarship",
        "Upcoming catalogue scholarship",
        "Deadline-variable catalogue scholarship",
        "Closed catalogue scholarship",
    ]


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
    assert [item["name"] for item in response_items(filtered)] == [
        "Malaysia International Scholarship"
    ]


def test_public_search_returns_pagination_metadata(client: TestClient, db_session: Session) -> None:
    headers = admin_headers(client, db_session)
    first = create_opportunity(
        client,
        headers,
        name="A First Scholarship",
        provider_name="First Provider",
        application_deadline="2027-01-01T00:00:00Z",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/a-first",
            "title": "A first source",
        },
    )
    second = create_opportunity(
        client,
        headers,
        name="B Second Scholarship",
        provider_name="Second Provider",
        application_deadline="2027-02-01T00:00:00Z",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/b-second",
            "title": "B second source",
        },
    )
    third = create_opportunity(
        client,
        headers,
        name="C Third Scholarship",
        provider_name="Third Provider",
        application_deadline="2027-03-01T00:00:00Z",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/c-third",
            "title": "C third source",
        },
    )
    for opportunity_id in [first["id"], second["id"], third["id"]]:
        response = client.patch(
            f"/api/v1/admin/opportunities/{opportunity_id}/verification",
            json={"verification_status": "officially_verified"},
            headers=headers,
        )
        assert response.status_code == 200

    page = client.get("/api/v1/opportunities?limit=2&offset=1")

    assert page.status_code == 200
    assert [item["name"] for item in response_items(page)] == [
        "B Second Scholarship",
        "C Third Scholarship",
    ]
    assert response_pagination(page) == {
        "total": 3,
        "limit": 2,
        "offset": 1,
        "count": 2,
        "has_next": False,
        "has_previous": True,
    }


def test_public_search_supports_advanced_structured_filters(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    ai = create_opportunity(
        client,
        headers,
        name="AI Access Scholarship",
        provider_name="AI Access Foundation",
        country="Canada",
        degree_level="masters",
        field_eligibility="Artificial Intelligence and Computer Science",
        nationality_eligibility="Pakistani and international applicants",
        application_deadline="2027-04-30T23:59:59Z",
        intake_year=2027,
        funding_type="full",
        tuition_coverage="Full tuition waiver",
        accommodation_coverage="Monthly living support for rent",
        application_fee_info="No application fee is charged",
        english_language_requirement="IELTS accepted; TOEFL accepted",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/ai-access",
            "title": "AI Access official page",
        },
    )
    history = create_opportunity(
        client,
        headers,
        name="History Partial Award",
        provider_name="Humanities Foundation",
        country="Germany",
        degree_level="phd",
        field_eligibility="History and cultural studies",
        nationality_eligibility="European applicants",
        application_deadline="2027-01-15T23:59:59Z",
        intake_year=2027,
        funding_type="partial",
        tuition_coverage="Partial tuition support",
        accommodation_coverage=None,
        application_fee_info="Application fee may apply",
        english_language_requirement="German proof required",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/history-award",
            "title": "History award official page",
        },
    )
    for opportunity_id in [ai["id"], history["id"]]:
        response = client.patch(
            f"/api/v1/admin/opportunities/{opportunity_id}/verification",
            json={"verification_status": "officially_verified"},
            headers=headers,
        )
        assert response.status_code == 200

    filtered = client.get(
        "/api/v1/opportunities"
        "?field=Artificial"
        "&nationality=Pakistani"
        "&intake_year=2027"
        "&deadline_after=2027-03-01T00:00:00Z"
        "&funding_coverage=rent"
        "&application_fee=No application fee"
        "&english_requirement=IELTS"
        "&verified_after=2026-01-01T00:00:00Z"
    )

    assert filtered.status_code == 200
    assert [item["name"] for item in response_items(filtered)] == ["AI Access Scholarship"]
    assert response_pagination(filtered)["total"] == 1


def test_admin_opportunity_list_supports_review_and_status_filters(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    active = create_opportunity(
        client,
        headers,
        name="Verified Admin Search Scholarship",
        provider_name="Verified Provider",
        country="Malaysia",
        degree_level="masters",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/verified-admin-search",
            "title": "Verified admin search source",
        },
    )
    draft = create_opportunity(
        client,
        headers,
        name="Draft Review Scholarship",
        provider_name="Review Provider",
        country="Canada",
        degree_level="phd",
        field_eligibility="Robotics and AI",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/draft-review",
            "title": "Draft review source",
        },
    )
    verified = client.patch(
        f"/api/v1/admin/opportunities/{active['id']}/verification",
        json={"verification_status": "officially_verified"},
        headers=headers,
    )
    assert verified.status_code == 200

    active_filter = client.get("/api/v1/admin/opportunities?status=active", headers=headers)
    review_filter = client.get("/api/v1/admin/opportunities?needs_review=true", headers=headers)
    provider_filter = client.get(
        "/api/v1/admin/opportunities?provider_query=Review", headers=headers
    )
    verification_filter = client.get(
        "/api/v1/admin/opportunities?verification_status=needs_review",
        headers=headers,
    )
    search_filter = client.get("/api/v1/admin/opportunities?search_query=Robotics", headers=headers)

    assert active_filter.status_code == 200
    assert [item["id"] for item in response_items(active_filter)] == [active["id"]]
    assert response_pagination(active_filter)["total"] == 1
    assert review_filter.status_code == 200
    assert [item["id"] for item in response_items(review_filter)] == [draft["id"]]
    assert provider_filter.status_code == 200
    assert [item["id"] for item in response_items(provider_filter)] == [draft["id"]]
    assert verification_filter.status_code == 200
    assert [item["id"] for item in response_items(verification_filter)] == [draft["id"]]
    assert search_filter.status_code == 200
    assert [item["id"] for item in response_items(search_filter)] == [draft["id"]]


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
    imported = response_items(admin_list)[0]
    assert imported["name"] == "Imported Review Scholarship"
    assert imported["status"] == "draft"
    assert imported["verification_status"] == "needs_review"

    public = client.get("/api/v1/opportunities")
    assert public.status_code == 200
    assert response_items(public) == []


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
    assert response_items(admin_list) == []


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


def test_csv_import_parses_rows_as_drafts_requiring_review(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    csv_content = (
        "name,provider_name,country,degree_level,funding_type,tuition_coverage,"
        "application_deadline,required_documents,english_language_requirement,"
        "minimum_academic_requirement,status,source_url,source_title,"
        "source_relevant_excerpt,source_verification_status\n"
        "CSV Review Scholarship,CSV Provider,Malaysia,masters,full,"
        "Full tuition stated by the official source,2027-05-30T23:59:59Z,"
        "Transcript;Passport,English proof may be required,"
        "Strong academic record required,active,https://example.edu/csv-review,"
        "CSV official source,"
        "Official source lists scholarship deadline funding eligibility and application route.,"
        "officially_verified\n"
    )

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={"source_format": "csv", "csv_content": csv_content},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_format"] == "csv"
    assert body["total_rows"] == 1
    assert body["imported_count"] == 1
    assert body["results"][0]["row_number"] == 2
    assert any("forced to draft" in warning for warning in body["results"][0]["warnings"])
    assert any("forced to needs_review" in warning for warning in body["results"][0]["warnings"])

    admin_list = client.get("/api/v1/admin/opportunities", headers=headers)
    imported = response_items(admin_list)[0]
    assert imported["name"] == "CSV Review Scholarship"
    assert imported["status"] == "draft"
    assert imported["verification_status"] == "needs_review"
    assert imported["required_documents"] == ["Transcript", "Passport"]
    assert response_items(client.get("/api/v1/opportunities")) == []


def test_csv_import_dry_run_reports_formula_cell_neutralization(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    csv_content = (
        "name,provider_name,country,degree_level,funding_type,tuition_coverage,"
        "source_url,source_title,source_relevant_excerpt\n"
        "Formula CSV Scholarship,Formula Provider,Malaysia,masters,full,"
        "Full tuition stated by the official source,https://example.edu/formula,"
        "=Official source,"
        "Official source lists scholarship deadline funding eligibility and application route.\n"
    )

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={"source_format": "csv", "dry_run": True, "csv_content": csv_content},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported_count"] == 0
    assert body["results"][0]["status"] == "dry_run_ready"
    assert any(
        "Formula-like value was neutralized" in warning
        for warning in body["results"][0]["warnings"]
    )
    assert response_items(client.get("/api/v1/admin/opportunities", headers=headers)) == []


def test_csv_import_reports_row_level_validation_errors(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    csv_content = (
        "name,provider_name,country,degree_level,funding_type,source_title,"
        "source_relevant_excerpt\n"
        "Broken CSV Scholarship,Broken Provider,Malaysia,masters,unknown,"
        "Broken official source,"
        "Official source excerpt is present but URL is intentionally missing.\n"
    )

    response = client.post(
        "/api/v1/admin/opportunities/import",
        json={"source_format": "csv", "csv_content": csv_content},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["failed_count"] == 1
    assert body["results"][0]["row_number"] == 2
    assert body["results"][0]["status"] == "failed_validation"
    assert any("source.url" in error for error in body["results"][0]["errors"])


def test_admin_data_quality_dashboard_reports_review_reasons(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    created = create_opportunity(
        client,
        headers,
        name="Quality Review Scholarship",
        application_deadline=None,
        funding_type="unknown",
        required_documents=[],
        english_language_requirement=None,
        minimum_academic_requirement=None,
        data_confidence="low",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/quality-review",
        },
    )

    issues = client.get("/api/v1/admin/data-quality-issues", headers=headers)
    queue = client.get("/api/v1/admin/review-queue", headers=headers)

    assert issues.status_code == 200
    issue_codes = {item["code"] for item in response_items(issues)}
    assert {
        "source_requires_review",
        "source_never_verified",
        "deadline_missing",
        "funding_type_unknown",
        "required_documents_missing",
        "english_requirement_missing",
        "academic_requirement_missing",
        "low_data_confidence",
    }.issubset(issue_codes)
    assert issues.json()["pagination"]["total"] >= 8

    assert queue.status_code == 200
    assert response_items(queue)[0]["opportunity"]["id"] == created["id"]
    assert any(reason["severity"] == "high" for reason in response_items(queue)[0]["reasons"])


def test_source_hash_change_blocks_public_visibility_until_reverified(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    created = create_opportunity(
        client,
        headers,
        name="Changed Source Scholarship",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/changed-source",
            "content_hash": "a" * 64,
        },
    )
    verified = client.patch(
        f"/api/v1/admin/opportunities/{created['id']}/verification",
        json={"verification_status": "officially_verified"},
        headers=headers,
    )
    assert verified.status_code == 200
    assert response_items(client.get("/api/v1/opportunities"))[0]["id"] == created["id"]

    source_id = created["sources"][0]["id"]
    check = client.post(
        f"/api/v1/admin/sources/{source_id}/checks",
        json={
            "content_hash": "b" * 64,
            "change_summary": "Official page content changed during monitoring.",
            "excerpt": {
                "section_label": "Eligibility",
                "locator": "#eligibility",
                "text": (
                    "Official source now shows changed scholarship eligibility "
                    "and deadline language for curator review."
                ),
            },
        },
        headers=headers,
    )

    assert check.status_code == 200
    body = check.json()
    assert body["changed"] is True
    assert body["previous_hash"] == "a" * 64
    assert body["current_hash"] == "b" * 64
    assert body["public_visibility_blocked"] is True
    assert body["source"]["verification_status"] == "needs_review"
    assert body["excerpt"]["section_label"] == "Eligibility"

    public = client.get("/api/v1/opportunities")
    assert public.status_code == 200
    assert response_items(public) == []

    records = db_session.scalars(select(VerificationRecord)).all()
    assert any(record.metadata_json.get("changed") is True for record in records)
    excerpts = db_session.scalars(select(SourceExcerpt)).all()
    assert len(excerpts) == 1
    assert excerpts[0].content_hash == "b" * 64


def test_admin_review_action_publish_and_flag_conflict_control_public_visibility(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    created = create_opportunity(
        client,
        headers,
        name="Reviewer Action Scholarship",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/reviewer-action",
        },
    )
    source_id = created["sources"][0]["id"]

    published = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={
            "action": "publish",
            "source_id": source_id,
            "notes": "Official source checked and ready for public search.",
        },
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["status"] == "active"
    assert published.json()["verification_status"] == "officially_verified"
    assert response_items(client.get("/api/v1/opportunities"))[0]["id"] == created["id"]

    conflict = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={
            "action": "flag_conflict",
            "source_id": source_id,
            "notes": "Deadline differs between official pages.",
        },
        headers=headers,
    )

    assert conflict.status_code == 200
    assert conflict.json()["status"] == "draft"
    assert conflict.json()["verification_status"] == "conflicting_information"
    assert response_items(client.get("/api/v1/opportunities")) == []

    records = db_session.scalars(select(VerificationRecord)).all()
    assert [record.metadata_json.get("action") for record in records] == [
        "publish",
        "flag_conflict",
    ]
    audit_logs = db_session.scalars(select(AuditLog)).all()
    assert any(log.action == "opportunity_review_action" for log in audit_logs)


def test_admin_review_action_resolves_conflict_and_request_recheck(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    created = create_opportunity(
        client,
        headers,
        name="Resolve Conflict Scholarship",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/resolve-conflict",
        },
    )
    source_id = created["sources"][0]["id"]
    assert (
        client.post(
            f"/api/v1/admin/opportunities/{created['id']}/review-actions",
            json={
                "action": "flag_conflict",
                "source_id": source_id,
                "notes": "Funding details conflict with another source.",
            },
            headers=headers,
        ).status_code
        == 200
    )

    resolved = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={
            "action": "resolve_conflict",
            "source_id": source_id,
            "notes": "Official source now matches the structured record.",
        },
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "active"
    assert resolved.json()["verification_status"] == "officially_verified"

    recheck = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={
            "action": "request_recheck",
            "source_id": source_id,
            "notes": "Source monitor found a changed hash.",
        },
        headers=headers,
    )
    assert recheck.status_code == 200
    assert recheck.json()["status"] == "draft"
    assert recheck.json()["verification_status"] == "needs_review"
    assert response_items(client.get("/api/v1/opportunities")) == []


def test_admin_review_actions_expire_archive_and_require_notes(
    client: TestClient, db_session: Session
) -> None:
    headers = admin_headers(client, db_session)
    created = create_opportunity(
        client,
        headers,
        name="Expire Archive Scholarship",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/expire-archive",
        },
    )
    source_id = created["sources"][0]["id"]

    missing_notes = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={"action": "expire", "source_id": source_id},
        headers=headers,
    )
    assert missing_notes.status_code == 422
    assert missing_notes.json()["error"]["code"] == "review_notes_required"

    expired = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={
            "action": "expire",
            "source_id": source_id,
            "notes": "Official application cycle is closed.",
        },
        headers=headers,
    )
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert expired.json()["verification_status"] == "expired"

    archived = client.post(
        f"/api/v1/admin/opportunities/{created['id']}/review-actions",
        json={
            "action": "archive",
            "source_id": source_id,
            "notes": "Record is no longer maintained.",
        },
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["verification_status"] == "archived"


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
