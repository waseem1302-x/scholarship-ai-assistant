"""Add tamper-evident audit log hash columns.

Revision ID: 20260814_0034
Revises: 20260814_0033
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260814_0034"
down_revision = "20260814_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("previous_integrity_hash", sa.String(64)))
    op.add_column(
        "audit_logs",
        sa.Column(
            "integrity_hash",
            sa.String(64),
            nullable=False,
            server_default="legacy-unhashed-audit-record-000000000000000000000000000000",
        ),
    )
    op.create_index("ix_audit_logs_previous_integrity_hash", "audit_logs", ["previous_integrity_hash"])
    op.create_index("ix_audit_logs_integrity_hash", "audit_logs", ["integrity_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_integrity_hash", table_name="audit_logs")
    op.drop_index("ix_audit_logs_previous_integrity_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "integrity_hash")
    op.drop_column("audit_logs", "previous_integrity_hash")
