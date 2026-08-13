from app.modules.auth.models import User
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.profiles.schemas import (
    StudentProfileResponse,
    StudentProfileUpsert,
)

RECOMMENDED_FIELDS = [
    "nationality",
    "country_of_residence",
    "current_education_level",
    "target_degree_level",
    "intended_field",
    "academic_discipline",
    "cgpa",
    "grading_scale",
    "english_test_status",
    "preferred_destination_countries",
    "target_intake",
    "target_intake_year",
]


class StudentProfileService:
    def __init__(self, repository: StudentProfileRepository) -> None:
        self.repository = repository

    def get_my_profile(self, user: User) -> StudentProfileResponse | None:
        profile = self.repository.get_by_user_id(user.id)
        return self.to_response(profile) if profile is not None else None

    def upsert_my_profile(
        self, user: User, payload: StudentProfileUpsert
    ) -> StudentProfileResponse:
        profile = self.repository.get_by_user_id(user.id)
        values = payload.model_dump()
        if profile is None:
            profile = StudentProfile(user_id=user.id, **values)
            self.repository.add(profile)
        else:
            for key, value in values.items():
                setattr(profile, key, value)

        self.repository.session.commit()
        self.repository.session.refresh(profile)
        return self.to_response(profile)

    def to_response(self, profile: StudentProfile) -> StudentProfileResponse:
        missing = self._missing_recommended_fields(profile)
        completed = len(RECOMMENDED_FIELDS) - len(missing)
        completeness = round((completed / len(RECOMMENDED_FIELDS)) * 100)
        data = {field: getattr(profile, field) for field in StudentProfileUpsert.model_fields}
        return StudentProfileResponse(
            **data,
            id=profile.id,
            user_id=profile.user_id,
            profile_completeness=completeness,
            missing_recommended_fields=missing,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _missing_recommended_fields(profile: StudentProfile) -> list[str]:
        missing: list[str] = []
        for field in RECOMMENDED_FIELDS:
            value = getattr(profile, field)
            if (
                value is None
                or value == []
                or (field == "english_test_status" and value.value == "unknown")
            ):
                missing.append(field)
        return missing
