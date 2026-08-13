import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.cli.dispatch_reminders import dispatch_due_reminders
from app.modules.applications.models import Application, ApplicationEvent, DeadlineState
from app.modules.auth.models import User, UserRole
from app.modules.matching.models import MatchEvaluation, MatchEvaluationResult, MatchRuleOutcome
from tests.test_applications import create_user, create_verified_opportunity, headers, login


def test_application_command_centre_is_private_and_records_task_events(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-command@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-command@example.com", role=UserRole.STUDENT)
    create_user(db_session, email="other-command@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-command@example.com"))
    owner_headers = headers(login(client, "owner-command@example.com"))
    other_headers = headers(login(client, "other-command@example.com"))
    opportunity = create_verified_opportunity(
        client,
        admin_headers,
        standardized_test_requirement="IELTS score must be confirmed.",
        application_fee_info="A fee waiver may be available.",
        required_documents=["Transcript", "Recommendation letter"],
    )

    created = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    )
    assert created.status_code == 201
    application = created.json()
    assert application["lifecycle"] == "saved"
    assert {task["category"] for task in application["tasks"]} >= {
        "document",
        "recommendation",
        "test",
        "funding",
    }
    assert all(task["is_generated"] for task in application["tasks"])

    blocked_task = application["tasks"][0]
    assert (
        client.patch(
            f"/api/v1/applications/{application['id']}/tasks/{blocked_task['id']}",
            json={"status": "blocked"},
            headers=owner_headers,
        ).status_code
        == 200
    )
    command_centre = client.get("/api/v1/applications/command-centre", headers=owner_headers)
    assert command_centre.status_code == 200
    assert [item["id"] for item in command_centre.json()["blocked_applications"]] == [
        application["id"]
    ]

    personal_task = {"category": "personal", "title": "Book portal appointment"}
    first_task = client.post(
        f"/api/v1/applications/{application['id']}/tasks",
        json=personal_task,
        headers=owner_headers,
    )
    duplicate_task = client.post(
        f"/api/v1/applications/{application['id']}/tasks",
        json=personal_task,
        headers=owner_headers,
    )
    assert first_task.status_code == 201
    assert duplicate_task.status_code == 409
    assert duplicate_task.json()["error"]["code"] == "duplicate_application_task"

    task = application["tasks"][0]
    completed = client.patch(
        f"/api/v1/applications/{application['id']}/tasks/{task['id']}",
        json={"status": "completed", "completion_evidence": "Uploaded to the official portal."},
        headers=owner_headers,
    )
    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None

    events = client.get(f"/api/v1/applications/{application['id']}/events", headers=owner_headers)
    assert events.status_code == 200
    assert {event["event_type"] for event in events.json()} >= {
        "application.created",
        "task.updated",
    }
    assert (
        client.get(f"/api/v1/applications/{application['id']}", headers=other_headers).status_code
        == 404
    )


