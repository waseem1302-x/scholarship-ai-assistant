from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.auth.models import UserRole
from tests.test_opportunities import create_user, login


def headers(client: TestClient, db_session: Session, email: str) -> dict[str, str]:
    create_user(db_session, email=email, role=UserRole.STUDENT)
    return {"Authorization": f"Bearer {login(client, email=email)}"}


def test_document_lab_policy_is_authenticated_and_declares_safe_limits(
    client: TestClient, db_session: Session
) -> None:
    assert client.get("/api/v1/document-lab/policy").status_code == 401
    response = client.get(
        "/api/v1/document-lab/policy",
        headers=headers(client, db_session, "document-policy@example.com"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["supported_types"] == [
        "cv_resume",
        "statement_of_purpose",
        "personal_statement",
        "motivation_letter",
    ]
    assert body["max_upload_bytes"] == 10_000_000
    assert body["max_pages"] == 50
    assert body["max_extracted_characters"] == 100_000
    assert "eligibility" in body["data_use_notice"]
