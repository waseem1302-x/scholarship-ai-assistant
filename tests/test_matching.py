import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.auth.models import User, UserRole
from app.modules.matching.models import MatchEvaluation, MatchEvaluationResult
from app.modules.matching.repository import MatchEvaluationRepository
from app.modules.matching.service import _compare
from app.modules.opportunities.models import (
    EligibilityOperator,
    EligibilityRule,
    EligibilityRuleType,
    Opportunity,
)

PASSWORD = "MatchingPassword123"


def create_user(db_session: Session, *, email: str, role: UserRole) -> None:
    db_session.add(
        User(
            id=uuid.uuid4(),
            email=email,
            password_hash=hash_password(PASSWORD),
            role=role,
            is_active=True,
        )
    )
    db_session.commit()


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def profile_payload(**overrides: object) -> dict:
    payload = {
        "nationality": "Pakistani",
        "country_of_residence": "Malaysia",
        "current_education_level": "bachelors",
        "target_degree_level": "masters",
        "intended_field": "Artificial Intelligence",
        "academic_discipline": "Computer Science",
        "cgpa": "3.70",
        "grading_scale": "4.00",
        "english_test_status": "taken",
        "ielts_score": "7.0",
        "gre_status": "planned",
        "financial_need": "Needs tuition and living support",
        "preferred_destination_countries": ["Malaysia", "Canada"],
        "preferred_study_mode": "on_campus",
        "target_intake": "Fall 2027",
    }
    payload.update(overrides)
    return payload


def opportunity_payload(**overrides: object) -> dict:
    payload = {
        "name": "Malaysia AI Graduate Scholarship",
        "provider_name": "Verified Scholarship Provider",
        "country": "Malaysia",
        "degree_level": "masters",
        "field_eligibility": "Artificial Intelligence, Computer Science, and related disciplines",
        "nationality_eligibility": "Pakistani and international applicants",
        "application_deadline": "2027-05-30T23:59:59Z",
        "intake_year": 2027,
        "funding_type": "full",
        "funding_policy": (
            "The official award policy confirms tuition, living stipend, accommodation, travel, "
            "insurance, and mandatory fee coverage for the full study period."
        ),
        "tuition_coverage_status": "confirmed",
        "stipend_coverage_status": "confirmed",
        "accommodation_coverage_status": "confirmed",
        "travel_coverage_status": "confirmed",
        "insurance_coverage_status": "confirmed",
        "fees_coverage_status": "confirmed",
        "tuition_coverage": "Full tuition coverage stated by the official source",
        "monthly_stipend_amount": "1500.00",
        "monthly_stipend_currency": "MYR",
        "english_language_requirement": "IELTS or TOEFL required unless waived",
        "minimum_academic_requirement": "Minimum CGPA 3.0 on a 4.0 scale",
        "required_documents": ["Transcript", "Passport"],
        "application_url": "https://example.edu/apply",
        "status": "draft",
        "data_confidence": "medium",
        "source": {
            "url": "https://example.edu/scholarships/ai",
            "source_type": "official",
            "title": "Official AI scholarship page",
            "relevant_excerpt": (
                "Official source lists deadline, eligible fields, nationality rules, "
                "English requirements, and funding coverage."
            ),
            "verification_status": "needs_review",
        },
    }
    payload.update(overrides)
    return payload


def create_verified_opportunity(
    client: TestClient, admin_headers: dict[str, str], **overrides: object
) -> dict:
    created = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(**overrides),
        headers=admin_headers,
    )
    assert created.status_code == 201
    created_body = created.json()
    published = client.post(
        f"/api/v1/admin/opportunities/{created_body['id']}/review-actions",
        json={
            "action": "publish",
            "source_id": created_body["sources"][0]["id"],
            "notes": "Official source checked and record reviewed for publication.",
        },
        headers=admin_headers,
    )
    assert published.status_code == 200
    return published.json()


def test_matching_requires_profile(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="student-no-profile@example.com", role=UserRole.STUDENT)
    token = login(client, "student-no-profile@example.com")

    response = client.get("/api/v1/matches/me", headers=headers(token))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "profile_required"