def test_reminder_idempotency_and_export_are_owner_scoped(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-reminder@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-reminder@example.com", role=UserRole.STUDENT)
    create_user(db_session, email="other-reminder@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-reminder@example.com"))
    owner_headers = headers(login(client, "owner-reminder@example.com"))
    other_headers = headers(login(client, "other-reminder@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    ).json()
    other_application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=other_headers
    ).json()
    payload = {"scheduled_at": "2027-05-20T09:00:00+08:00", "message": "Check the portal."}
    first = client.post(
        f"/api/v1/applications/{application['id']}/reminders", json=payload, headers=owner_headers
    )
    second = client.post(
        f"/api/v1/applications/{application['id']}/reminders", json=payload, headers=owner_headers
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    shared_payload = {
        "scheduled_at": "2027-05-22T09:00:00+08:00",
        "message": "Shared key, private app.",
        "idempotency_key": "shared-key-001",
    }
    owner_scoped = client.post(
        f"/api/v1/applications/{application['id']}/reminders",
        json=shared_payload,
        headers=owner_headers,
    )
    other_scoped = client.post(
        f"/api/v1/applications/{other_application['id']}/reminders",
        json=shared_payload,
        headers=other_headers,
    )
    owner_repeat = client.post(
        f"/api/v1/applications/{application['id']}/reminders",
        json=shared_payload,
        headers=owner_headers,
    )
    assert owner_scoped.status_code == other_scoped.status_code == owner_repeat.status_code == 201
    assert owner_repeat.json()["id"] == owner_scoped.json()["id"]
    assert other_scoped.json()["id"] != owner_scoped.json()["id"]
    worker_session = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert (
        dispatch_due_reminders(
            now=datetime(2027, 5, 20, 2, 0, tzinfo=UTC), session_factory=worker_session
        )
        == 1
    )
    assert (
        dispatch_due_reminders(
            now=datetime(2027, 5, 20, 2, 1, tzinfo=UTC), session_factory=worker_session
        )
        == 0
    )
    delivered = client.get(f"/api/v1/applications/{application['id']}", headers=owner_headers)
    assert delivered.json()["reminders"][0]["status"] == "delivered"
    health = client.get("/api/v1/applications/reminder-worker-health", headers=owner_headers)
    assert health.status_code == 200
    assert health.json()["processed_count"] == 1

    pending = client.post(
        f"/api/v1/applications/{application['id']}/reminders",
        json={"scheduled_at": "2027-05-21T09:00:00+08:00", "message": "Final check."},
        headers=owner_headers,
    )
    assert pending.status_code == 201
    preference = client.put(
        "/api/v1/applications/notification-preferences",
        json={"in_app_enabled": False},
        headers=owner_headers,
    )
    assert preference.status_code == 200
    assert preference.json()["in_app_enabled"] is False
    cancelled = client.get(f"/api/v1/applications/{application['id']}", headers=owner_headers)
    assert {reminder["status"] for reminder in cancelled.json()["reminders"]} == {
        "delivered",
        "cancelled",
    }
    exported = client.get("/api/v1/applications/export", headers=owner_headers)
    assert exported.status_code == 200
    assert [item["id"] for item in exported.json()["applications"]] == [application["id"]]
    deleted = client.delete("/api/v1/applications/data", headers=owner_headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/applications", headers=owner_headers).json()["items"] == []


def test_phase_four_next_actions_generate_distinct_personal_tasks(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-readiness@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-readiness@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-readiness@example.com"))
    owner_headers = headers(login(client, "owner-readiness@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    owner = db_session.scalar(select(User).where(User.email == "owner-readiness@example.com"))
    assert owner is not None
    evaluation = MatchEvaluation(
        user_id=owner.id,
        matcher_version="phase4-test",
        expires_at=datetime(2028, 1, 1, tzinfo=UTC),
        profile_snapshot_json={},
        profile_snapshot_hash="a" * 64,
    )
    result = MatchEvaluationResult(
        evaluation=evaluation,
        opportunity_id=uuid.UUID(opportunity["id"]),
        rank=1,
        match_score=75,
        fit_score=75,
        score_label="strong",
        eligibility_status="unknown",
        confidence="medium",
        evidence_completeness=80,
        opportunity_snapshot_json={},
        source_snapshot_json=None,
    )
    result.rule_outcomes.append(
        MatchRuleOutcome(
            rule_name="profile",
            outcome="unknown",
            reason_code="profile_incomplete",
            message="Profile information is incomplete.",
            confidence="medium",
            next_actions_json=["Add your current education level"],
        )
    )
    db_session.add(evaluation)
    db_session.commit()

    created = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    )
    assert created.status_code == 201
    generated = {task["title"]: task for task in created.json()["tasks"]}
    assert generated["Add your current education level"]["category"] == "personal"
    assert generated["Add your current education level"]["is_generated"] is True


def test_application_keeps_separate_personal_and_official_timezones(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-timezone@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-timezone@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-timezone@example.com"))
    owner_headers = headers(login(client, "owner-timezone@example.com"))
    opportunity = create_verified_opportunity(
        client,
        admin_headers,
        application_cycles=[
            {
                "application_deadline": "2027-05-30T23:59:59+08:00",
                "timezone": "Asia/Kuala_Lumpur",
            }
        ],
    )
    created = client.post(
        "/api/v1/applications",
        json={
            "opportunity_id": opportunity["id"],
            "personal_deadline": "2027-05-20T18:00:00-04:00",
            "personal_deadline_timezone": "America/Toronto",
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    application = created.json()
    assert application["official_deadline_timezone"] == "Asia/Kuala_Lumpur"
    assert application["personal_deadline_timezone"] == "America/Toronto"
    assert application["deadline_urgency"] == "upcoming"

    invalid_timezone = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"personal_deadline_timezone": "Not/A_Timezone"},
        headers=owner_headers,
    )
    assert invalid_timezone.status_code == 422


def test_source_verification_loss_makes_deadline_uncertain(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-deadline@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-deadline@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-deadline@example.com"))
    owner_headers = headers(login(client, "owner-deadline@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    ).json()
    verification = client.patch(
        f"/api/v1/admin/opportunities/{opportunity['id']}/verification",
        json={"source_id": opportunity["source"]["id"], "verification_status": "needs_review"},
        headers=admin_headers,
    )
    assert verification.status_code == 200
    refreshed = client.get(f"/api/v1/applications/{application['id']}", headers=owner_headers)
    assert refreshed.status_code == 200, refreshed.json()
    assert refreshed.json()["official_deadline_state"] == "uncertain"
    assert refreshed.json()["deadline_urgency"] == "deadline_uncertain"
    db_session.expire_all()
    stored = db_session.get(Application, uuid.UUID(application["id"]))
    assert stored is not None
    assert stored.official_deadline_state is DeadlineState.KNOWN
    deadline_events = db_session.scalars(
        select(ApplicationEvent).where(
            ApplicationEvent.application_id == stored.id,
            ApplicationEvent.event_type == "deadline.changed",
        )
    ).all()
    assert deadline_events == []


def test_document_metadata_is_private_and_never_claims_official_acceptance(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-documents@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-documents@example.com", role=UserRole.STUDENT)
    create_user(db_session, email="other-documents@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-documents@example.com"))
    owner_headers = headers(login(client, "owner-documents@example.com"))
    other_headers = headers(login(client, "other-documents@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    ).json()

    created = client.post(
        f"/api/v1/applications/{application['id']}/documents",
        json={
            "name": "Passport copy",
            "is_required": True,
            "file_name": "passport.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1200,
            "version_label": "v2",
            "expires_at": "2028-05-01T00:00:00+00:00",
            "reviewed_at": "2027-05-01T00:00:00+00:00",
            "is_complete": True,
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    document = created.json()
    assert document["is_complete"] is True
    assert "accepted" not in document

    update = client.patch(
        f"/api/v1/applications/{application['id']}/documents/{document['id']}",
        json={"version_label": "v3", "is_complete": False},
        headers=owner_headers,
    )
    assert update.status_code == 200
    assert update.json()["version_label"] == "v3"
    assert update.json()["is_complete"] is False
    assert (
        client.patch(
            f"/api/v1/applications/{application['id']}/documents/{document['id']}",
            json={"is_complete": True},
            headers=other_headers,
        ).status_code
        == 404
    )


def test_application_conflicts_are_detected_and_event_metadata_is_redacted(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-conflict@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-conflict@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-conflict@example.com"))
    owner_headers = headers(login(client, "owner-conflict@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    ).json()
    secret_note = "private note that must never be in activity metadata"
    changed = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"notes": secret_note, "expected_version": application["version"]},
        headers=owner_headers,
    )
    assert changed.status_code == 200
    missing_version = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"notes": "missing version"},
        headers=owner_headers,
    )
    assert missing_version.status_code == 409
    assert missing_version.json()["error"]["code"] == "application_version_required"
    stale = client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"notes": "other update", "expected_version": application["version"]},
        headers=owner_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "application_version_conflict"

    reminder_message = "private reminder message"
    reminder = client.post(
        f"/api/v1/applications/{application['id']}/reminders",
        json={"scheduled_at": "2028-05-01T09:00:00+00:00", "message": reminder_message},
        headers=owner_headers,
    )
    assert reminder.status_code == 201
    events = client.get(f"/api/v1/applications/{application['id']}/events", headers=owner_headers)
    assert events.status_code == 200
    serialized_metadata = str([event["metadata_json"] for event in events.json()])
    assert secret_note not in serialized_metadata
    assert reminder_message not in serialized_metadata


def test_operational_report_is_admin_only_and_contains_only_aggregate_counts(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-report@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-report@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-report@example.com"))
    owner_headers = headers(login(client, "owner-report@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    ).json()
    private_note = "private report test note"
    task = application["tasks"][0]
    assert (
        client.patch(
            f"/api/v1/applications/{application['id']}/tasks/{task['id']}",
            json={"status": "completed", "completion_evidence": private_note},
            headers=owner_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/applications/{application['id']}/reminders",
            json={
                "scheduled_at": "2028-05-01T09:00:00+00:00",
                "message": "private reminder for report test",
            },
            headers=owner_headers,
        ).status_code
        == 201
    )

    assert (
        client.get("/api/v1/applications/operational-report", headers=owner_headers).status_code
        == 403
    )
    report = client.get("/api/v1/applications/operational-report", headers=admin_headers)
    assert report.status_code == 200
    body = report.json()
    assert body["task_completion_funnel"]["completed"] >= 1
    assert body["open_tasks"] >= 0
    assert "notes" not in body
    assert private_note not in str(body)
    assert "private reminder for report test" not in str(body)


def test_application_api_contract_exposes_paginated_and_private_routes(client: TestClient) -> None:
    contract = client.get("/openapi.json").json()
    paths = contract["paths"]
    assert "/api/v1/applications" in paths
    assert "/api/v1/applications/{application_id}/tasks" in paths
    assert "/api/v1/applications/{application_id}/reminders" in paths
    assert "/api/v1/applications/{application_id}/documents" in paths
    assert "/api/v1/applications/command-centre" in paths
    assert "/api/v1/applications/operational-report" in paths
    assert paths["/api/v1/applications"]["get"]["parameters"]
    schemas = contract["components"]["schemas"]
    assert "ApplicationListResponse" in schemas
    assert "ApplicationOperationalReportResponse" in schemas
    assert schemas["ApplicationListResponse"]["properties"]["pagination"]


def test_reminder_worker_records_a_failure_without_delivering_duplicates(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-worker-failure@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="owner-worker-failure@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-worker-failure@example.com"))
    owner_headers = headers(login(client, "owner-worker-failure@example.com"))
    opportunity = create_verified_opportunity(client, admin_headers)
    application = client.post(
        "/api/v1/applications", json={"opportunity_id": opportunity["id"]}, headers=owner_headers
    ).json()
    assert (
        client.post(
            f"/api/v1/applications/{application['id']}/reminders",
            json={"scheduled_at": "2027-05-20T09:00:00+00:00"},
            headers=owner_headers,
        ).status_code
        == 201
    )
    engine = db_session.get_bind()

    def fail_delivery_update(conn, cursor, statement, parameters, context, executemany):
        if "UPDATE application_reminders" in statement:
            raise RuntimeError("simulated reminder dispatch failure")

    event.listen(engine, "before_cursor_execute", fail_delivery_update)
    worker_session = sessionmaker(bind=engine, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="simulated reminder dispatch failure"):
        dispatch_due_reminders(
            now=datetime(2027, 5, 20, 10, 0, tzinfo=UTC), session_factory=worker_session
        )
    event.remove(engine, "before_cursor_execute", fail_delivery_update)
    health = client.get("/api/v1/applications/reminder-worker-health", headers=owner_headers)
    assert health.status_code == 200
    assert health.json()["failed_count"] == 1
    delivered = client.get(f"/api/v1/applications/{application['id']}", headers=owner_headers)
    assert delivered.json()["reminders"][0]["status"] == "scheduled"
