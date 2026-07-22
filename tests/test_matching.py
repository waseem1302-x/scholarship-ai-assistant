import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import User, UserRole

PASSWORD = "MatchingPassword123"


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


def profile_payload(**overrides: object) -> dict:
    payload = {
        "nationality": "Pakistani",
        "country_of_residence": "Malaysia",
        "current_education_level": "bachelors",
        "target_degree_level": "masters",
        "intended_field": "Artificial Intelligence",
        "academic_discipline": "Computer Science",
        "cgpa": "3.70",
        "grading_scale": "4.00",
        "english_test_status": "taken",
        "ielts_score": "7.0",
        "gre_status": "planned",
        "financial_need": "Needs tuition and living support",
        "preferred_destination_countries": ["Malaysia", "Canada"],
        "preferred_study_mode": "on_campus",
        "target_intake": "Fall 2027",
    }
    payload.update(overrides)
    return payload


def opportunity_payload(**overrides: object) -> dict:
    payload = {
        "name": "Malaysia AI Graduate Scholarship",
        "provider_name": "Verified Scholarship Provider",
        "country": "Malaysia",
        "degree_level": "masters",
        "field_eligibility": "Artificial Intelligence, Computer Science, and related disciplines",
        "nationality_eligibility": "Pakistani and international applicants",
        "application_deadline": "2027-05-30T23:59:59Z",
        "intake_year": 2027,
        "funding_type": "full",
        "tuition_coverage": "Full tuition coverage stated by the official source",
        "monthly_stipend_amount": "1500.00",
        "monthly_stipend_currency": "MYR",
        "english_language_requirement": "IELTS or TOEFL required unless waived",
        "minimum_academic_requirement": "Minimum CGPA 3.0 on a 4.0 scale",
        "required_documents": ["Transcript", "Passport"],
        "application_url": "https://example.edu/apply",
        "status": "draft",
        "data_confidence": "medium",
        "source": {
            "url": "https://example.edu/scholarships/ai",
            "source_type": "official",
            "title": "Official AI scholarship page",
            "relevant_excerpt": (
                "Official source lists deadline, eligible fields, nationality rules, "
                "English requirements, and funding coverage."
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
    verified = client.patch(
        f"/api/v1/admin/opportunities/{created.json()['id']}/verification",
        json={"verification_status": "officially_verified"},
        headers=admin_headers,
    )
    assert verified.status_code == 200
    return verified.json()


def test_matching_requires_profile(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="student-no-profile@example.com", role=UserRole.STUDENT)
    token = login(client, "student-no-profile@example.com")

    response = client.get("/api/v1/matches/me", headers=headers(token))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "profile_required"


def test_matching_ranks_verified_opportunities_and_explains_fit(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-match@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-match@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-match@example.com"))
    student_headers = headers(login(client, "student-match@example.com"))
    profile = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(),
        headers=student_headers,
    )
    assert profile.status_code == 200

    strong = create_verified_opportunity(client, admin_headers)
    weak = create_verified_opportunity(
        client,
        admin_headers,
        name="PhD History Scholarship",
        country="Germany",
        degree_level="phd",
        field_eligibility="History and cultural studies",
        nationality_eligibility="German citizens",
        funding_type="partial",
        tuition_coverage="Partial tuition support",
        monthly_stipend_amount=None,
        monthly_stipend_currency=None,
        english_language_requirement="German-language proof required",
        minimum_academic_requirement="Minimum CGPA 3.9 on a 4.0 scale",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/scholarships/history",
            "title": "Official history scholarship page",
        },
    )

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["opportunity"]["id"] for item in results] == [strong["id"], weak["id"]]
    assert results[0]["match_score"] > results[1]["match_score"]
    assert results[0]["score_label"] == "strong_match"
    assert "not a probability" in results[0]["disclaimer"]
    assert any("Target degree matches" in item for item in results[0]["explanation"]["satisfied"])
    assert any("target degree" in item.lower() for item in results[1]["explanation"]["missing"])


def test_matching_hides_unverified_opportunities(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="admin-unverified@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-unverified@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-unverified@example.com"))
    student_headers = headers(login(client, "student-unverified@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me", json=profile_payload(), headers=student_headers
        ).status_code
        == 200
    )
    unverified = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(name="Unverified Scholarship"),
        headers=admin_headers,
    )
    assert unverified.status_code == 201

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_matching_surfaces_uncertainty_for_missing_profile_fields(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-uncertain@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-uncertain@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-uncertain@example.com"))
    student_headers = headers(login(client, "student-uncertain@example.com"))
    create_verified_opportunity(client, admin_headers)
    profile = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(
            nationality=None,
            intended_field=None,
            academic_discipline=None,
            cgpa=None,
            grading_scale=None,
            preferred_destination_countries=[],
        ),
        headers=student_headers,
    )
    assert profile.status_code == 200

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    uncertain = response.json()["results"][0]["explanation"]["uncertain"]
    assert any("nationality" in item.lower() for item in uncertain)
    assert any("field" in item.lower() for item in uncertain)
    assert any("cgpa" in item.lower() for item in uncertain)
