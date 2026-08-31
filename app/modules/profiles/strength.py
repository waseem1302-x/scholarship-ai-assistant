"""Profile Strength & Scholarship Unlock Meter."""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.profiles.models import StudentProfile, TestStatus


class UnlockSuggestion(BaseModel):
    field_key: str
    section_name: str
    impact_headline: str
    recommended_action: str
    potential_unlocked_count: int


class ProfileStrengthResponse(BaseModel):
    overall_score: int  # 0 - 100
    strength_tier: str  # "Elite (90-100%)", "Strong (75-89%)", "Moderate (50-74%)", "Basic (<50%)"
    completed_sections_count: int
    total_sections_count: int
    completed_fields: list[str]
    missing_fields: list[str]
    unlock_suggestions: list[UnlockSuggestion]


def evaluate_profile_strength(
    profile: StudentProfile,
) -> ProfileStrengthResponse:
    """Evaluate profile completeness and compute potential scholarship unlock suggestions."""
    total_sections = 6
    completed_sections = 0
    completed_fields: list[str] = []
    missing_fields: list[str] = []
    suggestions: list[UnlockSuggestion] = []

    # 1. Nationality & Demographics
    if profile.nationality or profile.nationality_code:
        completed_sections += 1
        completed_fields.append("Nationality / Citizenship")
    else:
        missing_fields.append("Nationality / Citizenship")
        suggestions.append(
            UnlockSuggestion(
                field_key="nationality",
                section_name="Citizenship & Country of Origin",
                impact_headline="Unlock country-specific bilateral government scholarships",
                recommended_action=(
                    "Select your primary citizenship to verify bilateral quota eligibility."
                ),
                potential_unlocked_count=50,
            )
        )

    # 2. Target Degree
    if profile.target_degree_level:
        completed_sections += 1
        completed_fields.append("Target Degree Level")
    else:
        missing_fields.append("Target Degree Level")
        suggestions.append(
            UnlockSuggestion(
                field_key="target_degree_level",
                section_name="Target Degree Level",
                impact_headline="Filter for Masters, Bachelors, or PhD programs",
                recommended_action="Specify whether you are targeting Masters, PhD, or Undergrad.",
                potential_unlocked_count=100,
            )
        )

    # 3. Academic GPA
    if profile.cgpa and profile.grading_scale:
        completed_sections += 1
        completed_fields.append("Academic GPA / Grade Scale")
    else:
        missing_fields.append("Academic GPA / Grade Scale")
        suggestions.append(
            UnlockSuggestion(
                field_key="cgpa",
                section_name="Academic Grades",
                impact_headline="Verify merit-based minimum cutoff criteria",
                recommended_action=(
                    "Enter your cumulative GPA or percentage to rank fit score against merit "
                    "thresholds."
                ),
                potential_unlocked_count=35,
            )
        )

    # 4. Field of Study
    if profile.intended_field:
        completed_sections += 1
        completed_fields.append("Intended Field of Study")
    else:
        missing_fields.append("Intended Field of Study")
        suggestions.append(
            UnlockSuggestion(
                field_key="intended_field",
                section_name="Academic Discipline",
                impact_headline="Match department and faculty-specific endowments",
                recommended_action=(
                    "Add your major (e.g. Computer Science, Public Policy, Engineering)."
                ),
                potential_unlocked_count=40,
            )
        )

    # 5. English Language Proficiency
    has_english = bool(
        profile.ielts_score
        or profile.toefl_score
        or profile.duolingo_score
        or profile.english_test_status == TestStatus.TAKEN
    )
    if has_english:
        completed_sections += 1
        completed_fields.append("English Language Test Score")
    else:
        missing_fields.append("English Language Test Score")
        suggestions.append(
            UnlockSuggestion(
                field_key="ielts_score",
                section_name="Language Proficiency",
                impact_headline="Unlock 45+ UK, USA, Canada & Australian scholarships",
                recommended_action=(
                    "Add your IELTS (6.5+) or TOEFL (90+) score or indicate English medium waiver."
                ),
                potential_unlocked_count=45,
            )
        )

    # 6. Work / Research Experience
    has_exp = bool(
        (profile.work_experience_months is not None and profile.work_experience_months > 0)
        or profile.research_experience
    )
    if has_exp:
        completed_sections += 1
        completed_fields.append("Work / Research Experience")
    else:
        missing_fields.append("Work / Research Experience")
        suggestions.append(
            UnlockSuggestion(
                field_key="work_experience_months",
                section_name="Professional & Research Background",
                impact_headline="Unlock Chevening, DAAD EPOS & leadership-track awards",
                recommended_action=(
                    "Enter months of professional work, volunteering, or academic publications."
                ),
                potential_unlocked_count=20,
            )
        )

    overall_score = int((completed_sections / total_sections) * 100)
    tier = (
        "Elite (90-100%)"
        if overall_score >= 90
        else (
            "Strong (75-89%)"
            if overall_score >= 70
            else ("Moderate (50-74%)" if overall_score >= 50 else "Basic (<50%)")
        )
    )

    return ProfileStrengthResponse(
        overall_score=overall_score,
        strength_tier=tier,
        completed_sections_count=completed_sections,
        total_sections_count=total_sections,
        completed_fields=completed_fields,
        missing_fields=missing_fields,
        unlock_suggestions=suggestions,
    )
