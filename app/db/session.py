from collections.abc import Generator
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.session import SessionTransaction

from app.core.config import get_settings

_TENANT_ID_KEY = "tenant_id"
_TENANT_BYPASS_KEY = "tenant_bypass"

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
SystemSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    info={_TENANT_BYPASS_KEY: True},
)


@event.listens_for(engine, "connect")
def _reject_privileged_production_runtime(
    dbapi_connection: object,
    _connection_record: object,
) -> None:
    """Fail closed if the production API credential can bypass PostgreSQL RLS."""
    if settings.env != "production" or settings.migration_only:
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        role_properties = cursor.fetchone()
    finally:
        cursor.close()

    if role_properties is None or any(role_properties):
        raise RuntimeError(
            "Production APP_DATABASE_URL must use a NOSUPERUSER NOBYPASSRLS role"
        )


def _apply_postgres_context(session: Session, connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        return

    if session.info.get(_TENANT_BYPASS_KEY) is True:
        connection.execute(text("SELECT set_config('app.tenant_bypass', 'on', true)"))
        connection.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
        return

    connection.execute(text("SELECT set_config('app.tenant_bypass', 'off', true)"))
    tenant_id = session.info.get(_TENANT_ID_KEY)
    connection.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id) if tenant_id is not None else ""},
    )


@event.listens_for(Session, "after_begin")
def _restore_context_after_begin(
    session: Session,
    _transaction: SessionTransaction,
    connection: Connection,
) -> None:
    """Reapply transaction-local RLS context after every commit or rollback."""
    _apply_postgres_context(session, connection)


def bind_tenant_context(session: Session, tenant_id: uuid.UUID) -> None:
    """Bind an authenticated tenant to this session without leaking through its pool."""
    if session.info.get(_TENANT_BYPASS_KEY) is True:
        raise RuntimeError("A privileged database session cannot be tenant-bound")

    existing_tenant = session.info.get(_TENANT_ID_KEY)
    if existing_tenant is not None and existing_tenant != tenant_id:
        raise RuntimeError("A database session cannot change tenants")

    session.info[_TENANT_ID_KEY] = tenant_id
    if session.in_transaction():
        connection = session.connection()
        _apply_postgres_context(session, connection)


def get_db() -> Generator[Session, None, None]:
    """Yield a fail-closed API session; authentication binds its tenant context."""
    with SessionLocal() as session:
        yield session


def get_system_db() -> Generator[Session, None, None]:
    """Yield an explicit cross-tenant session for guarded admin/system dependencies."""
    with SystemSessionLocal() as session:
        yield session
