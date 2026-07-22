import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import User, UserRole

PASSWORD = "ProfilePassword123"


def create_student(db_session: Session, email: str) -> None:
    db_session.add(
        User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(PASSWORD),
            role=UserRole.STUDENT,
            is_active=True,
        )
    )
    db_session.commit()


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def profile_payload(**overrides: object) -> dict:
    payload = {
        "nationality": "Pakistani",
        "country_of_residence": "Malaysia",
        "current_education_level": "bachelors",
        "target_degree_level": "masters",
        "intended_field": "Artificial Intelligence",
        "academic_discipline": "Computer Science",
        "cgpa": "3.72",
        "grading_scale": "4.00",
        "english_test_status": "taken",
        "ielts_score": "7.5",
        "gre_status": "planned",
        "work_experience_months": 6,
        "research_experience": "Final-year machine learning project",
        "publications": [],
        "leadership_experience": "Scholarship community volunteer",
        "financial_need": "Needs tuition and living support",
        "preferred_destination_countries": ["Malaysia", "Canada", "Germany"],
        "preferred_study_mode": "on_campus",
        "target_intake": "Fall 2027",
        "application_constraints": "Needs fully funded options",
        "additional_eligibility_information": "Open to research assistantships",
    }
    payload.update(overrides)
    return payload


def test_get_missing_profile_returns_204(client: TestClient, db_session: Session) -> None:
    email = "missing-profile@example.com"
    create_student(db_session, email)
    token = login(client, email)

    response = client.get("/api/v1/profiles/me", headers=auth_headers(token))

    assert response.status_code == 204
    assert response.content == b""


def test_student_can_create_and_update_incomplete_profile(
    client: TestClient, db_session: Session
) -> None:
    email = "profile@example.com"
    create_student(db_session, email)
    token = login(client, email)

    created = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(
            ielts_score=None,
            english_test_status="planned",
            preferred_destination_countries=[],
        ),
        headers=auth_headers(token),
    )
    assert created.status_code == 200
    body = created.json()
    assert body["nationality"] == "Pakistani"
    assert body["profile_completeness"] < 100
    assert "preferred_destination_countries" in body["missing_recommended_fields"]

    updated = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(target_degree_level="phd", preferred_destination_countries=["Japan"]),
        headers=auth_headers(token),
    )
    assert updated.status_code == 200
    assert updated.json()["target_degree_level"] == "phd"
    assert updated.json()["preferred_destination_countries"] == ["Japan"]


def test_profiles_are_isolated_between_users(client: TestClient, db_session: Session) -> None:
    first_email = "first-profile@example.com"
    second_email = "second-profile@example.com"
    create_student(db_session, first_email)
    create_student(db_session, second_email)
    first_token = login(client, first_email)
    second_token = login(client, second_email)

    first_response = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(nationality="Pakistani"),
        headers=auth_headers(first_token),
    )
    second_response = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(nationality="Malaysian"),
        headers=auth_headers(second_token),
    )

    assert first_response.status_code == second_response.status_code == 200
    assert (
        client.get("/api/v1/profiles/me", headers=auth_headers(first_token)).json()["nationality"]
        == "Pakistani"
    )
    assert (
        client.get("/api/v1/profiles/me", headers=auth_headers(second_token)).json()["nationality"]
        == "Malaysian"
    )


def test_profile_validation_rejects_invalid_score_combinations(
    client: TestClient, db_session: Session
) -> None:
    email = "invalid-profile@example.com"
    create_student(db_session, email)
    token = login(client, email)

    missing_scale = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(grading_scale=None),
        headers=auth_headers(token),
    )
    english_not_taken = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(english_test_status="planned", ielts_score="7.0"),
        headers=auth_headers(token),
    )
    gre_not_taken = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(gre_status="planned", gre_score=320),
        headers=auth_headers(token),
    )

    assert missing_scale.status_code == 422
    assert english_not_taken.status_code == 422
    assert gre_not_taken.status_code == 422


def test_profile_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/profiles/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
