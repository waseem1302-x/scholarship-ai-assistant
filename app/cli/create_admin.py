import getpass
import os
import uuid

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.modules.auth.models import User, UserRole
from app.modules.auth.repository import AuthRepository


def upsert_admin(session: Session, *, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    if len(password) < 12:
        raise ValueError("Admin password must be at least 12 characters long")

    repository = AuthRepository(session)
    user = repository.get_user_by_email(normalized_email)
    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=normalized_email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        repository.add_user(user)
    else:
        user.role = UserRole.ADMIN
        user.is_active = True
        user.password_hash = hash_password(password)

    session.commit()
    session.refresh(user)
    return user


def main() -> None:
    email = os.getenv("APP_ADMIN_EMAIL") or input("Admin email: ").strip()
    password = os.getenv("APP_ADMIN_PASSWORD") or getpass.getpass("Admin password: ")

    with SessionLocal() as session:
        user = upsert_admin(session, email=email, password=password)
        print(f"Admin account ready: {user.email}")


if __name__ == "__main__":
    main()
