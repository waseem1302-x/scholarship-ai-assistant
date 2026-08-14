"""Request tenant context used by PostgreSQL row-level security policies.

Application ownership predicates remain mandatory. RLS is a second boundary for
mistakes in those predicates, not a replacement for service-layer authorization.
"""

from __future__ import annotations

import uuid

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

_TENANT_INFO_KEY = "tenant_user_id"
_SET_TENANT = text("SELECT set_config('app.current_user_id', :user_id, true)")


def bind_tenant_context(session: Session, user_id: uuid.UUID) -> None:
    """Bind one authenticated user to this request-scoped SQLAlchemy Session.

    `set_config(..., true)` is transaction-local, so pooled PostgreSQL
    connections cannot leak one student's identity into the next request. The
    `after_begin` listener reapplies the identity after service-layer commits
    start a new transaction within the same request session.
    """

    value = str(user_id)
    session.info[_TENANT_INFO_KEY] = value
    if session.get_bind().dialect.name == "postgresql" and session.in_transaction():
        session.execute(_SET_TENANT, {"user_id": value})


def current_tenant_context(session: Session) -> str | None:
    value = session.info.get(_TENANT_INFO_KEY)
    return str(value) if value else None


@event.listens_for(Session, "after_begin")
def _apply_tenant_after_begin(
    session: Session,
    _transaction,
    connection: Connection,
) -> None:
    user_id = current_tenant_context(session)
    if user_id and connection.dialect.name == "postgresql":
        connection.execute(_SET_TENANT, {"user_id": user_id})
