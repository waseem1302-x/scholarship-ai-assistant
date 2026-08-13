"""Create the moderated scholarship-only community domain.

Revision ID: 20260813_0014
Revises: 20260812_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260813_0014"
down_revision = "20260812_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def uuid_column(name: str, *constraints: object, **kwargs: object) -> sa.Column:
    return sa.Column(name, sa.Uuid(), *constraints, **kwargs)


def upgrade() -> None:
    topic = enum(
        (
            "application_process",
            "documents",
            "interview",
            "official_source_update",
            "timeline",
            "question",
            "general",
        ),
        "community_topic",
    )
    content_status = enum(("visible", "hidden", "deleted"), "community_content_status")
    report_reason = enum(
        (
            "harassment",
            "hate_or_discrimination",
            "misleading",
            "off_topic",
            "privacy",
            "solicitation",
            "other",
        ),
        "community_report_reason",
    )
    report_status = enum(("open", "resolved"), "community_report_status")
    moderation_action = enum(
        ("hide", "restore", "resolve_report", "suspend", "reinstate"), "community_moderation_action"
    )

    op.create_table(
        "community_preferences",
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_name", sa.String(40), nullable=False, unique=True),
        sa.Column("consented_at", sa.DateTime(timezone=True)),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("suspension_reason", sa.String(300)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_community_preferences_display_name", "community_preferences", ["display_name"]
    )
    op.create_table(
        "community_posts",
        uuid_column("id", primary_key=True),
        uuid_column("author_user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        uuid_column(
            "opportunity_id", sa.ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("topic", topic, nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", content_status, nullable=False, server_default="visible"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_community_posts_author_user_id", "community_posts", ["author_user_id"])
    op.create_index("ix_community_posts_opportunity_id", "community_posts", ["opportunity_id"])
    op.create_index(
        "ix_community_posts_status_created", "community_posts", ["status", "created_at"]
    )
    op.create_index(
        "ix_community_posts_opportunity_status", "community_posts", ["opportunity_id", "status"]
    )
    op.create_table(
        "community_replies",
        uuid_column("id", primary_key=True),
        uuid_column("post_id", sa.ForeignKey("community_posts.id", ondelete="CASCADE")),
        uuid_column("author_user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", content_status, nullable=False, server_default="visible"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_community_replies_post_id", "community_replies", ["post_id"])
    op.create_index("ix_community_replies_author_user_id", "community_replies", ["author_user_id"])
    op.create_index(
        "ix_community_replies_post_status_created",
        "community_replies",
        ["post_id", "status", "created_at"],
    )
    op.create_table(
        "community_bookmarks",
        uuid_column("id", primary_key=True),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        uuid_column("post_id", sa.ForeignKey("community_posts.id", ondelete="CASCADE")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "post_id", name="uq_community_bookmarks_user_post"),
    )
    op.create_index("ix_community_bookmarks_user_id", "community_bookmarks", ["user_id"])
    op.create_index("ix_community_bookmarks_post_id", "community_bookmarks", ["post_id"])
    op.create_table(
        "community_blocks",
        uuid_column("id", primary_key=True),
        uuid_column("user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        uuid_column("blocked_user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "blocked_user_id", name="uq_community_blocks_user_target"),
        sa.CheckConstraint("user_id <> blocked_user_id", name="ck_community_blocks_no_self"),
    )
    op.create_index("ix_community_blocks_user_id", "community_blocks", ["user_id"])
    op.create_index("ix_community_blocks_blocked_user_id", "community_blocks", ["blocked_user_id"])
    op.create_table(
        "community_reports",
        uuid_column("id", primary_key=True),
        uuid_column("reporter_user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        uuid_column(
            "post_id", sa.ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=True
        ),
        uuid_column(
            "reply_id", sa.ForeignKey("community_replies.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("reason", report_reason, nullable=False),
        sa.Column("detail", sa.String(500)),
        sa.Column("status", report_status, nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        uuid_column(
            "resolved_by_user_id", sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(post_id IS NOT NULL) <> (reply_id IS NOT NULL)",
            name="ck_community_reports_one_target",
        ),
        sa.UniqueConstraint(
            "reporter_user_id", "post_id", "reply_id", name="uq_community_reports_reporter_target"
        ),
    )
    op.create_index(
        "ix_community_reports_reporter_user_id", "community_reports", ["reporter_user_id"]
    )
    op.create_index("ix_community_reports_post_id", "community_reports", ["post_id"])
    op.create_index("ix_community_reports_reply_id", "community_reports", ["reply_id"])
    op.create_index(
        "ix_community_reports_status_created", "community_reports", ["status", "created_at"]
    )
    op.create_table(
        "community_moderation_records",
        uuid_column("id", primary_key=True),
        uuid_column("moderator_user_id", sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("action", moderation_action, nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(300)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_community_moderation_records_moderator_user_id",
        "community_moderation_records",
        ["moderator_user_id"],
    )
    op.create_index(
        "ix_community_moderation_records_target_created",
        "community_moderation_records",
        ["target_type", "target_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("community_moderation_records")
    op.drop_table("community_reports")
    op.drop_table("community_blocks")
    op.drop_table("community_bookmarks")
    op.drop_table("community_replies")
    op.drop_table("community_posts")
    op.drop_table("community_preferences")
