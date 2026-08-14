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
    assert body["nationality_code"] == "PK"
    assert body["country_of_residence_code"] == "MY"
    assert body["intended_field_taxonomy"] == "computer-science"
    assert body["version"] == 1
    assert body["completeness_context"] == "masters_profile"
    assert body["profile_completeness"] < 100
    assert "preferred_destination_countries" in body["missing_recommended_fields"]

    updated = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(
            target_degree_level="phd",
            preferred_destination_countries=["Japan"],
            expected_version=body["version"],
        ),
        headers=auth_headers(token),
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["target_degree_level"] == "phd"
    assert updated_body["preferred_destination_countries"] == ["Japan"]
    assert updated_body["version"] == 2
    assert updated_body["completeness_context"] == "phd_profile"


def test_profile_accepts_percentage_without_cgpa_scale(
    client: TestClient, db_session: Session
) -> None:
    email = "percentage-profile@example.com"
    create_student(db_session, email)
    token = login(client, email)

    response = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(cgpa=None, grading_scale=None, percentage="88.5"),
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["percentage"] == "88.50"
    assert "cgpa_or_percentage" not in body["missing_recommended_fields"]
    assert "grading_scale" not in body["missing_recommended_fields"]


def test_patch_preserves_omitted_profile_fields_and_uses_version(
    client: TestClient, db_session: Session
) -> None:
    email = "patch-profile@example.com"
    create_student(db_session, email)
    token = login(client, email)
    created = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(preferred_destination_countries=["Malaysia", "Canada"]),
        headers=auth_headers(token),
    )
    assert created.status_code == 200

    patched = client.patch(
        "/api/v1/profiles/me",
        json={
            "financial_need": "Updated need statement",
            "country_of_residence": "Canada",
            "intended_field": "History",
            "expected_version": 1,
        },
        headers=auth_headers(token),
    )

    assert patched.status_code == 200
    body = patched.json()
    assert body["financial_need"] == "Updated need statement"
    assert body["country_of_residence_code"] == "CA"
    assert body["intended_field_taxonomy"] == "humanities"
    assert body["preferred_destination_countries"] == ["Malaysia", "Canada"]
    assert body["version"] == 2

    cleared = client.patch(
        "/api/v1/profiles/me",
        json={"nationality": None, "preferred_destination_countries": [], "expected_version": 2},
        headers=auth_headers(token),
    )
    assert cleared.status_code == 200
    assert cleared.json()["nationality"] is None
    assert cleared.json()["nationality_code"] is None
    assert cleared.json()["preferred_destination_country_codes"] == []


def test_profile_update_requires_current_version(client: TestClient, db_session: Session) -> None:
    email = "versioned-profile@example.com"
    create_student(db_session, email)
    token = login(client, email)
    created = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(),
        headers=auth_headers(token),
    )
    assert created.status_code == 200

    missing = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(nationality="Malaysia"),
        headers=auth_headers(token),
    )
    stale = client.patch(
        "/api/v1/profiles/me",
        json={"nationality": "Malaysia", "expected_version": 999},
        headers=auth_headers(token),
    )

    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "profile_version_required"
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "profile_version_conflict"


def test_profile_validation_bounds_free_text_and_lists(
    client: TestClient, db_session: Session
) -> None:
    email = "bounded-profile@example.com"
    create_student(db_session, email)
    token = login(client, email)

    long_text = "x" * 2001
    too_many_items = [f"paper {index}" for index in range(21)]
    long_item = ["x" * 501]
    text_response = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(research_experience=long_text),
        headers=auth_headers(token),
    )
    list_response = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(publications=too_many_items),
        headers=auth_headers(token),
    )
    item_response = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(preferred_destination_countries=long_item),
        headers=auth_headers(token),
    )

    assert text_response.status_code == 422
    assert list_response.status_code == 422
    assert item_response.status_code == 422


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
