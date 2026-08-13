import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

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

PROFILE_TEXT_LIMIT = 2_000
PROFILE_LIST_LIMIT = 20
PROFILE_LIST_ITEM_LIMIT = 500
COUNTRY_ALIASES = {
    "canada": "CA",
    "ca": "CA",
    "germany": "DE",
    "de": "DE",
    "malaysia": "MY",
    "my": "MY",
    "pakistan": "PK",
    "pakistani": "PK",
    "pk": "PK",
    "islamic republic of pakistan": "PK",
    "united kingdom": "GB",
    "uk": "GB",
    "gb": "GB",
    "united states": "US",
    "usa": "US",
    "us": "US",
}
FIELD_ALIASES = {
    "ai": "computer-science",
    "artificial intelligence": "computer-science",
    "computer science": "computer-science",
    "computing": "computer-science",
    "cs": "computer-science",
    "software engineering": "computer-science",
    "history": "humanities",
    "humanities": "humanities",
    "medicine": "medicine",
    "public health": "medicine",
}


def canonical_country_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return COUNTRY_ALIASES.get(normalized)


def canonical_field_taxonomy(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold().replace("&", "and")
    return FIELD_ALIASES.get(normalized)


class StudentProfileUpsert(BaseModel):
    nationality: str | None = Field(default=None, min_length=2, max_length=100)
    nationality_code: str | None = Field(default=None, min_length=2, max_length=2)
    country_of_residence: str | None = Field(default=None, min_length=2, max_length=100)
    country_of_residence_code: str | None = Field(default=None, min_length=2, max_length=2)
    current_education_level: EducationLevel | None = None
    target_degree_level: TargetDegreeLevel | None = None
    intended_field: str | None = Field(default=None, min_length=2, max_length=255)
    intended_field_taxonomy: str | None = Field(default=None, min_length=2, max_length=120)
    intended_field_detail: str | None = Field(default=None, min_length=2, max_length=255)
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
    research_experience: str | None = Field(default=None, max_length=PROFILE_TEXT_LIMIT)
    publications: list[str] = Field(default_factory=list, max_length=PROFILE_LIST_LIMIT)
    leadership_experience: str | None = Field(default=None, max_length=PROFILE_TEXT_LIMIT)
    financial_need: str | None = Field(default=None, max_length=PROFILE_TEXT_LIMIT)
    preferred_destination_countries: list[str] = Field(
        default_factory=list, max_length=PROFILE_LIST_LIMIT
    )
    preferred_destination_country_codes: list[str] = Field(
        default_factory=list, max_length=PROFILE_LIST_LIMIT
    )
    preferred_study_mode: StudyMode | None = None
    target_intake: str | None = Field(default=None, max_length=100)
    target_intake_year: int | None = Field(default=None, ge=2000, le=2100)
    application_constraints: str | None = Field(default=None, max_length=PROFILE_TEXT_LIMIT)
    additional_eligibility_information: str | None = Field(
        default=None, max_length=PROFILE_TEXT_LIMIT
    )
    expected_version: int | None = Field(default=None, ge=1, exclude=True)

    @field_validator(
        "nationality",
        "nationality_code",
        "country_of_residence",
        "country_of_residence_code",
        "intended_field",
        "intended_field_taxonomy",
        "intended_field_detail",
        "academic_discipline",
        "target_intake",
        "research_experience",
        "leadership_experience",
        "financial_need",
        "application_constraints",
        "additional_eligibility_information",
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
    def clean_lists(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > PROFILE_LIST_ITEM_LIMIT for value in cleaned):
            raise ValueError("Profile list items must not exceed 500 characters")
        return cleaned

    @field_validator("nationality_code", "country_of_residence_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @field_validator("preferred_destination_country_codes", mode="before")
    @classmethod
    def clean_country_codes(cls, values: list[str] | None) -> list[str]:
        if values is None:
            return []
        cleaned = [value.strip().upper() for value in values if value.strip()]
        if any(len(value) != 2 for value in cleaned):
            raise ValueError("Country codes must be ISO 3166-1 alpha-2 codes")
        return cleaned

    @model_validator(mode="after")
    def validate_grade_and_tests(self) -> "StudentProfileUpsert":
        if self.nationality and self.nationality_code is None:
            self.nationality_code = canonical_country_code(self.nationality)
        if self.country_of_residence and self.country_of_residence_code is None:
            self.country_of_residence_code = canonical_country_code(self.country_of_residence)
        if self.preferred_destination_countries and not self.preferred_destination_country_codes:
            self.preferred_destination_country_codes = [
                code
                for code in (
                    canonical_country_code(country)
                    for country in self.preferred_destination_countries
                )
                if code
            ]
        if self.intended_field and self.intended_field_taxonomy is None:
            self.intended_field_taxonomy = canonical_field_taxonomy(self.intended_field)
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


class StudentProfilePatch(StudentProfileUpsert):
    nationality: str | None = Field(default=None, min_length=2, max_length=100)
    english_test_status: TestStatus | None = None
    gre_status: TestStatus | None = None
    publications: list[str] | None = Field(default=None, max_length=PROFILE_LIST_LIMIT)
    preferred_destination_countries: list[str] | None = Field(
        default=None, max_length=PROFILE_LIST_LIMIT
    )
    preferred_destination_country_codes: list[str] | None = Field(
        default=None, max_length=PROFILE_LIST_LIMIT
    )

    def update_values(self) -> dict[str, Any]:
        values = self.model_dump(exclude_unset=True, exclude={"expected_version"})
        if (
            "nationality" in self.model_fields_set
            and "nationality_code" not in self.model_fields_set
        ):
            values["nationality_code"] = self.nationality_code
        if (
            "country_of_residence" in self.model_fields_set
            and "country_of_residence_code" not in self.model_fields_set
        ):
            values["country_of_residence_code"] = self.country_of_residence_code
        if (
            "intended_field" in self.model_fields_set
            and "intended_field_taxonomy" not in self.model_fields_set
        ):
            values["intended_field_taxonomy"] = self.intended_field_taxonomy
        if (
            "preferred_destination_countries" in self.model_fields_set
            and "preferred_destination_country_codes" not in self.model_fields_set
        ):
            values["preferred_destination_country_codes"] = (
                self.preferred_destination_country_codes or []
            )
        return values


class StudentProfileResponse(StudentProfileUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    profile_completeness: int
    missing_recommended_fields: list[str]
    completeness_context: str
    version: int
    created_at: datetime
    updated_at: datetime
