import uuid
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.modules.auth.models import UserRole
from app.modules.auth.service import AuthService


def test_alembic_schema_accepts_orm_enums_and_portable_timestamp_defaults(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration-integration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    repository_root = Path(__file__).parents[1]
    alembic_config = Config(repository_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(repository_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    settings = Settings(
        env="test",
        database_url=database_url,
        jwt_secret="migration-test-secret-at-least-32-characters",
    )
    with Session(engine) as session:
        result = AuthService(session, settings).register(
            "migrated@example.com", "MigrationPassword123"
        )
        assert result.user.role is UserRole.STUDENT

        session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, role, is_active) "
                "VALUES (:id, :email, :password_hash, :role, :is_active)"
            ),
            {
                "id": uuid.uuid4().hex,
                "email": "database-default@example.com",
                "password_hash": "unused",
                "role": "student",
                "is_active": True,
            },
        )
        session.commit()
        created_at = session.scalar(
            text("SELECT created_at FROM users WHERE email = 'database-default@example.com'")
        )
        assert created_at is not None
    engine.dispose()
