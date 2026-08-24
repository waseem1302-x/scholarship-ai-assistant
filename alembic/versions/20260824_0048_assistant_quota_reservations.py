"""atomically reserve assistant quota before provider work

Revision ID: 20260824_0048
Revises: 20260824_0047
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260824_0048"
down_revision: str | None = "20260824_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enable_tenant_policy(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        FOR ALL
        USING (scholarship_tenant_bypass() OR user_id = scholarship_current_tenant_id())
        WITH CHECK (scholarship_tenant_bypass() OR user_id = scholarship_current_tenant_id())
        """
    )


def upgrade() -> None:
    op.create_table(
        "assistant_quota_counters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("window", sa.String(length=16), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("used_slots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("used_slots >= 0", name="ck_assistant_quota_counters_nonnegative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "window", "window_start"),
    )
    op.create_table(
        "assistant_quota_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("daily_window_start", sa.Date(), nullable=False),
        sa.Column("monthly_window_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="reserved"),
        sa.Column("answer_id", sa.Uuid(), nullable=True),
        sa.Column("terminal_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["answer_id"], ["assistant_answers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id", name="uq_assistant_quota_reservations_answer_id"),
    )
    op.create_index(
        "ix_assistant_quota_reservations_user_created",
        "assistant_quota_reservations",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_assistant_quota_reservations_status",
        "assistant_quota_reservations",
        ["status"],
    )

    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO assistant_quota_counters (user_id, window, window_start, used_slots)
            SELECT user_id, 'daily', (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date, COUNT(*)
            FROM assistant_answers
            WHERE created_at >= (
                date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            )
            GROUP BY user_id
            UNION ALL
            SELECT user_id, 'monthly',
                date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date, COUNT(*)
            FROM assistant_answers
            WHERE created_at >= (
                date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            )
            GROUP BY user_id
            """
        )
        _enable_tenant_policy("assistant_quota_counters")
        _enable_tenant_policy("assistant_quota_reservations")
    elif connection.dialect.name == "sqlite":
        op.execute(
            """
            INSERT INTO assistant_quota_counters (user_id, window, window_start, used_slots)
            SELECT user_id, 'daily', date('now'), COUNT(*)
            FROM assistant_answers
            WHERE created_at >= date('now')
            GROUP BY user_id
            UNION ALL
            SELECT user_id, 'monthly', date('now', 'start of month'), COUNT(*)
            FROM assistant_answers
            WHERE created_at >= date('now', 'start of month')
            GROUP BY user_id
            """
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        for table in ("assistant_quota_reservations", "assistant_quota_counters"):
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_assistant_quota_reservations_status", table_name="assistant_quota_reservations"
    )
    op.drop_index(
        "ix_assistant_quota_reservations_user_created", table_name="assistant_quota_reservations"
    )
    op.drop_table("assistant_quota_reservations")
    op.drop_table("assistant_quota_counters")
