import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.modules.profiles.models import (
    EducationLevel,
    StudyMode,
    TargetDegreeLevel,
    TestStatus,
)


class StudentProfileUpsert(BaseModel):
    nationality: str | None = Field(default=None, min_length=2, max_length=100)
    country_of_residence: str | None = Field(default=None, min_length=2, max_length=100)
    current_education_level: EducationLevel | None = None
    target_degree_level: TargetDegreeLevel | None = None
    intended_field: str | None = Field(default=None, min_length=2, max_length=255)
    academic_discipline: str | None = Field(default=None, min_length=2, max_length=255)
    cgpa: Decimal | None = Field(default=None, ge=0)
    percentage: Decimal | None = Field(default=None, ge=0, le=100)
    grading_scale: Decimal | None = Field(default=None, gt=0)
    english_test_status: TestStatus = TestStatus.UNKNOWN
    ielts_score: Decimal | None = Field(default=None, ge=0, le=9)
    toefl_score: int | None = Field(default=None, ge=0, le=120)
    duolingo_score: int | None = Field(default=None, ge=10, le=160)
    gre_status: TestStatus = TestStatus.UNKNOWN
    gre_score: int | None = Field(default=None, ge=260, le=340)
    work_experience_months: int | None = Field(default=None, ge=0)
    research_experience: str | None = None
    publications: list[str] = Field(default_factory=list)
    leadership_experience: str | None = None
    financial_need: str | None = None
    preferred_destination_countries: list[str] = Field(default_factory=list)
    preferred_study_mode: StudyMode | None = None
    target_intake: str | None = Field(default=None, max_length=100)
    target_intake_year: int | None = Field(default=None, ge=2000, le=2100)
    application_constraints: str | None = None
    additional_eligibility_information: str | None = None

    @field_validator(
        "nationality",
        "country_of_residence",
        "intended_field",
        "academic_discipline",
        "target_intake",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("publications", "preferred_destination_countries")
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @model_validator(mode="after")
    def validate_grade_and_tests(self) -> "StudentProfileUpsert":
        if self.cgpa is not None and self.grading_scale is None:
            raise ValueError("grading_scale is required when cgpa is provided")
        if (
            self.cgpa is not None
            and self.grading_scale is not None
            and self.cgpa > self.grading_scale
        ):
            raise ValueError("cgpa cannot be greater than grading_scale")
        if self.english_test_status is not TestStatus.TAKEN and any(
            score is not None
            for score in [
                self.ielts_score,
                self.toefl_score,
                self.duolingo_score,
            ]
        ):
            raise ValueError("English test scores require english_test_status='taken'")
        if self.gre_score is not None and self.gre_status is not TestStatus.TAKEN:
            raise ValueError("GRE score requires gre_status='taken'")
        return self


class StudentProfileResponse(StudentProfileUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    profile_completeness: int
    missing_recommended_fields: list[str]
    created_at: datetime
    updated_at: datetime
