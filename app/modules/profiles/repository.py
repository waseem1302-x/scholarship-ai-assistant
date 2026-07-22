import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.profiles.models import StudentProfile


class StudentProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_user_id(self, user_id: uuid.UUID) -> StudentProfile | None:
        return self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))

    def add(self, profile: StudentProfile) -> None:
        self.session.add(profile)
