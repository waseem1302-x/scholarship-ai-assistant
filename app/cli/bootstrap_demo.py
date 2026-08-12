"""Create a demo administrator and load the curated catalogue in one command."""

import getpass
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.cli.create_admin import upsert_admin
from app.cli.seed_verified_opportunities import seed_verified_opportunities
from app.db.session import SessionLocal
from app.modules.auth.models import User


def bootstrap_demo(
    session: Session,
    *,
    email: str,
    password: str,
    seed_path: Path | None = None,
) -> tuple[User, dict[str, int]]:
    """Validate and load the demo dataset using an idempotent administrator account."""
    # Validate every record before changing the user or catalogue tables.
    seed_verified_opportunities(session, seed_path=seed_path, dry_run=True)

    admin = upsert_admin(session, email=email, password=password)
    summary = seed_verified_opportunities(
        session,
        admin_email=admin.email,
        seed_path=seed_path,
    )
    return admin, summary


def main() -> None:
    email = os.getenv("APP_DEMO_ADMIN_EMAIL") or input("Demo admin email: ").strip()
    password = os.getenv("APP_DEMO_ADMIN_PASSWORD") or getpass.getpass("Demo admin password: ")
    configured_seed_path = os.getenv("APP_DEMO_SEED_FILE")
    seed_path = Path(configured_seed_path) if configured_seed_path else None

    with SessionLocal() as session:
        admin, summary = bootstrap_demo(
            session,
            email=email,
            password=password,
            seed_path=seed_path,
        )

    print(
        f"Demo bootstrap complete for {admin.email}: "
        f"{summary['validated']} records validated, "
        f"{summary['created']} created, "
        f"{summary['skipped_duplicates']} duplicates skipped"
    )


if __name__ == "__main__":
    main()
