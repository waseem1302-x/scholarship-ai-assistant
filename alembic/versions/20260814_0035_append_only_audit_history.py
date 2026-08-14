"""Make audit history append-only and rebuild its integrity chain.

Revision ID: 20260814_0035
Revises: 20260814_0034
Create Date: 2026-08-14
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "20260814_0035"
down_revision = "20260814_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_table() -> sa.TableClause:
    return sa.table(
        "audit_logs",
        sa.column("id", sa.Uuid()),
        sa.column("actor_user_id", sa.Uuid()),
        sa.column("action", sa.String()),
        sa.column("entity_type", sa.String()),
        sa.column("entity_id", sa.String()),
        sa.column("metadata_json", sa.JSON()),
        sa.column("previous_integrity_hash", sa.String()),
        sa.column("integrity_hash", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )


def _hash_row(row: Any, previous_hash: str | None) -> str:
    created_at = row.created_at
    created_value = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
    payload = {
        "previous_hash": previous_hash,
        "id": str(row.id),
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "metadata_json": row.metadata_json or {},
        "created_at": created_value,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _rebuild_chain() -> None:
    connection = op.get_bind()
    audit = _audit_table()
    rows = connection.execute(
        sa.select(audit).order_by(audit.c.created_at.asc(), audit.c.id.asc())
    ).all()
    previous_hash: str | None = None
    for row in rows:
        integrity_hash = _hash_row(row, previous_hash)
        connection.execute(
            sa.update(audit)
            .where(audit.c.id == row.id)
            .values(
                previous_integrity_hash=previous_hash,
                integrity_hash=integrity_hash,
            )
        )
        previous_hash = integrity_hash


def upgrade() -> None:
    connection = op.get_bind()
    _rebuild_chain()

    if connection.dialect.name != "postgresql":
        # SQLite remains supported for portable migration/integration tests.
        # Application-level mapper guards still reject ORM mutation there.
        return

    # Preserve the actor UUID as immutable historical evidence. A foreign key
    # with ON DELETE SET NULL would necessarily mutate the audit row when an
    # account is erased, so production audit history intentionally stores the
    # actor identifier as a snapshot instead.
    op.execute(
        "ALTER TABLE audit_logs "
        "DROP CONSTRAINT IF EXISTS audit_logs_actor_user_id_fkey"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION reject_audit_log_mutation()
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_log_mutation()")

    # Downgrade restores the historic SET NULL foreign-key semantics. Accounts
    # erased while 0035 was active no longer exist, so orphan snapshots must be
    # nulled before the old constraint can be recreated.
    op.execute(
        """
        UPDATE audit_logs AS audit
        SET actor_user_id = NULL
        WHERE actor_user_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM users WHERE users.id = audit.actor_user_id
          )
        """
    )
    op.create_foreign_key(
        "audit_logs_actor_user_id_fkey",
        "audit_logs",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
