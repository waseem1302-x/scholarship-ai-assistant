from app.core.errors import ConflictError
from app.modules.auth.models import User
from app.modules.profiles.models import StudentProfile
from app.modules.profiles.repository import StudentProfileRepository
from app.modules.profiles.schemas import (
    StudentProfilePatch,
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
        values = payload.model_dump(exclude={"expected_version"})
        if profile is None:
            profile = StudentProfile(user_id=user.id, **values)
            self.repository.add(profile)
        else:
            self._check_expected_version(profile, payload.expected_version)
            for key, value in values.items():
                setattr(profile, key, value)
            profile.version += 1

        self.repository.session.commit()
        self.repository.session.refresh(profile)
        return self.to_response(profile)

    def patch_my_profile(
        self, user: User, payload: StudentProfilePatch
    ) -> StudentProfileResponse:
        profile = self.repository.get_by_user_id(user.id)
        if profile is None:
            values = payload.update_values()
            profile = StudentProfile(user_id=user.id, **values)
            self.repository.add(profile)
        else:
            self._check_expected_version(profile, payload.expected_version)
            for key, value in payload.update_values().items():
                setattr(profile, key, value)
            profile.version += 1

        self.repository.session.commit()
        self.repository.session.refresh(profile)
        return self.to_response(profile)

    def to_response(self, profile: StudentProfile) -> StudentProfileResponse:
        missing = self._missing_recommended_fields(profile)
        recommended_count = len(RECOMMENDED_FIELDS) + 1
        if profile.cgpa is not None:
            recommended_count += 1
        completed = max(0, recommended_count - len(missing))
        completeness = round((completed / recommended_count) * 100)
        data = {
            field: getattr(profile, field)
            for field in StudentProfileUpsert.model_fields
            if field != "expected_version"
        }
        return StudentProfileResponse(
            **data,
            id=profile.id,
            user_id=profile.user_id,
            profile_completeness=completeness,
            missing_recommended_fields=missing,
            completeness_context=self._completeness_context(profile),
            version=profile.version,
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
        if profile.cgpa is None and profile.percentage is None:
            missing.append("cgpa_or_percentage")
        elif profile.cgpa is not None and profile.grading_scale is None:
            missing.append("grading_scale")
        return missing

    @staticmethod
    def _completeness_context(profile: StudentProfile) -> str:
        if profile.target_degree_level:
            return f"{profile.target_degree_level.value}_profile"
        return "general_scholarship_profile"

    @staticmethod
    def _check_expected_version(profile: StudentProfile, expected_version: int | None) -> None:
        if expected_version is None:
            raise ConflictError(
                "profile_version_required",
                "Profile updates require expected_version to prevent overwriting newer edits",
            )
        if expected_version != profile.version:
            raise ConflictError(
                "profile_version_conflict",
                "This profile was updated elsewhere; refresh and try again",
            )
