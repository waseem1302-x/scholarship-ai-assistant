"""Add normalized private application command-centre records.

Revision ID: 20260812_0010
Revises: 20260812_0009
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260812_0010"
down_revision = "20260812_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    lifecycle = enum(
        (
            "saved",
            "preparing",
            "ready_to_submit",
            "submitted",
            "decision_received",
            "accepted",
            "declined",
            "withdrawn",
        ),
        "application_lifecycle",
    )
    deadline_state = enum(("known", "changed", "uncertain"), "application_deadline_state")
    task_category = enum(
        ("document", "test", "recommendation", "funding", "official_verification", "personal"),
        "application_task_category",
    )
    task_status = enum(
        ("todo", "in_progress", "blocked", "completed", "dismissed"), "application_task_status"
    )
    task_priority = enum(("low", "normal", "high", "urgent"), "application_task_priority")
    reminder_status = enum(
        ("scheduled", "delivered", "read", "snoozed", "cancelled", "failed"),
        "application_reminder_status",
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("saved_opportunities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lifecycle", lifecycle, nullable=False),
        sa.Column("official_deadline", sa.DateTime(timezone=True)),
        sa.Column(
            "official_deadline_timezone", sa.String(64), nullable=False, server_default="UTC"
        ),
        sa.Column("official_deadline_state", deadline_state, nullable=False),
        sa.Column(
            "official_deadline_source_id",
            sa.Uuid(),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "official_deadline_excerpt_id",
            sa.Uuid(),
            sa.ForeignKey("source_excerpts.id", ondelete="SET NULL"),
        ),
        sa.Column("official_deadline_verified_at", sa.DateTime(timezone=True)),
        sa.Column("personal_deadline", sa.DateTime(timezone=True)),
        sa.Column(
            "personal_deadline_timezone", sa.String(64), nullable=False, server_default="UTC"
        ),
        sa.Column("notes", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("decision_notes", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "opportunity_id", name="uq_applications_user_opportunity"),
        sa.UniqueConstraint("saved_opportunity_id", name="uq_applications_saved_opportunity"),
    )
    op.create_index("ix_applications_user_lifecycle", "applications", ["user_id", "lifecycle"])
    op.create_index("ix_applications_official_deadline", "applications", ["official_deadline"])
    op.create_table(
        "application_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", task_category, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("priority", task_priority, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column(
            "source_excerpt_id", sa.Uuid(), sa.ForeignKey("source_excerpts.id", ondelete="SET NULL")
        ),
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completion_evidence", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "application_id",
            "category",
            "title",
            name="uq_application_tasks_application_category_title",
        ),
    )
    op.create_index(
        "ix_application_tasks_application_status_due",
        "application_tasks",
        ["application_id", "status", "due_at"],
    )
    op.create_table(
        "application_reminders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("application_tasks.id", ondelete="CASCADE")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("message", sa.String(500)),
        sa.Column("status", reminder_status, nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_application_reminders_idempotency"),
    )
    op.create_index(
        "ix_application_reminders_status_scheduled",
        "application_reminders",
        ["status", "scheduled_at"],
    )
    op.create_table(
        "application_notification_preferences",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "reminder_worker_health",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_completed_at", sa.DateTime(timezone=True)),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
    )
    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_application_events_application_created",
        "application_events",
        ["application_id", "created_at"],
    )
    op.create_table(
        "application_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("application_tasks.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("file_name", sa.String(255)),
        sa.Column("content_type", sa.String(100)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("version_label", sa.String(100)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_application_documents_application", "application_documents", ["application_id"]
    )

    # Portable data migration: preserve every saved tracker row and its JSON lists.
    bind = op.get_bind()
    saved = sa.table(
        "saved_opportunities",
        sa.column("id"),
        sa.column("user_id"),
        sa.column("opportunity_id"),
        sa.column("status"),
        sa.column("personal_notes"),
        sa.column("personal_deadline"),
        sa.column("document_checklist", sa.JSON()),
        sa.column("recommendation_letters", sa.JSON()),
        sa.column("test_requirements", sa.JSON()),
        sa.column("submitted_at"),
        sa.column("outcome_notes"),
    )
    opportunities = sa.table("opportunities", sa.column("id"), sa.column("application_deadline"))
    statement = sa.select(
        saved,
        opportunities.c.application_deadline,
    ).select_from(saved.outerjoin(opportunities, saved.c.opportunity_id == opportunities.c.id))
    rows = bind.execute(statement).mappings()
    for row in rows:
        status = row["status"]
        mapped = {
            "interested": "saved",
            "researching": "preparing",
            "preparing_documents": "preparing",
            "waiting_for_recommendation": "preparing",
            "ready_to_apply": "ready_to_submit",
            "submitted": "submitted",
            "interview_stage": "decision_received",
            "accepted": "accepted",
            "rejected": "declined",
            "withdrawn": "withdrawn",
            "expired": "withdrawn",
        }[status]
        app_id = uuid.uuid4()
        deadline = row["application_deadline"]
        bind.execute(
            sa.insert(
                sa.table(
                    "applications",
                    sa.column("id"),
                    sa.column("user_id"),
                    sa.column("opportunity_id"),
                    sa.column("saved_opportunity_id"),
                    sa.column("lifecycle"),
                    sa.column("official_deadline"),
                    sa.column("official_deadline_timezone"),
                    sa.column("official_deadline_state"),
                    sa.column("official_deadline_source_id"),
                    sa.column("official_deadline_verified_at"),
                    sa.column("personal_deadline"),
                    sa.column("personal_deadline_timezone"),
                    sa.column("notes"),
                    sa.column("submitted_at"),
                    sa.column("decision_notes"),
                    sa.column("version"),
                )
            ).values(
                id=app_id.hex,
                user_id=row["user_id"],
                opportunity_id=row["opportunity_id"],
                saved_opportunity_id=row["id"],
                lifecycle=mapped,
                official_deadline=deadline,
                official_deadline_timezone="UTC",
                official_deadline_state="known" if deadline else "uncertain",
                # The opportunity retains its evidence; the first command-centre read
                # links the current verified official source without duplicating rows.
                official_deadline_source_id=None,
                official_deadline_verified_at=None,
                personal_deadline=row["personal_deadline"],
                personal_deadline_timezone="UTC",
                notes=row["personal_notes"],
                submitted_at=row["submitted_at"],
                decision_notes=row["outcome_notes"],
                version=1,
            )
        )
        bind.execute(
            sa.insert(
                sa.table(
                    "application_events",
                    sa.column("id"),
                    sa.column("application_id"),
                    sa.column("actor_user_id"),
                    sa.column("event_type"),
                    sa.column("metadata_json", sa.JSON()),
                )
            ).values(
                id=uuid.uuid4().hex,
                application_id=app_id.hex,
                actor_user_id=row["user_id"],
                event_type="application.migrated",
                metadata_json={"legacy_saved_opportunity_id": str(row["id"])},
            )
        )
        for field, category in (
            ("document_checklist", "document"),
            ("recommendation_letters", "recommendation"),
            ("test_requirements", "test"),
        ):
            migrated_titles: set[tuple[str, str]] = set()
            for item in row[field] or []:
                title = str(item.get("name", "Untitled task")).strip() or "Untitled task"
                key = (category, title)
                if key in migrated_titles:
                    continue
                migrated_titles.add(key)
                bind.execute(
                    sa.insert(
                        sa.table(
                            "application_tasks",
                            sa.column("id"),
                            sa.column("application_id"),
                            sa.column("category"),
                            sa.column("title"),
                            sa.column("status"),
                            sa.column("priority"),
                            sa.column("is_generated"),
                            sa.column("completion_evidence"),
                            sa.column("completed_at"),
                            sa.column("notes"),
                        )
                    ).values(
                        id=uuid.uuid4().hex,
                        application_id=app_id.hex,
                        category=category,
                        title=title,
                        status="completed" if item.get("is_complete") else "todo",
                        priority="normal",
                        is_generated=False,
                        completion_evidence="Migrated checklist completion"
                        if item.get("is_complete")
                        else None,
                        completed_at=datetime.now(UTC) if item.get("is_complete") else None,
                        notes=item.get("notes"),
                    )
                )


def downgrade() -> None:
    for name in (
        "application_documents",
        "application_events",
        "application_reminders",
        "application_notification_preferences",
        "reminder_worker_health",
        "application_tasks",
        "applications",
    ):
        op.drop_table(name)