def test_matching_ranks_verified_opportunities_and_explains_fit(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-match@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-match@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-match@example.com"))
    student_headers = headers(login(client, "student-match@example.com"))
    profile = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(),
        headers=student_headers,
    )
    assert profile.status_code == 200

    strong = create_verified_opportunity(
        client,
        admin_headers,
        eligibility_rules=[
            {"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]},
            {"rule_type": "field", "operator": "in", "value": ["Artificial Intelligence"]},
            {"rule_type": "cgpa", "operator": "gte", "value": 3.0, "grading_scale": 4.0},
            {"rule_type": "ielts", "operator": "gte", "value": 6.5},
        ],
    )
    create_verified_opportunity(
        client,
        admin_headers,
        name="PhD History Scholarship",
        country="Germany",
        degree_level="phd",
        field_eligibility="History and cultural studies",
        nationality_eligibility="German citizens",
        funding_type="partial",
        tuition_coverage="Partial tuition support",
        monthly_stipend_amount=None,
        monthly_stipend_currency=None,
        english_language_requirement="German-language proof required",
        minimum_academic_requirement="Minimum CGPA 3.9 on a 4.0 scale",
        source={
            **opportunity_payload()["source"],
            "url": "https://example.edu/scholarships/history",
            "title": "Official history scholarship page",
        },
    )

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["opportunity"]["id"] for item in results] == [strong["id"]]
    assert results[0]["score_label"] == "strong_match"
    assert results[0]["eligibility_status"] == "potentially_eligible"
    assert results[0]["profile_completeness"] >= 80
    assert results[0]["preference_fit"] is not None
    assert "not a probability" in results[0]["disclaimer"]
    assert any(
        "Nationality requirement is satisfied" in item
        for item in results[0]["explanation"]["satisfied"]
    )


