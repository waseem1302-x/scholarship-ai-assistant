import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.applications.models import Application
from app.modules.auth.models import AuditLog, User, UserRole
from app.modules.community.models import CommunityPost, CommunityPreference
from tests.test_opportunities import (
    admin_headers,
    create_opportunity,
    create_user,
    login,
    publish_opportunity,
)


def community_headers(client: TestClient, db_session: Session, email: str) -> dict[str, str]:
    create_user(db_session, email=email, role=UserRole.STUDENT)
    headers = {"Authorization": f"Bearer {login(client, email=email)}"}
    response = client.put(
        "/api/v1/community/preferences",
        json={
            "display_name": email.split("@")[0].replace(".", "-"),
            "consent": True,
        },
        headers=headers,
    )
    assert response.status_code == 200
    return headers


def verified_opportunity(client: TestClient, db_session: Session) -> dict:
    admin = admin_headers(client, db_session)
    now = datetime.now(UTC)
    created = create_opportunity(
        client,
        admin,
        application_opening_date=(now - timedelta(days=1)).isoformat(),
        application_deadline=(now + timedelta(days=30)).isoformat(),
    )
    publish_opportunity(client, admin, created)
    return created


def create_post(
    client: TestClient,
    headers: dict[str, str],
    opportunity_id: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/community/posts",
        json={
            "topic": "application_process",
            "title": "How did you organise the official checklist?",
            "body": (
                "I am looking for practical, scholarship-specific ways to organise my checklist."
            ),
            "opportunity_id": opportunity_id,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_community_is_pseudonymous_scholarship_linked_and_owner_scoped(
    client: TestClient, db_session: Session
) -> None:
    opportunity = verified_opportunity(client, db_session)
    author = community_headers(client, db_session, "author.member@example.com")
    reader = community_headers(client, db_session, "reader.member@example.com")
    post = create_post(client, author, opportunity["id"])

    assert post["author"]["display_name"] == "author-member"
    assert "email" not in post["author"]
    assert post["opportunity"] == {
        "id": opportunity["id"],
        "name": opportunity["name"],
    }
    assert (
        client.patch(
            f"/api/v1/community/posts/{post['id']}",
            json={
                "topic": "question",
                "title": "Another member title",
                "body": "A different student must not change this post.",
            },
            headers=reader,
        ).status_code
        == 404
    )

    reply = client.post(
        f"/api/v1/community/posts/{post['id']}/replies",
        json={"body": "I used the official provider checklist and a personal deadline."},
        headers=reader,
    )
    assert reply.status_code == 201
    detail = client.get(f"/api/v1/community/posts/{post['id']}", headers=author)
    assert detail.status_code == 200
    assert detail.json()["replies"][0]["author"]["display_name"] == "reader-member"


def test_community_enforces_consent_safe_content_and_verified_opportunities(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="no-consent@example.com", role=UserRole.STUDENT)
    headers = {"Authorization": f"Bearer {login(client, email='no-consent@example.com')}"}
    assert (
        client.post(
            "/api/v1/community/posts",
            json={
                "topic": "question",
                "title": "Need a safe answer",
                "body": "This is sufficiently long for a community post.",
            },
            headers=headers,
        ).status_code
        == 403
    )
    community_headers(client, db_session, "safe.member@example.com")
    safe = {"Authorization": f"Bearer {login(client, email='safe.member@example.com')}"}
    rejected = client.post(
        "/api/v1/community/posts",
        json={
            "topic": "question",
            "title": "Contact me",
            "body": "Email member@example.com so I can guarantee admission.",
        },
        headers=safe,
    )
    assert rejected.status_code == 400
    unknown = client.post(
        "/api/v1/community/posts",
        json={
            "topic": "question",
            "title": "Unverified opportunity",
            "body": "This should not attach to an unknown scholarship record.",
            "opportunity_id": "11111111-1111-1111-1111-111111111111",
        },
        headers=safe,
    )
    assert unknown.status_code == 404


def test_block_report_and_moderation_hide_content_with_safe_audit(
    client: TestClient, db_session: Session
) -> None:
    author = community_headers(client, db_session, "blocked.author@example.com")
    reader = community_headers(client, db_session, "blocking.reader@example.com")
    post = create_post(client, author)
    assert (
        client.post(
            "/api/v1/community/blocks",
            json={"user_id": post["author"]["id"]},
            headers=reader,
        ).status_code
        == 204
    )
    assert client.get("/api/v1/community/posts", headers=reader).json()["posts"] == []
    assert client.get("/api/v1/community/posts", headers=author).json()["posts"]
    assert (
        client.delete(
            f"/api/v1/community/blocks/{post['author']['id']}", headers=reader
        ).status_code
        == 204
    )
    report = client.post(
        "/api/v1/community/reports",
        json={
            "post_id": post["id"],
            "reason": "misleading",
            "detail": "Please check the evidence.",
        },
        headers=reader,
    )
    assert report.status_code == 201
    admin = admin_headers(client, db_session)
    queue = client.get("/api/v1/community/admin/reports", headers=admin)
    assert queue.status_code == 200
    assert queue.json()["reports"][0]["content_id"] == post["id"]
    hidden = client.post(
        "/api/v1/community/admin/moderation-actions",
        json={
            "action": "hide",
            "post_id": post["id"],
            "reason": "Pending evidence review.",
        },
        headers=admin,
    )
    assert hidden.status_code == 204
    assert client.get(f"/api/v1/community/posts/{post['id']}", headers=reader).status_code == 404
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "community.hide"))
    assert audit is not None
    assert audit.metadata_json == {"phase": "community"}


def test_community_delete_is_strictly_scoped_to_community_data(
    client: TestClient, db_session: Session
) -> None:
    headers = community_headers(client, db_session, "delete.scope@example.com")
    post = create_post(client, headers)
    user = db_session.scalar(select(User).where(User.email == "delete.scope@example.com"))
    assert user is not None
    application = Application(
        user_id=user.id,
        opportunity_id=uuid.UUID(verified_opportunity(client, db_session)["id"]),
    )
    db_session.add(application)
    db_session.commit()
    exported = client.get("/api/v1/community/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json()["posts"][0]["id"] == post["id"]
    assert client.delete("/api/v1/community/data", headers=headers).status_code == 204
    assert db_session.get(CommunityPreference, user.id) is None
    assert (
        db_session.scalar(select(CommunityPost).where(CommunityPost.author_user_id == user.id))
        is None
    )
    assert db_session.get(Application, application.id) is not None
