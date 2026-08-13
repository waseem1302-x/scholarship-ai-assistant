import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.auth.models import User, enum_values, utc_now


class EducationLevel(StrEnum):
    HIGH_SCHOOL = "high_school"
    DIPLOMA = "diploma"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    OTHER = "other"


class TargetDegreeLevel(StrEnum):
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    SHORT_COURSE = "short_course"
    OTHER = "other"


class TestStatus(StrEnum):
    NOT_TAKEN = "not_taken"
    PLANNED = "planned"
    TAKEN = "taken"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


class StudyMode(StrEnum):
    ON_CAMPUS = "on_campus"
    ONLINE = "online"
    HYBRID = "hybrid"
    ANY = "any"


class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint("cgpa IS NULL OR cgpa >= 0", name="ck_profiles_cgpa_non_negative"),
        CheckConstraint(
            "grading_scale IS NULL OR grading_scale > 0",
            name="ck_profiles_grading_scale_positive",
        ),
        CheckConstraint(
            "cgpa IS NULL OR grading_scale IS NULL OR cgpa <= grading_scale",
            name="ck_profiles_cgpa_within_scale",
        ),
        CheckConstraint(
            "percentage IS NULL OR percentage BETWEEN 0 AND 100",
            name="ck_profiles_percentage_range",
        ),
        CheckConstraint(
            "ielts_score IS NULL OR ielts_score BETWEEN 0 AND 9",
            name="ck_profiles_ielts_range",
        ),
        CheckConstraint(
            "toefl_score IS NULL OR toefl_score BETWEEN 0 AND 120",
            name="ck_profiles_toefl_range",
        ),
        CheckConstraint(
            "duolingo_score IS NULL OR duolingo_score BETWEEN 10 AND 160",
            name="ck_profiles_duolingo_range",
        ),
        CheckConstraint(
            "gre_score IS NULL OR gre_score BETWEEN 260 AND 340",
            name="ck_profiles_gre_range",
        ),
        CheckConstraint(
            "work_experience_months IS NULL OR work_experience_months >= 0",
            name="ck_profiles_work_experience_non_negative",
        ),
        CheckConstraint(
            "target_intake_year IS NULL OR target_intake_year BETWEEN 2000 AND 2100",
            name="ck_profiles_target_intake_year_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    nationality: Mapped[str | None] = mapped_column(String(100))
    nationality_code: Mapped[str | None] = mapped_column(String(2), index=True)
    country_of_residence: Mapped[str | None] = mapped_column(String(100))
    country_of_residence_code: Mapped[str | None] = mapped_column(String(2), index=True)
    current_education_level: Mapped[EducationLevel | None] = mapped_column(
        Enum(
            EducationLevel,
            name="education_level",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    target_degree_level: Mapped[TargetDegreeLevel | None] = mapped_column(
        Enum(
            TargetDegreeLevel,
            name="target_degree_level",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        index=True,
    )
    intended_field: Mapped[str | None] = mapped_column(String(255))
    intended_field_taxonomy: Mapped[str | None] = mapped_column(String(120), index=True)
    intended_field_detail: Mapped[str | None] = mapped_column(String(255))
    academic_discipline: Mapped[str | None] = mapped_column(String(255))
    cgpa: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    grading_scale: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    english_test_status: Mapped[TestStatus] = mapped_column(
        Enum(
            TestStatus,
            name="test_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=TestStatus.UNKNOWN,
    )
    ielts_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    toefl_score: Mapped[int | None]
    duolingo_score: Mapped[int | None]
    gre_status: Mapped[TestStatus] = mapped_column(
        Enum(
            TestStatus,
            name="gre_status",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        ),
        default=TestStatus.UNKNOWN,
    )
    gre_score: Mapped[int | None]
    work_experience_months: Mapped[int | None]
    research_experience: Mapped[str | None] = mapped_column(Text)
    publications: Mapped[list[str]] = mapped_column(JSON, default=list)
    leadership_experience: Mapped[str | None] = mapped_column(Text)
    financial_need: Mapped[str | None] = mapped_column(Text)
    preferred_destination_countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_destination_country_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_study_mode: Mapped[StudyMode | None] = mapped_column(
        Enum(
            StudyMode,
            name="study_mode",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            values_callable=enum_values,
        )
    )
    target_intake: Mapped[str | None] = mapped_column(String(100))
    target_intake_year: Mapped[int | None]
    application_constraints: Mapped[str | None] = mapped_column(Text)
    additional_eligibility_information: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )

    user: Mapped[User] = relationship()
