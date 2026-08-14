from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.modules.auth.models import UserRole
from app.modules.document_lab.routes import get_document_lab_service
from app.modules.document_lab.scanner import SignatureTestScanner
from app.modules.document_lab.service import DocumentLabService
from app.modules.document_lab.validation import PDF_CONTENT_TYPE
from tests.test_applications import create_verified_opportunity
from tests.test_applications import headers as application_headers
from tests.test_document_lab_intake import pdf, settings
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
    assert body["feature_enabled"] is True
    assert body["accepting_uploads"] is True
    assert body["enabled"] == body["accepting_uploads"]
    assert body["scanner_ready"] is False
    assert body["worker_ready"] is False
    assert body["analysis_provider_ready"] is False
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


def test_raw_upload_contract_is_authenticated_owner_scoped_and_quarantined(
    client: TestClient, db_session: Session, tmp_path
) -> None:
    owner_headers = headers(client, db_session, "document-api-owner@example.com")
    other_headers = headers(client, db_session, "document-api-other@example.com")
    service = DocumentLabService(
        db_session,
        settings(tmp_path),
        scanner=SignatureTestScanner(),
    )
    app.dependency_overrides[get_document_lab_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/document-lab/assets?document_kind=cv_resume",
            content=pdf(),
            headers={
                **owner_headers,
                "Content-Type": PDF_CONTENT_TYPE,
                "X-Document-Filename": "resume.pdf",
            },
        )
        assert response.status_code == 202
        version_id = response.json()["versions"][0]["id"]
        assert response.json()["versions"][0]["status"] == "quarantined"
        assert (
            client.get(
                f"/api/v1/document-lab/versions/{version_id}/download", headers=other_headers
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_document_lab_service, None)


def test_linking_requires_confirmation_and_both_owned_records(
    client: TestClient, db_session: Session, tmp_path
) -> None:
    create_user(db_session, email="document-link-admin@example.com", role=UserRole.ADMIN)
    owner_headers = headers(client, db_session, "document-link-owner@example.com")
    other_headers = headers(client, db_session, "document-link-other@example.com")
    admin_headers = application_headers(login(client, email="document-link-admin@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications",
        json={"opportunity_id": opportunity["id"]},
        headers=owner_headers,
    ).json()
    application_document = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        json={"name": "Statement"},
        headers=owner_headers,
    ).json()
    service = DocumentLabService(
        db_session,
        settings(tmp_path),
        scanner=SignatureTestScanner(),
    )
    app.dependency_overrides[get_document_lab_service] = lambda: service
    try:
        uploaded = client.post(
            "/api/v1/document-lab/assets?document_kind=statement_of_purpose",
            content=pdf("My private statement"),
            headers={
                **owner_headers,
                "Content-Type": PDF_CONTENT_TYPE,
                "X-Document-Filename": "statement.pdf",
            },
        ).json()
        version_id = uploaded["versions"][0]["id"]
        unconfirmed = client.post(
            f"/api/v1/document-lab/application-documents/{application_document['id']}/link",
            json={"version_id": version_id, "confirmed": False},
            headers=owner_headers,
        )
        assert unconfirmed.status_code == 422
        linked = client.post(
            f"/api/v1/document-lab/application-documents/{application_document['id']}/link",
            json={"version_id": version_id, "confirmed": True},
            headers=owner_headers,
        )
        assert linked.status_code == 200
        assert (
            client.post(
                f"/api/v1/document-lab/application-documents/{application_document['id']}/link",
                json={"version_id": version_id, "confirmed": True},
                headers=other_headers,
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.pop(get_document_lab_service, None)
