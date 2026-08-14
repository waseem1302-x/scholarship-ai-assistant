"""Production-like PostgreSQL RLS smoke test executed explicitly by CI.

This file is intentionally not a pytest test because the normal suite uses an
in-memory SQLite database for speed. CI runs it after Alembic upgrades the real
PostgreSQL service so row-level security is tested by PostgreSQL itself.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["APP_DATABASE_URL"]
TEST_API_ROLE = "scholarship_rls_test_api"
TEST_WORKER_ROLE = "scholarship_worker"


def main() -> None:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    user_c = uuid.uuid4()

    with engine.connect() as connection:
        _cleanup_roles(connection)
        connection.execute(text(f"CREATE ROLE {TEST_API_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS"))
        connection.execute(text(f"CREATE ROLE {TEST_WORKER_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS"))
        connection.execute(
            text(f"GRANT USAGE ON SCHEMA public TO {TEST_API_ROLE}, {TEST_WORKER_ROLE}")
        )
        connection.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON student_profiles "
                f"TO {TEST_API_ROLE}, {TEST_WORKER_ROLE}"
            )
        )
        for user_id, email in (
            (user_a, f"rls-a-{user_a}@example.invalid"),
            (user_b, f"rls-b-{user_b}@example.invalid"),
            (user_c, f"rls-c-{user_c}@example.invalid"),
        ):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, role, is_active, token_version) "
                    "VALUES (:id, :email, 'not-a-real-hash', 'student', true, 0)"
                ),
                {"id": user_id, "email": email},
            )
        connection.execute(
            text(
                "INSERT INTO student_profiles "
                "(id, user_id, english_test_status, gre_status, publications, "
                "preferred_destination_countries, preferred_destination_country_codes, version) "
                "VALUES "
                "(:id_a, :user_a, 'unknown', 'unknown', '[]'::json, '[]'::json, '[]'::json, 1), "
                "(:id_b, :user_b, 'unknown', 'unknown', '[]'::json, '[]'::json, '[]'::json, 1)"
            ),
            {
                "id_a": uuid.uuid4(),
                "user_a": user_a,
                "id_b": uuid.uuid4(),
                "user_b": user_b,
            },
        )
        connection.commit()

        try:
            _assert_api_role_is_isolated(connection, user_a, user_b, user_c)
            _assert_worker_role_can_process_cross_tenant_rows(connection)
        finally:
            connection.rollback()
            connection.exec_driver_sql("RESET ROLE")
            connection.execute(
                text("DELETE FROM users WHERE id IN (:a, :b, :c)"),
                {"a": user_a, "b": user_b, "c": user_c},
            )
            connection.commit()
            _cleanup_roles(connection)
            connection.commit()

    engine.dispose()
    print("PostgreSQL RLS smoke test passed")


def _assert_api_role_is_isolated(
    connection,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
    user_c: uuid.UUID,
) -> None:
    connection.exec_driver_sql(f"SET ROLE {TEST_API_ROLE}")
    connection.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_a)},
    )

    visible = connection.execute(
        text("SELECT user_id FROM student_profiles ORDER BY user_id")
    ).scalars().all()
    if visible != [user_a]:
        raise AssertionError(f"API tenant saw unexpected profile owners: {visible!r}")

    update_result = connection.execute(
        text("UPDATE student_profiles SET nationality = 'blocked' WHERE user_id = :other"),
        {"other": user_b},
    )
    if update_result.rowcount != 0:
        raise AssertionError("API tenant updated another student's profile")

    try:
        connection.execute(
            text(
                "INSERT INTO student_profiles "
                "(id, user_id, english_test_status, gre_status, publications, "
                "preferred_destination_countries, preferred_destination_country_codes, version) "
                "VALUES (:id, :other, 'unknown', 'unknown', '[]'::json, '[]'::json, '[]'::json, 1)"
            ),
            {"id": uuid.uuid4(), "other": user_c},
        )
    except Exception:
        # PostgreSQL WITH CHECK must reject insertion for a different tenant.
        connection.rollback()
        connection.exec_driver_sql(f"SET ROLE {TEST_API_ROLE}")
        connection.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_a)},
        )
    else:
        raise AssertionError("API tenant inserted a profile for another user")

    connection.rollback()
    connection.exec_driver_sql("RESET ROLE")


def _assert_worker_role_can_process_cross_tenant_rows(connection) -> None:
    connection.exec_driver_sql(f"SET ROLE {TEST_WORKER_ROLE}")
    count = connection.execute(text("SELECT count(*) FROM student_profiles")).scalar_one()
    if count < 2:
        raise AssertionError("Scheduled worker role cannot see cross-tenant rows")
    connection.rollback()
    connection.exec_driver_sql("RESET ROLE")


def _cleanup_roles(connection) -> None:
    connection.exec_driver_sql("RESET ROLE")
    for role in (TEST_API_ROLE, TEST_WORKER_ROLE):
        connection.exec_driver_sql(
            "DO $$ BEGIN "
            f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"EXECUTE 'DROP OWNED BY {role}'; "
            f"EXECUTE 'DROP ROLE {role}'; "
            "END IF; END $$;"
        )


if __name__ == "__main__":
    main()
