import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.profiles.models import StudentProfile


class StudentProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_user_id(self, user_id: uuid.UUID) -> StudentProfile | None:
        return self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))

    def add(self, profile: StudentProfile) -> None:
        self.session.add(profile)

    def update_if_version(
        self,
        *,
        user_id: uuid.UUID,
        expected_version: int,
        values: dict[str, object],
    ) -> StudentProfile | None:
        """Atomically apply one validated profile update or return no row."""

        statement = (
            update(StudentProfile)
            .where(
                StudentProfile.user_id == user_id,
                StudentProfile.version == expected_version,
            )
            .values(**values, version=StudentProfile.version + 1)
            .returning(StudentProfile)
        )
        return self.session.scalars(statement).one_or_none()
