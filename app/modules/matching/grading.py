"""GPA, percentage, and academic grading scale normalizer for cross-scale comparisons."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.modules.opportunities.models import EligibilityOperator


def to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_to_percentage(
    grade: Decimal | float | str | None,
    scale: Decimal | float | str | None = None,
) -> Decimal | None:
    """Normalize a GPA or grade on any scale to a standard 0-100 percentage."""
    grade_dec = to_decimal(grade)
    scale_dec = to_decimal(scale)
    if grade_dec is None:
        return None

    # If scale is explicitly 100 or grade is already in percentage range with scale 100/None
    if scale_dec is None or scale_dec == Decimal("100"):
        if grade_dec <= Decimal("100"):
            return grade_dec
        return None

    if scale_dec <= Decimal("0"):
        return None

    # Calculate percentage: (grade / scale) * 100
    percentage = (grade_dec / scale_dec) * Decimal("100")
    return percentage.quantize(Decimal("0.01"))


def compare_gpa_cross_scale(
    student_cgpa: Decimal | float | str | None,
    student_scale: Decimal | float | str | None,
    req_cgpa: Decimal | float | str | None,
    req_scale: Decimal | float | str | None,
    operator: EligibilityOperator = EligibilityOperator.GTE,
) -> tuple[bool, str]:
    """Compare student CGPA against scholarship requirements across differing scales.

    Args:
        student_cgpa: Student's GPA or percentage.
        student_scale: Student's grading scale (e.g. 4.0, 5.0, 10.0, 100.0).
        req_cgpa: Required minimum/maximum GPA or percentage.
        req_scale: Required grading scale.
        operator: Comparison operator (GTE, LTE, EQUALS).

    Returns:
        tuple[bool, str]: (is_satisfied, explanatory_message)
    """
    s_grade = to_decimal(student_cgpa)
    s_scale = to_decimal(student_scale) or Decimal("4.0")
    r_grade = to_decimal(req_cgpa)
    r_scale = to_decimal(req_scale)

    if s_grade is None or r_grade is None:
        return False, "Missing CGPA or requirement value"

    # If both scales are identical, do direct comparison
    if r_scale is not None and s_scale == r_scale:
        if operator is EligibilityOperator.GTE:
            satisfied = s_grade >= r_grade
        elif operator is EligibilityOperator.LTE:
            satisfied = s_grade <= r_grade
        else:
            satisfied = s_grade == r_grade
        status = "satisfies" if satisfied else "does not satisfy"
        return (
            satisfied,
            f"CGPA {s_grade}/{s_scale} {status} requirement {operator.value} {r_grade}/{r_scale}",
        )

    # Cross-scale conversion to percentage
    fallback_scale = Decimal("100") if r_grade > Decimal("10") else Decimal("4.0")
    target_scale = r_scale if r_scale is not None else fallback_scale
    s_pct = normalize_to_percentage(s_grade, s_scale)
    r_pct = normalize_to_percentage(r_grade, target_scale)

    if s_pct is None or r_pct is None:
        return False, "Unable to normalize CGPA scales"

    if operator is EligibilityOperator.GTE:
        satisfied = s_pct >= r_pct
    elif operator is EligibilityOperator.LTE:
        satisfied = s_pct <= r_pct
    else:
        satisfied = abs(s_pct - r_pct) <= Decimal("1.0")

    status = "satisfies" if satisfied else "does not satisfy"
    r_scale_label = f"/{r_scale}" if r_scale is not None else ""
    return satisfied, (
        f"CGPA {s_grade}/{s_scale} (~{s_pct}%) {status} requirement "
        f"{r_grade}{r_scale_label} (~{r_pct}%)"
    )
