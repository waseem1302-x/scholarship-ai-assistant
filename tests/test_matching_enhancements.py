"""Comprehensive test suite for enhanced taxonomy, country/demonym, and GPA matching modules."""

from __future__ import annotations

from decimal import Decimal

from app.modules.matching.countries import (
    match_nationality_or_country,
    resolve_canonical_country,
)
from app.modules.matching.grading import (
    compare_gpa_cross_scale,
    normalize_to_percentage,
)
from app.modules.matching.taxonomy import (
    get_field_cluster,
    match_fields_of_study,
)
from app.modules.opportunities.models import EligibilityOperator


class TestAcademicTaxonomy:
    """Test suite for hierarchical academic discipline taxonomy matching."""

    def test_direct_exact_match(self) -> None:
        result = match_fields_of_study(["Computer Science"], ["Computer Science"])
        assert result.matched is True
        assert result.score == 1.0
        assert "Direct match" in result.explanation

    def test_cluster_sibling_match_ai_to_cs(self) -> None:
        result = match_fields_of_study(
            ["Machine Learning"], ["Computer Science", "Information Technology"]
        )
        assert result.matched is True
        assert result.score == 0.85
        assert result.cluster_name == "Computer Science & Information Technology"
        assert "Academic cluster match" in result.explanation

    def test_cluster_sibling_data_science_to_cybersecurity(self) -> None:
        result = match_fields_of_study(["Data Science"], ["Cybersecurity"])
        assert result.matched is True
        assert result.score == 0.85
        assert "Computer Science" in (result.cluster_name or "")

    def test_universal_any_fields_match(self) -> None:
        result = match_fields_of_study(["Mechanical Engineering"], ["All fields", "Open"])
        assert result.matched is True
        assert result.score == 1.0
        assert "Open to all" in result.explanation

    def test_unrelated_fields_do_not_match(self) -> None:
        result = match_fields_of_study(
            ["Fine Arts"], ["Computer Science", "Electrical Engineering"]
        )
        assert result.matched is False
        assert result.score == 0.0

    def test_empty_or_none_fields(self) -> None:
        result = match_fields_of_study([], ["Computer Science"])
        assert result.matched is False
        assert result.score == 0.0

    def test_get_field_cluster_lookup(self) -> None:
        cluster = get_field_cluster("Biomedical Engineering")
        assert cluster is not None
        assert cluster[1] == "engineering_technology"


class TestCountryAndDemonymResolver:
    """Test suite for country code, demonym, and international eligibility resolution."""

    def test_resolve_canonical_country_demonym(self) -> None:
        res = resolve_canonical_country("Pakistani")
        assert res is not None
        assert res[0] == "PK"
        assert res[1] == "Pakistan"

    def test_resolve_canonical_country_iso2(self) -> None:
        res = resolve_canonical_country("DE")
        assert res is not None
        assert res[0] == "DE"
        assert res[1] == "Germany"

    def test_match_nationality_demonym_to_country_name(self) -> None:
        assert (
            match_nationality_or_country("Pakistani", ["Pakistan", "India", "Bangladesh"]) is True
        )

    def test_match_nationality_iso2_to_full_name(self) -> None:
        assert match_nationality_or_country("PK", ["Pakistan"]) is True
        assert match_nationality_or_country("Pakistan", ["PK", "IN", "BD"]) is True

    def test_match_nationality_all_international(self) -> None:
        assert match_nationality_or_country("German", ["International", "All countries"]) is True

    def test_match_nationality_exclusion_list(self) -> None:
        # If opportunity excludes US citizens:
        assert match_nationality_or_country("US", ["United States"], is_exclusion=True) is False
        assert (
            match_nationality_or_country("Pakistani", ["United States"], is_exclusion=True) is True
        )


class TestGradingAndGPACalculations:
    """Test suite for cross-scale GPA and percentage calculations."""

    def test_normalize_4_scale_to_percentage(self) -> None:
        pct = normalize_to_percentage("3.8", "4.0")
        assert pct == Decimal("95.00")

    def test_normalize_5_scale_to_percentage(self) -> None:
        pct = normalize_to_percentage("4.5", "5.0")
        assert pct == Decimal("90.00")

    def test_normalize_10_scale_to_percentage(self) -> None:
        pct = normalize_to_percentage("8.5", "10.0")
        assert pct == Decimal("85.00")

    def test_compare_gpa_same_scale_gte(self) -> None:
        satisfied, msg = compare_gpa_cross_scale(
            Decimal("3.5"),
            Decimal("4.0"),
            Decimal("3.0"),
            Decimal("4.0"),
            EligibilityOperator.GTE,
        )
        assert satisfied is True
        assert "satisfies" in msg

    def test_compare_gpa_cross_scale_4_to_100_percent(self) -> None:
        # 3.6 / 4.0 is 90%, which satisfies >= 80%
        satisfied, msg = compare_gpa_cross_scale(
            Decimal("3.6"),
            Decimal("4.0"),
            Decimal("80.0"),
            Decimal("100.0"),
            EligibilityOperator.GTE,
        )
        assert satisfied is True
        assert "satisfies" in msg

    def test_compare_gpa_cross_scale_fails_when_below(self) -> None:
        # 2.8 / 4.0 is 70%, which does NOT satisfy >= 85%
        satisfied, msg = compare_gpa_cross_scale(
            Decimal("2.8"),
            Decimal("4.0"),
            Decimal("85.0"),
            Decimal("100.0"),
            EligibilityOperator.GTE,
        )
        assert satisfied is False
        assert "does not satisfy" in msg