def test_structured_rule_scores_are_normalized_regardless_of_rule_count(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-normalized@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-normalized@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-normalized@example.com"))
    student_headers = headers(login(client, "student-normalized@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me", json=profile_payload(), headers=student_headers
        ).status_code
        == 200
    )

    one_rule = create_verified_opportunity(
        client,
        admin_headers,
        name="One structured rule scholarship",
        eligibility_rules=[{"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]}],
    )
    four_rules = create_verified_opportunity(
        client,
        admin_headers,
        name="Four structured rules scholarship",
        eligibility_rules=[
            {"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]},
            {"rule_type": "field", "operator": "in", "value": ["Artificial Intelligence"]},
            {"rule_type": "cgpa", "operator": "gte", "value": 3.0, "grading_scale": 4.0},
            {"rule_type": "ielts", "operator": "gte", "value": 6.5},
        ],
    )

    results = client.get("/api/v1/matches/me", headers=student_headers).json()["results"]
    scores = {item["opportunity"]["id"]: item["fit_score"] for item in results}

    assert scores[one_rule["id"]] == scores[four_rules["id"]]


def test_matching_hides_unverified_opportunities(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="admin-unverified@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-unverified@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-unverified@example.com"))
    student_headers = headers(login(client, "student-unverified@example.com"))
    profile_response = client.put(
        "/api/v1/profiles/me", json=profile_payload(), headers=student_headers
    )
    assert profile_response.status_code == 200
    unverified = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(name="Unverified Scholarship"),
        headers=admin_headers,
    )
    assert unverified.status_code == 201

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_matching_surfaces_uncertainty_for_missing_profile_fields(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-uncertain@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-uncertain@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-uncertain@example.com"))
    student_headers = headers(login(client, "student-uncertain@example.com"))
    create_verified_opportunity(client, admin_headers)
    profile = client.put(
        "/api/v1/profiles/me",
        json=profile_payload(
            nationality=None,
            intended_field=None,
            academic_discipline=None,
            cgpa=None,
            grading_scale=None,
            preferred_destination_countries=[],
        ),
        headers=student_headers,
    )
    assert profile.status_code == 200

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    uncertain = response.json()["results"][0]["explanation"]["uncertain"]
    assert any("nationality" in item.lower() for item in uncertain)
    assert any("field" in item.lower() for item in uncertain)
    assert any("academic" in item.lower() for item in uncertain)


def test_structured_hard_exclusion_never_receives_a_strong_match(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-hard-rule@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-hard-rule@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-hard-rule@example.com"))
    student_headers = headers(login(client, "student-hard-rule@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me", json=profile_payload(), headers=student_headers
        ).status_code
        == 200
    )
    create_verified_opportunity(
        client,
        admin_headers,
        name="Excluded nationality scholarship",
        eligibility_rules=[
            {"rule_type": "nationality", "operator": "not_in", "value": ["Pakistani"]},
            {"rule_type": "target_degree", "operator": "equals", "value": "masters"},
            {"rule_type": "cgpa", "operator": "gte", "value": 3.2, "grading_scale": 4.0},
            {"rule_type": "ielts", "operator": "gte", "value": 6.5},
        ],
    )

    result = client.get("/api/v1/matches/me", headers=student_headers).json()["results"][0]

    assert result["eligibility_status"] == "ineligible"
    assert result["fit_score"] is None
    assert result["score_label"] == "not_eligible"
    assert result["matcher_version"] == "2026-08-14.separated-fit-confidence.v1"


def test_matching_persists_reproducible_evaluation_history(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-evaluation@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-evaluation@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-evaluation@example.com"))
    student_headers = headers(login(client, "student-evaluation@example.com"))
    profile_response = client.put(
        "/api/v1/profiles/me", json=profile_payload(), headers=student_headers
    )
    assert profile_response.status_code == 200
    opportunity = create_verified_opportunity(
        client,
        admin_headers,
        application_cycles=[
            {
                "intake_year": 2027,
                "application_opening_date": "2027-01-01T00:00:00Z",
                "application_deadline": "2027-05-30T23:59:59Z",
            }
        ],
    )

    first_response = client.get("/api/v1/matches/me", headers=student_headers)

    assert first_response.status_code == 200
    first_evaluation_id = first_response.json()["evaluation_id"]
    first = db_session.get(MatchEvaluation, uuid.UUID(first_evaluation_id))
    assert first is not None
    assert first.matcher_version == "2026-08-14.separated-fit-confidence.v1"
    assert len(first.profile_snapshot_hash) == 64
    assert first.profile_snapshot_json["identity"]["nationality"] == "Pakistani"
    assert first.expires_at > first.evaluated_at

    stored_result = db_session.scalar(
        select(MatchEvaluationResult).where(MatchEvaluationResult.evaluation_id == first.id)
    )
    assert stored_result is not None
    assert str(stored_result.opportunity_id) == opportunity["id"]
    assert stored_result.opportunity_cycle_id is not None
    assert stored_result.source_id is not None
    assert stored_result.source_snapshot_json is not None
    assert stored_result.source_snapshot_json["source_id"] == str(stored_result.source_id)
    assert len(stored_result.rule_outcomes) == 8
    assert all(item.reason_code.startswith("match.") for item in stored_result.rule_outcomes)

    assert (
        client.put(
            "/api/v1/profiles/me",
            json=profile_payload(
                ielts_score="7.5",
                expected_version=profile_response.json()["version"],
            ),
            headers=student_headers,
        ).status_code
        == 200
    )
    second_response = client.get("/api/v1/matches/me", headers=student_headers)
    second = db_session.get(MatchEvaluation, uuid.UUID(second_response.json()["evaluation_id"]))

    assert second is not None
    assert second.supersedes_evaluation_id == first.id
    assert second.profile_snapshot_hash != first.profile_snapshot_hash

    second.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    removed = MatchEvaluationRepository(db_session).purge_expired(before=datetime.now(UTC))
    db_session.commit()

    assert removed == 1
    assert db_session.get(MatchEvaluation, second.id) is None


def test_structured_rules_cover_all_profile_backed_categories_and_operators(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-complete-rules@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-complete-rules@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-complete-rules@example.com"))
    student_headers = headers(login(client, "student-complete-rules@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me",
            json=profile_payload(
                percentage="85",
                toefl_score=105,
                duolingo_score=130,
                gre_status="taken",
                gre_score=320,
                work_experience_months=12,
                preferred_study_mode="online",
                target_intake_year=2027,
            ),
            headers=student_headers,
        ).status_code
        == 200
    )
    created = create_verified_opportunity(
        client,
        admin_headers,
        eligibility_rules=[
            {"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]},
            {"rule_type": "residence", "operator": "equals", "value": "Malaysia"},
            {"rule_type": "target_degree", "operator": "equals", "value": "masters"},
            {"rule_type": "field", "operator": "in", "value": ["Artificial Intelligence"]},
            {"rule_type": "cgpa", "operator": "gte", "value": 3.5, "grading_scale": 4.0},
            {"rule_type": "percentage", "operator": "gte", "value": 80},
            {"rule_type": "ielts", "operator": "gte", "value": 6.5},
            {"rule_type": "toefl", "operator": "lte", "value": 110},
            {"rule_type": "duolingo", "operator": "gte", "value": 120},
            {"rule_type": "gre", "operator": "gte", "value": 310},
            {"rule_type": "work_experience_months", "operator": "lte", "value": 24},
            {"rule_type": "study_mode", "operator": "equals", "value": "online"},
            {"rule_type": "intake_year", "operator": "equals", "value": "2027"},
            {"rule_type": "current_education_level", "operator": "equals", "value": "bachelors"},
            {"rule_type": "english_test_status", "operator": "equals", "value": "taken"},
            {"rule_type": "gre_status", "operator": "equals", "value": "taken"},
            {"rule_type": "application_window", "operator": "in", "value": ["open", "rolling"]},
        ],
    )

    response = client.get("/api/v1/matches/me", headers=student_headers)

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["opportunity"]["id"] == created["id"]
    assert result["failed_criteria"] == []
    assert result["unknown_criteria"] == []
    assert result["eligibility_status"] == "potentially_eligible"
    assert all(
        rule["source_id"] == created["sources"][0]["id"] for rule in created["eligibility_rules"]
    )
    assert all(rule["source_excerpt_id"] is not None for rule in created["eligibility_rules"])


def test_missing_or_waived_structured_test_evidence_stays_unknown(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-unknown-rule@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-unknown-rule@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-unknown-rule@example.com"))
    student_headers = headers(login(client, "student-unknown-rule@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me",
            json=profile_payload(english_test_status="not_required", ielts_score=None),
            headers=student_headers,
        ).status_code
        == 200
    )
    create_verified_opportunity(
        client,
        admin_headers,
        eligibility_rules=[
            {"rule_type": "english_test_status", "operator": "equals", "value": "taken"}
        ],
    )

    result = client.get("/api/v1/matches/me", headers=student_headers).json()["results"][0]

    assert result["eligibility_status"] == "likely_eligible"
    assert result["fit_score"] == 0
    assert result["failed_criteria"] == []
    assert result["eligibility_failures"] == []
    assert result["missing_information"] == result["unknown_criteria"]
    assert any("waiver" in item.lower() for item in result["unknown_criteria"])


def test_preference_mismatches_are_separate_from_eligibility_failures(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-preference@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-preference@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-preference@example.com"))
    student_headers = headers(login(client, "student-preference@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me",
            json=profile_payload(preferred_destination_countries=["Malaysia"]),
            headers=student_headers,
        ).status_code
        == 200
    )
    created = create_verified_opportunity(
        client,
        admin_headers,
        name="Canada AI Scholarship",
        country="Canada",
        eligibility_rules=[
            {"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]},
            {"rule_type": "target_degree", "operator": "equals", "value": "masters"},
            {"rule_type": "field", "operator": "in", "value": ["Artificial Intelligence"]},
        ],
    )

    result = client.get("/api/v1/matches/me", headers=student_headers).json()["results"][0]

    assert result["opportunity"]["id"] == created["id"]
    assert result["fit_score"] == 100
    assert result["failed_criteria"] == []
    assert result["eligibility_failures"] == []
    assert result["preference_fit"] < 100
    assert any("preferred destination" in item for item in result["preference_mismatches"])


def test_incompatible_gpa_scales_are_uncertain_not_converted(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-gpa-scale@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-gpa-scale@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-gpa-scale@example.com"))
    student_headers = headers(login(client, "student-gpa-scale@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me",
            json=profile_payload(cgpa="9.00", grading_scale="10.00"),
            headers=student_headers,
        ).status_code
        == 200
    )
    create_verified_opportunity(
        client,
        admin_headers,
        eligibility_rules=[
            {"rule_type": "cgpa", "operator": "gte", "value": 3.0, "grading_scale": 4.0}
        ],
    )

    result = client.get("/api/v1/matches/me", headers=student_headers).json()["results"][0]

    assert result["fit_score"] == 0
    assert result["failed_criteria"] == []
    assert any("CGPA scales differ" in item for item in result["missing_information"])
    assert any("Missing profile or source data" in item for item in result["confidence_factors"])


def test_unstructured_eligibility_is_admin_visible_and_never_a_hard_failure(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-unstructured@example.com", role=UserRole.ADMIN)
    create_user(db_session, email="student-unstructured@example.com", role=UserRole.STUDENT)
    admin_headers = headers(login(client, "admin-unstructured@example.com"))
    student_headers = headers(login(client, "student-unstructured@example.com"))
    assert (
        client.put(
            "/api/v1/profiles/me", json=profile_payload(), headers=student_headers
        ).status_code
        == 200
    )
    created = create_verified_opportunity(
        client,
        admin_headers,
        nationality_eligibility="German citizens only",
        field_eligibility="History only",
    )

    result = client.get("/api/v1/matches/me", headers=student_headers).json()["results"][0]
    quality = client.get("/api/v1/admin/data-quality-issues", headers=admin_headers).json()

    assert result["eligibility_status"] != "ineligible"
    assert result["fit_score"] is not None
    codes = {item["code"] for item in quality["items"] if item["opportunity_id"] == created["id"]}
    assert "unstructured_eligibility_nationality_eligibility" in codes
    assert "unstructured_eligibility_field_eligibility" in codes
    assert "structured_eligibility_missing" in codes


def test_admin_rules_require_official_source_evidence(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-rule-evidence@example.com", role=UserRole.ADMIN)
    admin_headers = headers(login(client, "admin-rule-evidence@example.com"))

    response = client.post(
        "/api/v1/admin/opportunities",
        json=opportunity_payload(
            eligibility_rules=[
                {"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]}
            ],
            source={
                **opportunity_payload()["source"],
                "source_type": "university",
                "url": "https://example.edu/non-official-rule-source",
            },
        ),
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "eligibility_rule_official_source_required"


@pytest.mark.parametrize(
    ("actual", "required", "operator", "expected"),
    [
        ("Pakistan", "Pakistan", EligibilityOperator.EQUALS, True),
        ("Pakistan", ["Malaysia", "Pakistan"], EligibilityOperator.IN, True),
        ("Pakistan", ["Pakistan"], EligibilityOperator.NOT_IN, False),
        (3.5, 3.0, EligibilityOperator.GTE, True),
        (3.5, 3.0, EligibilityOperator.LTE, False),
        (
            ["Artificial Intelligence", "Computer Science"],
            ["Computer Science"],
            EligibilityOperator.IN,
            True,
        ),
    ],
)
def test_structured_operator_matrix(
    actual: str | float | list[str],
    required: str | float | list[str],
    operator: EligibilityOperator,
    expected: bool,
) -> None:
    assert _compare(actual, required, operator) is expected


def test_admin_quality_flags_legacy_rule_without_official_excerpt(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="admin-legacy-rule@example.com", role=UserRole.ADMIN)
    admin_headers = headers(login(client, "admin-legacy-rule@example.com"))
    created = create_verified_opportunity(
        client,
        admin_headers,
        eligibility_rules=[{"rule_type": "nationality", "operator": "in", "value": ["Pakistani"]}],
    )
    opportunity = db_session.get(Opportunity, uuid.UUID(created["id"]))
    assert opportunity is not None
    db_session.add(
        EligibilityRule(
            opportunity_id=opportunity.id,
            rule_type=EligibilityRuleType.FIELD,
            operator=EligibilityOperator.IN,
            value_json=["Computer Science"],
            required=True,
            source_id=None,
            source_excerpt_id=None,
        )
    )
    db_session.commit()

    quality = client.get("/api/v1/admin/data-quality-issues", headers=admin_headers).json()
    codes = {item["code"] for item in quality["items"] if item["opportunity_id"] == created["id"]}

    assert "eligibility_rule_evidence_missing" in codes
